"""Valuation multiples — pure functions over an asset's latest values.

Each returns a multiple **or ``None``** when the required inputs are missing or a
denominator is non-positive (explicit missing-data / undefined, never ``0`` — ADR-003).
The four multiples measure **distinct** economic relationships and are never collapsed
into one (§9):

- ``price_to_fees`` — market cap vs annualized **fees** (gross economic throughput),
- ``price_to_revenue`` — market cap vs annualized **revenue** (the protocol's take),
- ``price_to_holders_revenue`` — market cap vs annualized **holders revenue** (accrual
  to token holders),
- ``mcap_to_tvl`` — market cap vs **TVL** (capital efficiency / deposit multiple).

Market cap (circulating) is the numerator; dilution is a **separate** concern owned by
the Tokenomics engine. A multiple is a *relative* magnitude, not a fair-value verdict.
"""

from __future__ import annotations

from collections.abc import Mapping

from alphadex.fundamentals.normalize import (
    METRIC_FEES_30D_USD,
    METRIC_HOLDERS_REVENUE_30D_USD,
    METRIC_REVENUE_30D_USD,
    METRIC_TVL_USD,
)
from alphadex.marketdata.normalize import METRIC_MARKET_CAP_USD

_DAYS_PER_YEAR = 365.0

Values = Mapping[str, float]


def _annualized_30d(value: float) -> float:
    return value * (_DAYS_PER_YEAR / 30.0)


def _multiple(numerator: float | None, denominator: float | None) -> float | None:
    """market cap / annualized-flow, or ``None`` when undefined (never a false 0)."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def price_to_fees(values: Values) -> float | None:
    """Market cap / annualized fees — cheapness vs gross economic throughput."""
    fees = values.get(METRIC_FEES_30D_USD)
    mc = values.get(METRIC_MARKET_CAP_USD)
    return _multiple(mc, _annualized_30d(fees) if fees is not None else None)


def price_to_revenue(values: Values) -> float | None:
    """Market cap / annualized revenue — cheapness vs the protocol's take (§9)."""
    rev = values.get(METRIC_REVENUE_30D_USD)
    mc = values.get(METRIC_MARKET_CAP_USD)
    return _multiple(mc, _annualized_30d(rev) if rev is not None else None)


def price_to_holders_revenue(values: Values) -> float | None:
    """Market cap / annualized holders revenue — cheapness vs holder accrual (§9)."""
    hr = values.get(METRIC_HOLDERS_REVENUE_30D_USD)
    mc = values.get(METRIC_MARKET_CAP_USD)
    return _multiple(mc, _annualized_30d(hr) if hr is not None else None)


def mcap_to_tvl(values: Values) -> float | None:
    """Market cap / TVL — cheapness vs capital locked (a deposit multiple)."""
    tvl = values.get(METRIC_TVL_USD)
    mc = values.get(METRIC_MARKET_CAP_USD)
    return _multiple(mc, tvl)
