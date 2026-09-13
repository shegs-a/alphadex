"""Unit tests for the divergence engine — classification, measurement, evidence.

Covers the Sprint 05.1 case matrix (A–G), including the VVV regression, that
distinguishes genuine divergence from repricing/momentum (ADR-005).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from alphadex.divergence.config import DivergenceConfig
from alphadex.divergence.engine import (
    CLASS_DIVERGENCE,
    CLASS_INSUFFICIENT,
    CLASS_MOMENTUM,
    CLASS_POTENTIAL_MISPRICING,
    CLASS_REPRICING,
    CLASS_WATCH,
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
        min_fundamentals_improvement=0.05,
        price_stagnant_ceiling=0.05,
        price_strong_threshold=0.50,
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


def _snapshot(*, fees_7d: float, fees_30d: float, price_30d_pct: float) -> AssetSeries:
    return _series(
        {
            METRIC_FEES_7D_USD: [(0, fees_7d)],
            METRIC_FEES_30D_USD: [(0, fees_30d)],
            METRIC_PRICE_CHANGE_PCT_30D: [(0, price_30d_pct)],
        }
    )


# fees_7d=12, fees_30d=30 → 7d run-rate ~+71% above 30d baseline (improving).
# fees_7d=7,  fees_30d=30 → run-rates equal → ~0% (not materially improving).
# fees_7d=4,  fees_30d=30 → run-rate below baseline → declining.


def test_case_a_potential_mispricing() -> None:
    # Fundamentals strongly improving, price falling.
    out = evaluate(_snapshot(fees_7d=12, fees_30d=30, price_30d_pct=-15.0), _cfg())
    assert out.classification == CLASS_POTENTIAL_MISPRICING


def test_case_b_fundamental_divergence() -> None:
    # Fundamentals improving, price relatively flat/modestly positive.
    out = evaluate(_snapshot(fees_7d=12, fees_30d=30, price_30d_pct=10.0), _cfg())
    assert out.classification == CLASS_DIVERGENCE


def test_case_c_fundamental_repricing() -> None:
    # Fundamentals improving strongly AND price also rising strongly.
    out = evaluate(_snapshot(fees_7d=12, fees_30d=30, price_30d_pct=60.0), _cfg())
    assert out.classification == CLASS_REPRICING


def test_case_d_momentum() -> None:
    # Price strongly positive without material fundamental support.
    out = evaluate(_snapshot(fees_7d=7, fees_30d=30, price_30d_pct=60.0), _cfg())
    assert out.classification == CLASS_MOMENTUM


def test_case_e_thesis_weakening() -> None:
    # Fundamentals deteriorating.
    out = evaluate(_snapshot(fees_7d=4, fees_30d=30, price_30d_pct=5.0), _cfg())
    assert out.classification == CLASS_WEAKENING


def test_case_f_insufficient_data_is_null_not_zero() -> None:
    out = evaluate(_series({METRIC_PRICE_CHANGE_PCT_30D: [(0, 5.0)]}), _cfg())
    assert out.classification == CLASS_INSUFFICIENT
    assert out.divergence_score is None  # never a fake 0
    assert out.signal_strength is None


def test_case_g_vvv_regression_is_not_fundamental_divergence() -> None:
    # VVV's real pattern: fundamentals +155.8%, price +98.3%.
    out = evaluate(
        _snapshot(fees_7d=469881, fees_30d=787316, price_30d_pct=98.3), _cfg()
    )
    # Must NOT be represented as undiscovered divergence — price already repriced.
    assert out.classification != CLASS_DIVERGENCE
    assert out.classification == CLASS_REPRICING
    # The measured gap is still positive and recorded — measurement is preserved.
    assert out.divergence_gap is not None and out.divergence_gap > 0
    assert out.signal_strength is not None


def test_watch_when_gap_too_small() -> None:
    # Improving but price moderately up and gap below threshold → watch.
    out = evaluate(_snapshot(fees_7d=7.5, fees_30d=30, price_30d_pct=10.0), _cfg())
    assert out.classification == CLASS_WATCH


def test_measurement_fields_are_distinct() -> None:
    out = evaluate(_snapshot(fees_7d=12, fees_30d=30, price_30d_pct=-15.0), _cfg())
    # Raw gap (unclamped) vs clamped/blended score vs magnitude are separate.
    assert out.divergence_gap is not None
    assert out.divergence_score is not None
    assert out.signal_strength is not None
    assert out.data_quality is not None
    # Growth-window single-snapshot → low evidence strength.
    assert out.evidence["evidence_strength"] == "low"


def test_cross_time_method_and_medium_evidence() -> None:
    # Two fees_30d obs (+60%) and flat price across history → cross-time method.
    s = _series(
        {
            METRIC_FEES_30D_USD: [(10, 100.0), (0, 160.0)],
            METRIC_PRICE_USD: [(10, 100.0), (0, 100.0)],
        }
    )
    out = evaluate(s, _cfg())
    assert out.method == "cross_time"
    assert out.evidence["evidence_strength"] == "medium"
    # Fundamentals up, price flat → potential mispricing.
    assert out.classification == CLASS_POTENTIAL_MISPRICING


def test_no_buy_language_across_classes() -> None:
    for price in (-15.0, 10.0, 60.0):
        out = evaluate(_snapshot(fees_7d=12, fees_30d=30, price_30d_pct=price), _cfg())
        payload = json.dumps(out.evidence).upper()
        for term in _FORBIDDEN:
            assert term not in payload
