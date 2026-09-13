"""Unit tests for the Risk engine."""

from __future__ import annotations

import pytest

from alphadex.marketdata.normalize import (
    METRIC_FDV_USD,
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
)
from alphadex.risk import factors
from alphadex.risk.config import RiskConfig
from alphadex.risk.score import BAND_UNKNOWN, evaluate


def _cfg(**o: object) -> RiskConfig:
    base = dict(
        scope="all",
        ref_turnover=0.10,
        ref_volatility=0.50,
        ref_market_cap=1e10,
        weight_liquidity=0.30,
        weight_volatility=0.30,
        weight_dilution=0.20,
        weight_size=0.20,
        band_moderate=0.25,
        band_elevated=0.50,
        band_high=0.75,
    )
    base.update(o)
    return RiskConfig(**base)  # type: ignore[arg-type]


def test_config_validation() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        _cfg(weight_liquidity=0.5)
    with pytest.raises(ValueError, match="bands"):
        _cfg(band_moderate=0.6)


def test_liquidity_risk_low_turnover_is_high_risk() -> None:
    v = {METRIC_TOTAL_VOLUME_USD: 1e7, METRIC_MARKET_CAP_USD: 1e9}  # turnover 0.01
    assert factors.liquidity_risk(v, _cfg()) == pytest.approx(0.9)


def test_missing_factors_are_none_not_zero() -> None:
    cfg = _cfg()
    assert factors.liquidity_risk({}, cfg) is None
    assert factors.volatility_risk({}, cfg) is None
    assert factors.dilution_risk({}) is None
    assert factors.size_risk({}, cfg) is None


def test_concentration_always_unavailable() -> None:
    assert factors.concentration_risk({METRIC_MARKET_CAP_USD: 1e9}) is None


def test_score_and_band_and_data_quality() -> None:
    v = {
        METRIC_TOTAL_VOLUME_USD: 1e7,
        METRIC_MARKET_CAP_USD: 1e9,
        METRIC_FDV_USD: 2e9,  # float 0.5 → dilution risk 0.5
        METRIC_PRICE_CHANGE_PCT_30D: 60.0,  # volatility 1.0
    }
    out = evaluate(v, _cfg())
    assert out.risk_score is not None
    assert out.risk_band in ("elevated", "high")
    # concentration missing → 4/5 factors → data_quality 0.8, separate from score.
    assert out.data_quality == pytest.approx(0.8)
    assert out.concentration_risk is None


def test_all_missing_is_unknown_null_not_zero() -> None:
    out = evaluate({}, _cfg())
    assert out.risk_score is None
    assert out.risk_band == BAND_UNKNOWN
    assert out.data_quality == 0.0


def test_missing_factor_does_not_create_false_low_risk() -> None:
    # Only a high-volatility factor present → score reflects it (renormalized),
    # NOT diluted toward 0 by absent factors.
    v = {METRIC_PRICE_CHANGE_PCT_30D: 60.0}  # volatility risk clamps to 1.0
    out = evaluate(v, _cfg())
    assert out.risk_score == pytest.approx(1.0)
    assert out.risk_band == "high"
