"""Unit tests for divergence trend computations (Track A and Track B)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from alphadex.divergence.config import DivergenceConfig
from alphadex.divergence.inputs import AssetSeries, ObsPoint
from alphadex.divergence.trends import (
    METHOD_CROSS_TIME,
    METHOD_GROWTH_WINDOW,
    fundamentals_trend,
    price_trend,
    valuation_multiple,
)
from alphadex.fundamentals.normalize import METRIC_FEES_7D_USD, METRIC_FEES_30D_USD
from alphadex.marketdata.normalize import (
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_PRICE_USD,
)

_NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def _cfg(**o: object) -> DivergenceConfig:
    base = dict(
        scope="candidates",
        min_history_days=5.0,
        threshold=0.15,
        min_fundamentals_improvement=0.05,
        price_stagnant_ceiling=0.05,
        price_strong_threshold=0.50,
        weight_gap=0.7,
        weight_valuation=0.3,
    )
    base.update(o)
    return DivergenceConfig(**base)  # type: ignore[arg-type]


def _series(points: dict[str, list[tuple[float, float]]]) -> AssetSeries:
    """points: metric -> list of (days_ago, value), oldest→newest by days_ago desc."""
    s = AssetSeries(asset_id=1)
    for metric, pts in points.items():
        s.series[metric] = [
            ObsPoint(observed_at=_NOW - timedelta(days=d), value=v)
            for d, v in sorted(pts, key=lambda x: -x[0])
        ]
    return s


def test_fundamentals_track_a_acceleration() -> None:
    # 7d run-rate > 30d run-rate → positive acceleration (single snapshot).
    s = _series({METRIC_FEES_7D_USD: [(0, 10.0)], METRIC_FEES_30D_USD: [(0, 30.0)]})
    res = fundamentals_trend(s, _cfg())
    assert res.method == METHOD_GROWTH_WINDOW
    assert res.value is not None and res.value > 0


def test_fundamentals_track_b_preferred_over_track_a() -> None:
    # Two fees_30d observations 10 days apart → cross-time wins over the window.
    s = _series(
        {
            METRIC_FEES_30D_USD: [(10, 100.0), (0, 150.0)],
            METRIC_FEES_7D_USD: [(0, 10.0)],
        }
    )
    res = fundamentals_trend(s, _cfg())
    assert res.method == METHOD_CROSS_TIME
    assert res.value == 0.5  # (150-100)/100


def test_fundamentals_insufficient_is_none_not_zero() -> None:
    res = fundamentals_trend(_series({}), _cfg())
    assert res.value is None
    assert res.method == "none"


def test_prior_requires_minimum_gap() -> None:
    # Two points only 2 days apart, min_history 5 → no cross-time trend.
    s = _series({METRIC_PRICE_USD: [(2, 100.0), (0, 120.0)]})
    res = price_trend(s, _cfg(min_history_days=5.0))
    # Falls back to provider window if present; here none → None.
    assert res.value is None


def test_price_track_a_from_provider_window() -> None:
    s = _series({METRIC_PRICE_CHANGE_PCT_30D: [(0, -10.0)]})
    res = price_trend(s, _cfg())
    assert res.method == METHOD_GROWTH_WINDOW
    assert res.value == -0.1


def test_valuation_multiple() -> None:
    s = _series(
        {METRIC_MARKET_CAP_USD: [(0, 3650.0)], METRIC_FEES_30D_USD: [(0, 30.0)]}
    )
    # annualized fees = 30 * 365/30 = 365; multiple = 3650/365 = 10
    assert valuation_multiple(s) == 10.0


def test_valuation_multiple_missing_is_none() -> None:
    assert valuation_multiple(_series({METRIC_MARKET_CAP_USD: [(0, 100.0)]})) is None
