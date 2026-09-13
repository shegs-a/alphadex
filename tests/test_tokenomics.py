"""Unit tests for the Tokenomics (Token Value Capture) engine."""

from __future__ import annotations

import pytest

from alphadex.fundamentals.normalize import (
    METRIC_FEES_30D_USD,
    METRIC_HOLDERS_REVENUE_30D_USD,
    METRIC_REVENUE_30D_USD,
)
from alphadex.marketdata.normalize import (
    METRIC_CIRCULATING_SUPPLY,
    METRIC_FDV_USD,
    METRIC_MARKET_CAP_USD,
    METRIC_MAX_SUPPLY,
)
from alphadex.tokenomics import signals
from alphadex.tokenomics.config import TokenomicsConfig
from alphadex.tokenomics.score import LABEL_UNKNOWN, evaluate


def _cfg(**o: object) -> TokenomicsConfig:
    base = dict(
        scope="all",
        ref_real_yield=0.10,
        weight_dilution=0.5,
        weight_value_capture=0.5,
    )
    base.update(o)
    return TokenomicsConfig(**base)  # type: ignore[arg-type]


def _full() -> dict[str, float]:
    return {
        METRIC_MARKET_CAP_USD: 5e8,
        METRIC_FDV_USD: 1e9,  # float ratio 0.5
        METRIC_FEES_30D_USD: 100.0,
        METRIC_REVENUE_30D_USD: 30.0,  # revenue/fees 0.3
        METRIC_HOLDERS_REVENUE_30D_USD: 15.0,  # holders/revenue 0.5
    }


def test_config_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        _cfg(weight_dilution=0.6, weight_value_capture=0.5)


def test_float_ratio_prefers_mc_over_fdv() -> None:
    assert signals.float_ratio({METRIC_MARKET_CAP_USD: 5e8, METRIC_FDV_USD: 1e9}) == 0.5


def test_float_ratio_falls_back_to_supply() -> None:
    v = {METRIC_CIRCULATING_SUPPLY: 60.0, METRIC_MAX_SUPPLY: 100.0}
    assert signals.float_ratio(v) == 0.6


def test_signals_missing_are_none_not_zero() -> None:
    assert signals.float_ratio({}) is None
    assert signals.revenue_to_fees({}) is None
    assert signals.holders_to_revenue({}) is None
    assert signals.real_yield({}) is None


def test_fees_revenue_holders_kept_distinct() -> None:
    v = _full()
    assert signals.revenue_to_fees(v) == 0.3
    assert signals.holders_to_revenue(v) == 0.5
    # Distinct ratios, not collapsed.
    assert signals.revenue_to_fees(v) != signals.holders_to_revenue(v)


def test_score_full_data() -> None:
    out = evaluate(_full(), _cfg())
    assert out.value_capture_score is not None
    assert 0.0 <= out.value_capture_score <= 1.0
    # float ratio, revenue/fees, holders/revenue, and real yield all computable.
    assert out.data_completeness == 1.0


def test_dilution_only_yields_null_score_but_exposes_float_ratio() -> None:
    # Sprint 06.1: a strong float ratio alone is NOT value capture. The score must be
    # None (not a positive sentinel), while float_ratio is still exposed separately.
    only_supply = {METRIC_MARKET_CAP_USD: 5e8, METRIC_FDV_USD: 1e9}
    out = evaluate(only_supply, _cfg())
    assert out.value_capture_score is None
    assert out.value_capture_label == LABEL_UNKNOWN
    assert out.float_ratio == 0.5  # dilution measurement still available
    assert out.data_completeness == 0.25  # 1/4 sub-signals


def test_100pct_float_low_dilution_is_not_strong_value_capture() -> None:
    # ETH/stablecoin pattern: float ratio 1.0, no fee/revenue/holders data.
    out = evaluate({METRIC_MARKET_CAP_USD: 1e9, METRIC_FDV_USD: 1e9}, _cfg())
    assert out.float_ratio == 1.0
    assert out.value_capture_score is None  # never 1.0 "strong"
    assert out.value_capture_label == LABEL_UNKNOWN


def test_significant_dilution_still_null_without_value_capture() -> None:
    out = evaluate({METRIC_MARKET_CAP_USD: 2e8, METRIC_FDV_USD: 1e9}, _cfg())
    assert out.float_ratio == 0.2  # heavy overhang, exposed as a measurement
    assert out.value_capture_score is None
    assert out.value_capture_label == LABEL_UNKNOWN


def test_value_capture_present_yields_a_real_score() -> None:
    # Dilution + value capture both present → a genuine blended score.
    out = evaluate(_full(), _cfg())
    assert out.value_capture_score is not None
    assert out.value_capture_label in ("strong", "moderate", "weak")


def test_genuine_zero_value_capture_is_distinct_from_unknown() -> None:
    # revenue = 0 (a real zero) → revenue_to_fees 0.0, a genuine value, NOT null.
    v = {
        METRIC_MARKET_CAP_USD: 5e8,
        METRIC_FDV_USD: 1e9,
        METRIC_FEES_30D_USD: 100.0,
        METRIC_REVENUE_30D_USD: 0.0,  # genuine zero: protocol keeps nothing
    }
    out = evaluate(v, _cfg())
    assert out.revenue_to_fees == 0.0  # zero, not None
    assert out.value_capture_score is not None  # value capture WAS measured (as 0)
    assert out.value_capture_label in ("weak", "moderate", "strong")


def test_all_missing_is_unknown_null_not_zero() -> None:
    out = evaluate({}, _cfg())
    assert out.value_capture_score is None
    assert out.value_capture_label == LABEL_UNKNOWN
