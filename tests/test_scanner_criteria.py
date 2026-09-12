"""Unit tests for the inclusion gates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from alphadex.scanner.config import ScreenConfig
from alphadex.scanner.criteria import evaluate_gates
from alphadex.scanner.inputs import AssetSnapshot, ObsValue

_NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _cfg(**o: object) -> ScreenConfig:
    base = dict(
        market_cap_min=1e7,
        market_cap_max=1e11,
        min_volume_24h=1e5,
        freshness_max_hours=48.0,
        require_fundamentals=False,
        ref_fees_30d=1e8,
        ref_volume_24h=1e9,
        weight_activity=0.4,
        weight_liquidity=0.3,
        weight_momentum=0.3,
    )
    base.update(o)
    return ScreenConfig(**base)  # type: ignore[arg-type]


def _ok(value: float, *, observed_at: datetime = _NOW) -> ObsValue:
    return ObsValue(value=value, status="OK", observed_at=observed_at)


def _snap(**o: object) -> AssetSnapshot:
    base = dict(
        asset_id=1,
        market_cap=_ok(1e9),
        volume_24h=_ok(5e6),
        price_change_30d=_ok(10.0),
        fees_30d=_ok(1e6),
    )
    base.update(o)
    return AssetSnapshot(**base)  # type: ignore[arg-type]


def test_healthy_asset_passes_all_gates() -> None:
    outcome = evaluate_gates(_snap(), _cfg(), now=_NOW)
    assert outcome.passed
    assert outcome.exclusion_reason is None


def test_below_market_cap_floor_excluded() -> None:
    outcome = evaluate_gates(_snap(market_cap=_ok(1e6)), _cfg(), now=_NOW)
    assert not outcome.passed
    assert outcome.exclusion_reason == "market_cap_min"


def test_above_market_cap_ceiling_excluded() -> None:
    outcome = evaluate_gates(_snap(market_cap=_ok(5e11)), _cfg(), now=_NOW)
    assert not outcome.passed
    assert outcome.exclusion_reason == "market_cap_max"


def test_missing_market_cap_is_not_treated_as_zero() -> None:
    outcome = evaluate_gates(_snap(market_cap=ObsValue.missing()), _cfg(), now=_NOW)
    assert not outcome.passed
    # Fails the presence gate explicitly (not silently scored as 0).
    assert outcome.exclusion_reason == "market_cap_present"


def test_illiquid_asset_excluded() -> None:
    outcome = evaluate_gates(_snap(volume_24h=_ok(1000.0)), _cfg(), now=_NOW)
    assert not outcome.passed
    assert outcome.exclusion_reason == "min_volume_24h"


def test_missing_volume_excluded() -> None:
    outcome = evaluate_gates(_snap(volume_24h=ObsValue.missing()), _cfg(), now=_NOW)
    assert not outcome.passed
    assert outcome.exclusion_reason == "min_volume_24h"


def test_stale_data_excluded() -> None:
    stale = _NOW - timedelta(hours=100)
    outcome = evaluate_gates(
        _snap(market_cap=_ok(1e9, observed_at=stale)), _cfg(), now=_NOW
    )
    assert not outcome.passed
    assert outcome.exclusion_reason == "freshness"


def test_gate_evidence_records_value_and_threshold() -> None:
    outcome = evaluate_gates(_snap(), _cfg(), now=_NOW)
    by_name = {g.name: g for g in outcome.gates}
    assert by_name["min_volume_24h"].value == 5e6
    assert by_name["min_volume_24h"].threshold == 1e5
