"""Preliminary Screen Score.

A transparent, configurable blend of a few cheap, single-snapshot signals used only
to **order** candidates. This is explicitly NOT the Alpha Score (Sprint 07). A
missing signal contributes nothing and lowers ``data_completeness`` — it can never
inflate a score, so incomplete data cannot masquerade as strength (§10, ADR-003).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from alphadex.scanner.config import ScreenConfig
from alphadex.scanner.inputs import AssetSnapshot


@dataclass(frozen=True)
class SignalBreakdown:
    name: str
    present: bool
    raw: float | None
    normalized: float | None
    weight: float

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "present": self.present,
            "raw": self.raw,
            "normalized": self.normalized,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class ScoreBreakdown:
    score: float
    completeness: float
    signals: list[SignalBreakdown]

    def signals_as_dict(self) -> list[dict]:
        return [s.as_dict() for s in self.signals]


def _log_norm(value: float, reference: float) -> float:
    """Log-scaled normalization to [0, 1] against a reference magnitude."""
    if value <= 0:
        return 0.0
    return min(1.0, math.log10(1.0 + value) / math.log10(1.0 + reference))


def _momentum_norm(pct: float) -> float:
    """Map a 30d price change % to [0, 1] (-50% → 0, 0% → 0.5, +50% → 1)."""
    return max(0.0, min(1.0, (pct + 50.0) / 100.0))


def compute_score(snapshot: AssetSnapshot, config: ScreenConfig) -> ScoreBreakdown:
    """Compute the preliminary Screen Score and data completeness for an asset."""
    signals: list[SignalBreakdown] = []

    # Activity — protocol economics (fundamentals). Absent for non-DeFi assets.
    fees = snapshot.fees_30d
    activity_norm = (
        _log_norm(fees.value, config.ref_fees_30d)
        if fees.present and fees.value is not None
        else None
    )
    signals.append(
        SignalBreakdown(
            "activity", fees.present, fees.value, activity_norm, config.weight_activity
        )
    )

    # Liquidity — 24h volume.
    vol = snapshot.volume_24h
    liq_norm = (
        _log_norm(vol.value, config.ref_volume_24h)
        if vol.present and vol.value is not None
        else None
    )
    signals.append(
        SignalBreakdown(
            "liquidity", vol.present, vol.value, liq_norm, config.weight_liquidity
        )
    )

    # Momentum — 30d price change.
    mom = snapshot.price_change_30d
    mom_norm = (
        _momentum_norm(mom.value) if mom.present and mom.value is not None else None
    )
    signals.append(
        SignalBreakdown(
            "momentum", mom.present, mom.value, mom_norm, config.weight_momentum
        )
    )

    score = sum(s.weight * (s.normalized or 0.0) for s in signals)
    present = sum(1 for s in signals if s.present)
    completeness = present / len(signals)
    return ScoreBreakdown(score=score, completeness=completeness, signals=signals)
