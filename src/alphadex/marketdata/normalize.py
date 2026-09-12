"""Normalize raw provider snapshots into internal metric observations.

This is the raw→normalized boundary (AGENTS.md §2). It maps each provider-agnostic
snapshot field to a well-defined internal metric name, unit, and period, and — most
importantly — records absent values as an explicit ``ValueStatus`` (never ``0``,
ADR-003). Market metrics only; fundamentals (Fees/Revenue) are a different module
and must not be conflated (AGENTS.md §9).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from alphadex.models import ValueStatus
from alphadex.providers.base import RawMarketSnapshot

# Internal metric namespace for market data. Keep names stable — later modules
# (scoring, divergence) reference them.
METRIC_PRICE_USD = "market.price_usd"
METRIC_MARKET_CAP_USD = "market.market_cap_usd"
METRIC_FDV_USD = "market.fully_diluted_valuation_usd"
METRIC_TOTAL_VOLUME_USD = "market.total_volume_usd"
METRIC_CIRCULATING_SUPPLY = "market.circulating_supply"
METRIC_TOTAL_SUPPLY = "market.total_supply"
METRIC_MAX_SUPPLY = "market.max_supply"
METRIC_PRICE_CHANGE_PCT_24H = "market.price_change_pct_24h"
METRIC_PRICE_CHANGE_PCT_7D = "market.price_change_pct_7d"
METRIC_PRICE_CHANGE_PCT_30D = "market.price_change_pct_30d"
METRIC_MARKET_CAP_RANK = "market.market_cap_rank"

_UNIT_USD = "USD"
_UNIT_TOKENS = "tokens"
_UNIT_PERCENT = "percent"
_UNIT_RANK = "rank"

_PERIOD_POINT = "point"
_PERIOD_24H = "24h"
_PERIOD_7D = "7d"
_PERIOD_30D = "30d"

# (metric name, snapshot attribute, unit, period)
_SPEC: tuple[tuple[str, str, str, str], ...] = (
    (METRIC_PRICE_USD, "price_usd", _UNIT_USD, _PERIOD_POINT),
    (METRIC_MARKET_CAP_USD, "market_cap_usd", _UNIT_USD, _PERIOD_POINT),
    (METRIC_FDV_USD, "fully_diluted_valuation_usd", _UNIT_USD, _PERIOD_POINT),
    (METRIC_TOTAL_VOLUME_USD, "total_volume_usd", _UNIT_USD, _PERIOD_24H),
    (METRIC_CIRCULATING_SUPPLY, "circulating_supply", _UNIT_TOKENS, _PERIOD_POINT),
    (METRIC_TOTAL_SUPPLY, "total_supply", _UNIT_TOKENS, _PERIOD_POINT),
    (METRIC_MAX_SUPPLY, "max_supply", _UNIT_TOKENS, _PERIOD_POINT),
    (METRIC_PRICE_CHANGE_PCT_24H, "price_change_pct_24h", _UNIT_PERCENT, _PERIOD_24H),
    (METRIC_PRICE_CHANGE_PCT_7D, "price_change_pct_7d", _UNIT_PERCENT, _PERIOD_7D),
    (METRIC_PRICE_CHANGE_PCT_30D, "price_change_pct_30d", _UNIT_PERCENT, _PERIOD_30D),
    (METRIC_MARKET_CAP_RANK, "market_cap_rank", _UNIT_RANK, _PERIOD_POINT),
)


@dataclass(frozen=True)
class NormalizedObservation:
    """A provider-agnostic observation ready to persist as a ``MetricObservation``.

    ``asset_id`` is attached by the persistence layer; identity resolution is not
    normalization's concern.
    """

    metric: str
    value: float | None
    value_status: ValueStatus
    unit: str
    period: str
    observed_at: datetime
    source_provider: str
    source_timestamp: datetime | None
    source_status: str


def normalize_snapshot(
    snapshot: RawMarketSnapshot,
    *,
    provider: str,
    ingested_at: datetime,
) -> list[NormalizedObservation]:
    """Convert one snapshot into a list of normalized observations.

    A present value yields ``ValueStatus.OK``; an absent (``None``) value yields
    ``ValueStatus.NOT_AVAILABLE`` with a ``None`` value — never ``0``. ``observed_at``
    is the provider timestamp when available, else the ingestion time.
    """
    observed_at = snapshot.observed_at or ingested_at
    source_status = "ok" if snapshot.observed_at is not None else "no_timestamp"

    observations: list[NormalizedObservation] = []
    for metric, attr, unit, period in _SPEC:
        value = getattr(snapshot, attr)
        if value is None:
            status = ValueStatus.NOT_AVAILABLE
        else:
            status = ValueStatus.OK
        observations.append(
            NormalizedObservation(
                metric=metric,
                value=value,
                value_status=status,
                unit=unit,
                period=period,
                observed_at=observed_at,
                source_provider=provider,
                source_timestamp=snapshot.observed_at,
                source_status=source_status,
            )
        )
    return observations
