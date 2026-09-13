"""Tokenomics signals — pure ratio functions over an asset's latest values.

Each returns a value **or ``None``** when the required inputs are missing (explicit
missing-data, never ``0`` — ADR-003). Fees, Revenue, and Holders Revenue are read as
distinct inputs and never collapsed (§9).
"""

from __future__ import annotations

from collections.abc import Mapping

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
    METRIC_TOTAL_SUPPLY,
)

_DAYS_PER_YEAR = 365.0

Values = Mapping[str, float]


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def float_ratio(values: Values) -> float | None:
    """Circulating value as a fraction of fully diluted value (higher = less overhang).

    Prefers ``market_cap / FDV``; falls back to ``circulating / max`` then
    ``circulating / total`` supply. ``None`` if none are available.
    """
    mc = values.get(METRIC_MARKET_CAP_USD)
    fdv = values.get(METRIC_FDV_USD)
    if mc is not None and fdv and fdv > 0:
        return _clamp(mc / fdv)
    circ = values.get(METRIC_CIRCULATING_SUPPLY)
    for denom_metric in (METRIC_MAX_SUPPLY, METRIC_TOTAL_SUPPLY):
        denom = values.get(denom_metric)
        if circ is not None and denom and denom > 0:
            return _clamp(circ / denom)
    return None


def revenue_to_fees(values: Values) -> float | None:
    """Fraction of fees the protocol keeps as revenue (Revenue ≠ Fees, §9)."""
    fees = values.get(METRIC_FEES_30D_USD)
    rev = values.get(METRIC_REVENUE_30D_USD)
    if rev is not None and fees and fees > 0:
        return _clamp(rev / fees)
    return None


def holders_to_revenue(values: Values) -> float | None:
    """Fraction of revenue routed to token holders (Holders Revenue ≠ Revenue, §9)."""
    hr = values.get(METRIC_HOLDERS_REVENUE_30D_USD)
    rev = values.get(METRIC_REVENUE_30D_USD)
    if hr is not None and rev and rev > 0:
        return _clamp(hr / rev)
    return None


def real_yield(values: Values) -> float | None:
    """Annualized holders-revenue as a fraction of market cap (a real-yield proxy)."""
    hr = values.get(METRIC_HOLDERS_REVENUE_30D_USD)
    mc = values.get(METRIC_MARKET_CAP_USD)
    if hr is not None and mc and mc > 0:
        return (hr * (_DAYS_PER_YEAR / 30.0)) / mc
    return None
