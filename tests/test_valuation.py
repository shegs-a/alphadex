"""Unit tests for the Valuation engine — multiples and relative-attractiveness score.

Guardrails under test (Sprint 08): attractiveness is relative (not fair value); the
four multiples keep distinct meanings; completeness is separate from the score; mixed/
conflicting evidence and single-multiple availability are handled; missing/undefined
inputs are None, never 0.
"""

from __future__ import annotations

import pytest

from alphadex.fundamentals.normalize import (
    METRIC_FEES_30D_USD,
    METRIC_HOLDERS_REVENUE_30D_USD,
    METRIC_REVENUE_30D_USD,
    METRIC_TVL_USD,
)
from alphadex.marketdata.normalize import METRIC_MARKET_CAP_USD
from alphadex.valuation import multiples
from alphadex.valuation.config import ValuationConfig
from alphadex.valuation.score import (
    LABEL_CHEAP,
    LABEL_EXPENSIVE,
    LABEL_UNKNOWN,
    evaluate,
)


def _cfg(**o: object) -> ValuationConfig:
    base = dict(
        scope="all",
        ref_price_to_fees=30.0,
        ref_price_to_revenue=40.0,
        ref_price_to_holders_revenue=20.0,
        ref_mcap_to_tvl=1.0,
        weight_fees=0.30,
        weight_revenue=0.30,
        weight_holders_revenue=0.25,
        weight_tvl=0.15,
        band_expensive=0.40,
        band_cheap=0.66,
    )
    base.update(o)
    return ValuationConfig(**base)  # type: ignore[arg-type]


# annualized flow = value * 365/30
def _annual(v: float) -> float:
    return v * (365.0 / 30.0)


# ── Config ──────────────────────────────────────────────────────────────────


def test_config_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        _cfg(weight_fees=0.5)


def test_config_bands_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="expensive < cheap"):
        _cfg(band_expensive=0.7, band_cheap=0.5)


# ── Multiples ─────────────────────────────────────────────────────────────────


def test_multiples_missing_inputs_are_none_not_zero() -> None:
    assert multiples.price_to_fees({}) is None
    assert multiples.price_to_revenue({}) is None
    assert multiples.price_to_holders_revenue({}) is None
    assert multiples.mcap_to_tvl({}) is None


def test_multiples_zero_denominator_is_none_not_zero() -> None:
    v = {METRIC_MARKET_CAP_USD: 1e9, METRIC_FEES_30D_USD: 0.0, METRIC_TVL_USD: 0.0}
    assert multiples.price_to_fees(v) is None  # undefined, not a false 0
    assert multiples.mcap_to_tvl(v) is None


def test_multiples_retain_distinct_economic_meanings() -> None:
    v = {
        METRIC_MARKET_CAP_USD: 1e9,
        METRIC_FEES_30D_USD: 100.0,
        METRIC_REVENUE_30D_USD: 50.0,  # revenue != fees
        METRIC_HOLDERS_REVENUE_30D_USD: 25.0,  # holders-revenue != revenue
        METRIC_TVL_USD: 2e8,
    }
    pf = multiples.price_to_fees(v)
    ps = multiples.price_to_revenue(v)
    phr = multiples.price_to_holders_revenue(v)
    mtv = multiples.mcap_to_tvl(v)
    # Distinct denominators → distinct multiples, never collapsed.
    assert pf is not None and ps is not None and phr is not None and mtv is not None
    assert pf < ps < phr  # smaller denominator → larger multiple
    assert mtv == pytest.approx(5.0)


# ── Score: relative attractiveness ─────────────────────────────────────────────


def test_reference_multiple_maps_to_half_attractiveness() -> None:
    # market cap / annualized fees == ref (30) → attractiveness 0.5.
    v = {METRIC_MARKET_CAP_USD: 30.0 * _annual(30.0), METRIC_FEES_30D_USD: 30.0}
    out = evaluate(v, _cfg())
    assert out.price_to_fees == pytest.approx(30.0)
    assert out.valuation_score == pytest.approx(0.5)  # only fees present
    assert out.data_completeness == pytest.approx(0.25)  # 1 of 4 multiples


def test_lower_multiple_is_more_attractive_monotonic() -> None:
    cheap = {METRIC_MARKET_CAP_USD: 5.0 * _annual(30.0), METRIC_FEES_30D_USD: 30.0}
    rich = {METRIC_MARKET_CAP_USD: 90.0 * _annual(30.0), METRIC_FEES_30D_USD: 30.0}
    cheap_out = evaluate(cheap, _cfg())
    rich_out = evaluate(rich, _cfg())
    assert (
        cheap_out.valuation_score is not None and rich_out.valuation_score is not None
    )
    assert cheap_out.valuation_score > rich_out.valuation_score
    assert cheap_out.valuation_label == LABEL_CHEAP
    assert rich_out.valuation_label == LABEL_EXPENSIVE


def test_score_none_unless_a_multiple_is_measurable() -> None:
    out = evaluate({}, _cfg())
    assert out.valuation_score is None
    assert out.valuation_label == LABEL_UNKNOWN
    assert out.data_completeness == 0.0
    # market cap alone (no flows/TVL) → nothing measurable.
    only_mc = evaluate({METRIC_MARKET_CAP_USD: 1e9}, _cfg())
    assert only_mc.valuation_score is None


def test_single_multiple_availability_scores_on_that_alone() -> None:
    # Only Mcap/TVL available → scored on it, low completeness, not fabricated.
    v = {METRIC_MARKET_CAP_USD: 1e9, METRIC_TVL_USD: 1e9}  # ratio 1.0 == ref
    out = evaluate(v, _cfg())
    assert out.mcap_to_tvl == pytest.approx(1.0)
    assert out.price_to_fees is None
    assert out.valuation_score == pytest.approx(0.5)  # ref → 0.5, on TVL alone
    assert out.data_completeness == pytest.approx(0.25)


def test_mixed_conflicting_evidence_blends_and_surfaces_both_sides() -> None:
    # Cheap on fees (P/F = 5), expensive on TVL (Mcap/TVL = 10).
    mc = 1e9
    v = {
        METRIC_MARKET_CAP_USD: mc,
        METRIC_FEES_30D_USD: (mc / 5.0) * (30.0 / 365.0),  # → P/F = 5
        METRIC_TVL_USD: mc / 10.0,  # → Mcap/TVL = 10
    }
    out = evaluate(v, _cfg())
    assert out.price_to_fees == pytest.approx(5.0)
    assert out.mcap_to_tvl == pytest.approx(10.0)
    # Blend lands strictly between the cheap and rich attractiveness values.
    a_fees = 30.0 / (30.0 + 5.0)  # ~0.857
    a_tvl = 1.0 / (1.0 + 10.0)  # ~0.091
    assert out.valuation_score is not None
    assert min(a_fees, a_tvl) < out.valuation_score < max(a_fees, a_tvl)
    # Evidence surfaces both sides of the conflict.
    assert out.evidence["cheaper_on"] and out.evidence["richer_on"]
    assert out.data_completeness == pytest.approx(0.5)


def test_evidence_states_relative_basis_not_fair_value() -> None:
    v = {METRIC_MARKET_CAP_USD: 1e9, METRIC_TVL_USD: 1e9}
    out = evaluate(v, _cfg())
    assert "not an intrinsic/fair-value estimate" in out.evidence["basis"].lower()


def test_completeness_is_separate_from_score() -> None:
    # Two assets with the SAME measurable multiple (same score) but differing coverage.
    one = evaluate({METRIC_MARKET_CAP_USD: 1e9, METRIC_TVL_USD: 1e9}, _cfg())
    two = evaluate(
        {
            METRIC_MARKET_CAP_USD: 1e9,
            METRIC_TVL_USD: 1e9,
            METRIC_FEES_30D_USD: (1e9) * (30.0 / 365.0) / 1.0,  # P/F = 1.0 (very cheap)
        },
        _cfg(),
    )
    # Completeness rose with the extra multiple; the score is NOT the completeness.
    assert two.data_completeness > one.data_completeness
    assert one.valuation_score == pytest.approx(0.5)  # unchanged by completeness
