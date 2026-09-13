"""Unit tests for the Alpha Scoring Engine — components, score, confidence, status.

Central to Sprint 07 (ADR-006): renormalizing over available components must never
inflate the Alpha Score, the three outputs stay independent, and a missing component
never buys a ranking advantage.
"""

from __future__ import annotations

import pytest

from alphadex.alpha import components as comp
from alphadex.alpha.components import AlphaComponent, ComponentInputs, build_components
from alphadex.alpha.config import AlphaConfig
from alphadex.alpha.score import (
    BAND_STRONG,
    CONF_LOW,
    STATUS_HIGH_INTEREST,
    STATUS_INSUFFICIENT,
    STATUS_LOW_CONFIDENCE,
    STATUS_RISK_ELEVATED,
    STATUS_THESIS_WEAKENING,
    UpstreamContext,
    score,
)
from alphadex.divergence.engine import (
    CLASS_INSUFFICIENT,
    CLASS_MOMENTUM,
    CLASS_POTENTIAL_MISPRICING,
    CLASS_WEAKENING,
)
from alphadex.marketdata.normalize import (
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
)


def _cfg(**o: object) -> AlphaConfig:
    base = dict(
        scope="all",
        weight_economic_growth=0.25,
        weight_divergence=0.20,
        weight_valuation=0.15,
        weight_token_value_capture=0.15,
        weight_market_strength=0.10,
        weight_tokenomics=0.10,
        weight_technical_setup=0.05,
        ref_fundamentals_growth=0.50,
        ref_market_momentum=0.50,
        ref_market_turnover=0.10,
        conf_weight_completeness=0.60,
        conf_weight_data_quality=0.40,
        confidence_band_moderate=0.40,
        confidence_band_high=0.70,
        status_moderate=0.45,
        status_strong=0.65,
    )
    base.update(o)
    return AlphaConfig(**base)  # type: ignore[arg-type]


# ── Config ──────────────────────────────────────────────────────────────────


def test_config_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        _cfg(weight_economic_growth=0.5)


def test_config_confidence_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="confidence weights must sum to 1.0"):
        _cfg(conf_weight_completeness=0.7, conf_weight_data_quality=0.4)


# ── Component adapters ───────────────────────────────────────────────────────


def test_economic_growth_missing_is_unavailable_not_zero() -> None:
    c = comp.economic_growth(None, _cfg())
    assert c.available is False
    assert c.contribution is None


def test_economic_growth_declining_is_genuine_zero_available() -> None:
    c = comp.economic_growth(-0.3, _cfg())
    assert c.available is True
    assert c.contribution == 0.0  # a real low reading, not missing data


def test_economic_growth_normalizes_against_reference() -> None:
    c = comp.economic_growth(0.25, _cfg())  # half of the 0.50 reference
    assert c.contribution == pytest.approx(0.5)


def test_divergence_maps_by_classification_not_gap() -> None:
    assert comp.divergence(CLASS_POTENTIAL_MISPRICING, 0.9, _cfg()).contribution == 1.0
    # Momentum has already repriced — low opportunity despite any strength.
    assert comp.divergence(CLASS_MOMENTUM, 0.99, _cfg()).contribution == 0.1
    # Weakening thesis is a genuine zero (available), not missing.
    w = comp.divergence(CLASS_WEAKENING, 0.5, _cfg())
    assert w.available is True and w.contribution == 0.0


def test_divergence_insufficient_is_unavailable() -> None:
    c = comp.divergence(CLASS_INSUFFICIENT, None, _cfg())
    assert c.available is False and c.contribution is None
    assert comp.divergence(None, None, _cfg()).available is False


def test_token_value_capture_none_is_unavailable() -> None:
    assert comp.token_value_capture(None, _cfg()).available is False
    assert comp.token_value_capture(0.8, _cfg()).contribution == 0.8


def test_market_strength_averages_momentum_and_turnover() -> None:
    values = {
        METRIC_PRICE_CHANGE_PCT_30D: 25.0,  # +25% → 0.5 of the 0.50 ref
        METRIC_TOTAL_VOLUME_USD: 5e6,
        METRIC_MARKET_CAP_USD: 1e8,  # turnover 5% → 0.5 of the 0.10 ref
    }
    c = comp.market_strength(values, _cfg())
    assert c.available is True
    assert c.contribution == pytest.approx(0.5)


def test_market_strength_missing_is_unavailable() -> None:
    assert comp.market_strength({}, _cfg()).available is False


def test_tokenomics_uses_float_ratio() -> None:
    assert comp.tokenomics(0.6, _cfg()).contribution == 0.6
    assert comp.tokenomics(None, _cfg()).available is False


def test_valuation_consumes_score_and_technical_is_not_implemented() -> None:
    # Valuation graduated in Sprint 08: it now consumes the valuation score.
    assert comp.valuation(0.7, _cfg()).contribution == 0.7
    assert comp.valuation(None, _cfg()).available is False  # unmeasured → unavailable
    # Technical Setup is still not implemented.
    t = comp.technical_setup(_cfg())
    assert t.available is False and t.detail == comp.REASON_NOT_IMPLEMENTED


def test_build_components_returns_seven_in_order() -> None:
    cs = build_components(ComponentInputs(), _cfg())
    assert [c.name for c in cs] == [
        comp.NAME_ECONOMIC_GROWTH,
        comp.NAME_DIVERGENCE,
        comp.NAME_VALUATION,
        comp.NAME_TOKEN_VALUE_CAPTURE,
        comp.NAME_MARKET_STRENGTH,
        comp.NAME_TOKENOMICS,
        comp.NAME_TECHNICAL_SETUP,
    ]


# ── Helpers for score-level tests ────────────────────────────────────────────

_IMPLEMENTED = (
    (comp.NAME_ECONOMIC_GROWTH, 0.25),
    (comp.NAME_DIVERGENCE, 0.20),
    (comp.NAME_TOKEN_VALUE_CAPTURE, 0.15),
    (comp.NAME_MARKET_STRENGTH, 0.10),
    (comp.NAME_TOKENOMICS, 0.10),
)


def _available(name: str, weight: float, value: float) -> AlphaComponent:
    return AlphaComponent(name, weight, value, True, f"{name}={value}")


def _unavailable(name: str, weight: float) -> AlphaComponent:
    return AlphaComponent(name, weight, None, False, "unavailable")


def _five_available(value: float) -> list[AlphaComponent]:
    """The 5 implemented components at ``value``; valuation+technical unavailable."""
    cs = [_available(n, w, value) for n, w in _IMPLEMENTED]
    cs.append(_unavailable(comp.NAME_VALUATION, 0.15))
    cs.append(_unavailable(comp.NAME_TECHNICAL_SETUP, 0.05))
    return cs


# ── Alpha Score: renormalization + no-inflation invariant ────────────────────


def test_alpha_is_renormalized_weighted_average_of_available() -> None:
    a = score(_five_available(0.8), UpstreamContext(), _cfg())
    assert a.alpha_score == pytest.approx(0.8)  # avg of equal values, renormalized
    assert a.model_completeness == pytest.approx(0.80)  # 2 of 7 (0.20) unavailable


def test_alpha_never_exceeds_max_available_contribution() -> None:
    # Mixed contributions; a missing component must not push Alpha out of [min,max].
    values = [0.2, 0.9, 0.4, 0.6, 0.5]
    cs = [_available(n, w, v) for (n, w), v in zip(_IMPLEMENTED, values, strict=True)]
    cs += [
        _unavailable(comp.NAME_VALUATION, 0.15),
        _unavailable(comp.NAME_TECHNICAL_SETUP, 0.05),
    ]
    a = score(cs, UpstreamContext(), _cfg())
    assert a.alpha_score is not None
    assert min(values) <= a.alpha_score <= max(values)


def test_missing_high_component_does_not_inflate_the_shorter_asset() -> None:
    # Asset A: 5 shared at 0.5 + valuation & technical genuinely HIGH (0.9).
    a_components = [_available(n, w, 0.5) for n, w in _IMPLEMENTED]
    a_components += [
        _available(comp.NAME_VALUATION, 0.15, 0.9),
        _available(comp.NAME_TECHNICAL_SETUP, 0.05, 0.9),
    ]
    a = score(a_components, UpstreamContext(), _cfg())
    # Asset B: only the same 5 shared at 0.5 (valuation/technical unavailable).
    b = score(_five_available(0.5), UpstreamContext(), _cfg())
    assert a.alpha_score is not None and b.alpha_score is not None
    # Dropping the high components must LOWER B, never inflate it above A.
    assert b.alpha_score < a.alpha_score


# ── User Test 1: identical available evidence → identical Alpha ──────────────


def test_identical_available_evidence_yields_identical_alpha() -> None:
    a = score(_five_available(0.7), UpstreamContext(), _cfg())
    b = score(_five_available(0.7), UpstreamContext(), _cfg())
    assert a.alpha_score == b.alpha_score
    # Same alpha; Confidence differs ONLY if the data-quality inputs differ.
    assert a.confidence == b.confidence


def test_confidence_differs_only_via_data_quality_inputs() -> None:
    strong_ctx = UpstreamContext(divergence_quality=1.0, tokenomics_quality=1.0)
    weak_ctx = UpstreamContext(divergence_quality=0.2, tokenomics_quality=0.2)
    a = score(_five_available(0.7), strong_ctx, _cfg())
    b = score(_five_available(0.7), weak_ctx, _cfg())
    assert a.alpha_score == b.alpha_score  # identical evidence → identical Alpha
    assert a.confidence > b.confidence  # only the data quality moved Confidence


# ── User Test 2: a shorter component set must not out-rank a complete one ─────


def test_more_complete_asset_outranks_equal_score_incomplete_asset() -> None:
    # Asset A: all 7 available, the 2 extras set NEUTRAL (== the shared value) so the
    # renormalized Alpha is unchanged. Asset B: only the 5 shared, same values.
    a_components = [_available(n, w, 0.6) for n, w in _IMPLEMENTED]
    a_components += [
        _available(comp.NAME_VALUATION, 0.15, 0.6),
        _available(comp.NAME_TECHNICAL_SETUP, 0.05, 0.6),
    ]
    a = score(a_components, UpstreamContext(), _cfg())
    b = score(_five_available(0.6), UpstreamContext(), _cfg())

    assert a.alpha_score == pytest.approx(b.alpha_score)  # a tie on Alpha
    assert a.model_completeness > b.model_completeness
    # The completeness tie-break orders the MORE-complete asset first — the shorter
    # set never out-ranks it merely because its weights were renormalized.
    assert a.rank_key < b.rank_key


# ── Confidence ───────────────────────────────────────────────────────────────


def test_confidence_capped_when_few_components_available() -> None:
    # Only market_strength (0.10) + tokenomics (0.10) available → completeness 0.20.
    cs = [
        _unavailable(comp.NAME_ECONOMIC_GROWTH, 0.25),
        _unavailable(comp.NAME_DIVERGENCE, 0.20),
        _unavailable(comp.NAME_VALUATION, 0.15),
        _unavailable(comp.NAME_TOKEN_VALUE_CAPTURE, 0.15),
        _available(comp.NAME_MARKET_STRENGTH, 0.10, 0.8),
        _available(comp.NAME_TOKENOMICS, 0.10, 0.8),
        _unavailable(comp.NAME_TECHNICAL_SETUP, 0.05),
    ]
    a = score(cs, UpstreamContext(), _cfg())
    assert a.model_completeness == pytest.approx(0.20)
    assert a.confidence_band == CONF_LOW


# ── Decision status (down-classification; no BUY) ────────────────────────────


def test_status_high_interest_needs_strong_alpha_and_high_confidence() -> None:
    ctx = UpstreamContext(
        divergence_quality=1.0, tokenomics_quality=1.0, risk_band="low"
    )
    a = score(_five_available(0.9), ctx, _cfg())
    assert a.alpha_band == BAND_STRONG
    assert a.status == STATUS_HIGH_INTEREST


def test_high_alpha_high_risk_is_down_classified() -> None:
    ctx = UpstreamContext(
        divergence_quality=1.0, tokenomics_quality=1.0, risk_band="high"
    )
    a = score(_five_available(0.9), ctx, _cfg())
    assert a.status == STATUS_RISK_ELEVATED  # not high_interest


def test_high_alpha_low_confidence_is_down_classified() -> None:
    # No upstream quality and weak completeness pressure → low confidence.
    a = score(_five_available(0.9), UpstreamContext(risk_band="low"), _cfg())
    if a.confidence_band == CONF_LOW:
        assert a.status == STATUS_LOW_CONFIDENCE


def test_thesis_weakening_classification_sets_status() -> None:
    ctx = UpstreamContext(
        divergence_classification=CLASS_WEAKENING,
        divergence_quality=1.0,
        tokenomics_quality=1.0,
        risk_band="low",
    )
    a = score(_five_available(0.5), ctx, _cfg())
    assert a.status == STATUS_THESIS_WEAKENING


def test_no_available_components_is_insufficient_data() -> None:
    cs = build_components(ComponentInputs(), _cfg())  # nothing supplied
    a = score(cs, UpstreamContext(), _cfg())
    assert a.alpha_score is None
    assert a.status == STATUS_INSUFFICIENT
    assert a.alpha_band == "unknown"
