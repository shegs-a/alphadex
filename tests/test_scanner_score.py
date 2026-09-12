"""Unit tests for the preliminary Screen Score."""

from __future__ import annotations

from datetime import UTC, datetime

from alphadex.scanner.config import ScreenConfig
from alphadex.scanner.inputs import AssetSnapshot, ObsValue
from alphadex.scanner.score import compute_score

_NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _cfg(**o: object) -> ScreenConfig:
    base = dict(
        market_cap_min=1e7,
        market_cap_max=None,
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


def _ok(value: float) -> ObsValue:
    return ObsValue(value=value, status="OK", observed_at=_NOW)


def _snap(**o: object) -> AssetSnapshot:
    base = dict(
        asset_id=1,
        market_cap=_ok(1e9),
        volume_24h=_ok(5e8),
        price_change_30d=_ok(0.0),
        fees_30d=_ok(1e7),
    )
    base.update(o)
    return AssetSnapshot(**base)  # type: ignore[arg-type]


def test_complete_asset_has_full_completeness_and_bounded_score() -> None:
    out = compute_score(_snap(), _cfg())
    assert out.completeness == 1.0
    assert 0.0 <= out.score <= 1.0


def test_missing_fundamentals_lowers_completeness_not_inflated_score() -> None:
    complete = compute_score(_snap(), _cfg())
    no_fund = compute_score(_snap(fees_30d=ObsValue.missing()), _cfg())
    # Completeness drops; the missing activity contributes 0, never inflating.
    assert no_fund.completeness < complete.completeness
    assert no_fund.score <= complete.score
    activity = next(s for s in no_fund.signals if s.name == "activity")
    assert activity.present is False
    assert activity.normalized is None


def test_higher_momentum_scores_higher() -> None:
    low = compute_score(_snap(price_change_30d=_ok(-40.0)), _cfg())
    high = compute_score(_snap(price_change_30d=_ok(40.0)), _cfg())
    assert high.score > low.score


def test_weights_change_score_predictably() -> None:
    snap = _snap(price_change_30d=_ok(50.0), fees_30d=ObsValue.missing())
    # With no activity, weighting everything on momentum (=1.0) scores higher than
    # spreading weight onto the absent activity signal.
    momentum_heavy = compute_score(
        snap, _cfg(weight_activity=0.0, weight_liquidity=0.0, weight_momentum=1.0)
    )
    activity_heavy = compute_score(
        snap, _cfg(weight_activity=0.8, weight_liquidity=0.1, weight_momentum=0.1)
    )
    assert momentum_heavy.score > activity_heavy.score
