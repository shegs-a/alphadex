"""Unit tests for the divergence engine (scoring, classification, evidence)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from alphadex.divergence.config import DivergenceConfig
from alphadex.divergence.engine import (
    CLASS_DIVERGENCE,
    CLASS_INSUFFICIENT,
    CLASS_WEAKENING,
    evaluate,
)
from alphadex.divergence.inputs import AssetSeries, ObsPoint
from alphadex.fundamentals.normalize import METRIC_FEES_7D_USD, METRIC_FEES_30D_USD
from alphadex.marketdata.normalize import METRIC_PRICE_CHANGE_PCT_30D, METRIC_PRICE_USD

_NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
_FORBIDDEN = ("BUY", "GUARANTEED", "100% PUMP", "RISK FREE")


def _cfg(**o: object) -> DivergenceConfig:
    base = dict(
        scope="candidates",
        min_history_days=5.0,
        threshold=0.15,
        weakening_threshold=-0.15,
        min_fundamentals_improvement=0.05,
        weight_gap=0.7,
        weight_valuation=0.3,
    )
    base.update(o)
    return DivergenceConfig(**base)  # type: ignore[arg-type]


def _series(points: dict[str, list[tuple[float, float]]]) -> AssetSeries:
    s = AssetSeries(asset_id=1)
    for metric, pts in points.items():
        s.series[metric] = [
            ObsPoint(observed_at=_NOW - timedelta(days=d), value=v)
            for d, v in sorted(pts, key=lambda x: -x[0])
        ]
    return s


def test_fundamental_divergence_when_fundamentals_up_price_lagging() -> None:
    s = _series(
        {
            METRIC_FEES_7D_USD: [(0, 12.0)],  # rate 12*52.1=625
            METRIC_FEES_30D_USD: [(0, 30.0)],  # rate 30*12.17=365 → +71% accel
            METRIC_PRICE_CHANGE_PCT_30D: [(0, -15.0)],  # price -15%
        }
    )
    out = evaluate(s, _cfg())
    assert out.classification == CLASS_DIVERGENCE
    assert out.divergence_score is not None and out.divergence_score > 0.15
    assert out.method == "growth_window"
    # Evidence answers the §10 questions.
    for key in (
        "what_changed",
        "why_now",
        "what_supports",
        "what_contradicts",
        "what_invalidates",
        "major_risk",
    ):
        assert key in out.evidence


def test_thesis_weakening_when_fundamentals_declining() -> None:
    s = _series(
        {
            METRIC_FEES_7D_USD: [(0, 4.0)],  # rate low → deceleration
            METRIC_FEES_30D_USD: [(0, 30.0)],
            METRIC_PRICE_CHANGE_PCT_30D: [(0, 5.0)],
        }
    )
    out = evaluate(s, _cfg())
    assert out.classification == CLASS_WEAKENING


def test_insufficient_data_is_null_score_not_zero() -> None:
    out = evaluate(_series({METRIC_PRICE_CHANGE_PCT_30D: [(0, 5.0)]}), _cfg())
    # No fundamentals trend → cannot assess divergence.
    assert out.classification == CLASS_INSUFFICIENT
    assert out.divergence_score is None  # never a fake 0


def test_cross_time_method_reported_and_higher_quality() -> None:
    s = _series(
        {
            METRIC_FEES_30D_USD: [(10, 100.0), (0, 160.0)],  # +60% cross-time
            METRIC_PRICE_USD: [(10, 100.0), (0, 100.0)],  # flat price
        }
    )
    out = evaluate(s, _cfg())
    assert out.method == "cross_time"
    assert out.data_quality is not None and out.data_quality >= 0.5
    assert out.classification == CLASS_DIVERGENCE


def test_no_buy_language_in_evidence() -> None:
    s = _series(
        {
            METRIC_FEES_7D_USD: [(0, 12.0)],
            METRIC_FEES_30D_USD: [(0, 30.0)],
            METRIC_PRICE_CHANGE_PCT_30D: [(0, -15.0)],
        }
    )
    payload = json.dumps(evaluate(s, _cfg()).evidence).upper()
    for term in _FORBIDDEN:
        assert term not in payload
