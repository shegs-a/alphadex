"""Inclusion gates for the screen.

Each gate is a pure check over an asset's latest observations that returns its
outcome **plus the value and threshold considered**, so a scan result can explain
exactly why an asset passed or failed (§10). Missing inputs fail their gate
explicitly — never evaluated as ``0`` (ADR-003).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from alphadex.scanner.config import ScreenConfig
from alphadex.scanner.inputs import AssetSnapshot


@dataclass(frozen=True)
class GateEval:
    """The outcome of one gate, with the evidence behind it."""

    name: str
    passed: bool
    value: float | None
    threshold: float | None
    detail: str

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class GatesOutcome:
    """All gate outcomes for an asset plus the overall pass/fail."""

    passed: bool
    gates: list[GateEval]
    exclusion_reason: str | None


def evaluate_gates(
    snapshot: AssetSnapshot,
    config: ScreenConfig,
    *,
    now: datetime | None = None,
) -> GatesOutcome:
    """Run every inclusion gate and combine them (all must pass)."""
    now = now or datetime.now(UTC)
    gates: list[GateEval] = []

    mc = snapshot.market_cap
    if not mc.present:
        gates.append(
            GateEval("market_cap_present", False, None, None, "market cap unavailable")
        )
    else:
        gates.append(
            GateEval(
                "market_cap_min",
                mc.value >= config.market_cap_min,  # type: ignore[operator]
                mc.value,
                config.market_cap_min,
                "market cap at or above floor",
            )
        )
        if config.market_cap_max is not None:
            gates.append(
                GateEval(
                    "market_cap_max",
                    mc.value <= config.market_cap_max,  # type: ignore[operator]
                    mc.value,
                    config.market_cap_max,
                    "market cap at or below ceiling",
                )
            )

    vol = snapshot.volume_24h
    gates.append(
        GateEval(
            "min_volume_24h",
            vol.present and vol.value >= config.min_volume_24h,  # type: ignore[operator]
            vol.value,
            config.min_volume_24h,
            "24h volume at or above floor" if vol.present else "24h volume unavailable",
        )
    )

    age_hours = _age_hours(mc.observed_at, now) if mc.observed_at else None
    gates.append(
        GateEval(
            "freshness",
            age_hours is not None and age_hours <= config.freshness_max_hours,
            age_hours,
            config.freshness_max_hours,
            "market data within freshness window"
            if age_hours is not None
            else "no market observation timestamp",
        )
    )

    passed = all(g.passed for g in gates)
    exclusion_reason = None
    if not passed:
        exclusion_reason = next(g.name for g in gates if not g.passed)
    return GatesOutcome(passed=passed, gates=gates, exclusion_reason=exclusion_reason)


def _age_hours(observed_at: datetime, now: datetime) -> float:
    ts = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=UTC)
    return (now - ts).total_seconds() / 3600.0
