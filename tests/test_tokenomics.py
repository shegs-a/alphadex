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


def test_missing_value_capture_uses_dilution_only_and_lowers_completeness() -> None:
    only_supply = {METRIC_MARKET_CAP_USD: 5e8, METRIC_FDV_USD: 1e9}
    out = evaluate(only_supply, _cfg())
    # Only the dilution component is present → score equals float ratio (0.5)…
    assert out.value_capture_score == 0.5
    assert out.data_completeness == 0.25  # 1/4 sub-signals
    assert out.revenue_to_fees is None
    # …but value capture itself is unmeasured, so the label must not claim it.
    assert out.value_capture_label == LABEL_UNKNOWN


def test_all_missing_is_unknown_null_not_zero() -> None:
    out = evaluate({}, _cfg())
    assert out.value_capture_score is None
    assert out.value_capture_label == LABEL_UNKNOWN


def test_missing_inputs_never_inflate_score() -> None:
    # A token with only a strong float ratio must not out-score by "assuming" the
    # missing value-capture is favorable.
    only_float = evaluate({METRIC_MARKET_CAP_USD: 9e8, METRIC_FDV_USD: 1e9}, _cfg())
    assert only_float.value_capture_score == 0.9  # just the dilution component
