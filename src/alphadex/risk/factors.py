"""Risk factors — pure functions, each 0..1 (higher = riskier) or ``None``.

A missing input yields ``None`` (the factor drops out and lowers data quality) —
never a false low risk (ADR-003). ``concentration_risk`` is always ``None``:
holder-concentration needs on-chain data not yet available (a surfaced data gap).
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from alphadex.marketdata.normalize import (
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_7D,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
)
from alphadex.risk.config import RiskConfig
from alphadex.tokenomics.signals import float_ratio

Values = Mapping[str, float]


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def liquidity_risk(values: Values, config: RiskConfig) -> float | None:
    """Low 24h turnover (volume / market cap) → high liquidity risk."""
    vol = values.get(METRIC_TOTAL_VOLUME_USD)
    mc = values.get(METRIC_MARKET_CAP_USD)
    if vol is None or mc is None or mc <= 0:
        return None
    turnover = vol / mc
    return _clamp(1.0 - min(1.0, turnover / config.ref_turnover))


def volatility_risk(values: Values, config: RiskConfig) -> float | None:
    """Large recent price swings (30d/7d magnitude) → high volatility risk."""
    magnitudes = [
        abs(values[m]) / 100.0
        for m in (METRIC_PRICE_CHANGE_PCT_30D, METRIC_PRICE_CHANGE_PCT_7D)
        if m in values
    ]
    if not magnitudes:
        return None
    return _clamp(max(magnitudes) / config.ref_volatility)


def dilution_risk(values: Values) -> float | None:
    """Supply overhang → high dilution risk (inverse of the float ratio)."""
    fr = float_ratio(values)
    if fr is None:
        return None
    return _clamp(1.0 - fr)


def size_risk(values: Values, config: RiskConfig) -> float | None:
    """Small market cap → high size risk (log-scaled against a reference)."""
    mc = values.get(METRIC_MARKET_CAP_USD)
    if mc is None or mc <= 0:
        return None
    norm = math.log10(1.0 + mc) / math.log10(1.0 + config.ref_market_cap)
    return _clamp(1.0 - norm)


def concentration_risk(values: Values) -> float | None:
    """Always ``None`` — holder concentration needs on-chain data (not available)."""
    return None
