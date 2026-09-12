"""Normalize raw fundamental snapshots into internal metric observations.

The raw→normalized boundary for the fundamentals domain (AGENTS.md §2). Maps each
provider-agnostic field to a distinct ``fundamental.*`` metric with unit and period,
and records absent values as an explicit ``ValueStatus`` (never ``0``, ADR-003).

Fees ≠ Revenue ≠ Holders Revenue ≠ TVL (AGENTS.md §9): these are separate metrics
here and must never be summed, averaged, or derived from one another.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from alphadex.models import ValueStatus
from alphadex.providers.base import RawFundamentalSnapshot

# Internal fundamentals metric namespace. Kept distinct from market.* metrics.
METRIC_TVL_USD = "fundamental.tvl_usd"
METRIC_FEES_24H_USD = "fundamental.fees_usd.24h"
METRIC_FEES_7D_USD = "fundamental.fees_usd.7d"
METRIC_FEES_30D_USD = "fundamental.fees_usd.30d"
METRIC_REVENUE_24H_USD = "fundamental.revenue_usd.24h"
METRIC_REVENUE_7D_USD = "fundamental.revenue_usd.7d"
METRIC_REVENUE_30D_USD = "fundamental.revenue_usd.30d"
METRIC_HOLDERS_REVENUE_24H_USD = "fundamental.holders_revenue_usd.24h"
METRIC_HOLDERS_REVENUE_30D_USD = "fundamental.holders_revenue_usd.30d"

_UNIT_USD = "USD"
_PERIOD_POINT = "point"
_PERIOD_24H = "24h"
_PERIOD_7D = "7d"
_PERIOD_30D = "30d"

# (metric name, snapshot attribute, unit, period)
_SPEC: tuple[tuple[str, str, str, str], ...] = (
    (METRIC_TVL_USD, "tvl_usd", _UNIT_USD, _PERIOD_POINT),
    (METRIC_FEES_24H_USD, "fees_24h_usd", _UNIT_USD, _PERIOD_24H),
    (METRIC_FEES_7D_USD, "fees_7d_usd", _UNIT_USD, _PERIOD_7D),
    (METRIC_FEES_30D_USD, "fees_30d_usd", _UNIT_USD, _PERIOD_30D),
    (METRIC_REVENUE_24H_USD, "revenue_24h_usd", _UNIT_USD, _PERIOD_24H),
    (METRIC_REVENUE_7D_USD, "revenue_7d_usd", _UNIT_USD, _PERIOD_7D),
    (METRIC_REVENUE_30D_USD, "revenue_30d_usd", _UNIT_USD, _PERIOD_30D),
    (
        METRIC_HOLDERS_REVENUE_24H_USD,
        "holders_revenue_24h_usd",
        _UNIT_USD,
        _PERIOD_24H,
    ),
    (
        METRIC_HOLDERS_REVENUE_30D_USD,
        "holders_revenue_30d_usd",
        _UNIT_USD,
        _PERIOD_30D,
    ),
)


@dataclass(frozen=True)
class NormalizedObservation:
    """A provider-agnostic observation ready to persist as a ``MetricObservation``."""

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
    snapshot: RawFundamentalSnapshot,
    *,
    provider: str,
    ingested_at: datetime,
) -> list[NormalizedObservation]:
    """Convert one fundamentals snapshot into normalized observations.

    A present value yields ``ValueStatus.OK``; an absent (``None``) value yields
    ``ValueStatus.NOT_AVAILABLE`` with a ``None`` value — never ``0``. DefiLlama's
    overview totals are current as of the fetch, so ``observed_at`` is the ingestion
    time and ``source_timestamp`` is the provider timestamp when supplied.
    """
    observed_at = snapshot.observed_at or ingested_at
    source_status = "ok"

    observations: list[NormalizedObservation] = []
    for metric, attr, unit, period in _SPEC:
        value = getattr(snapshot, attr)
        status = ValueStatus.OK if value is not None else ValueStatus.NOT_AVAILABLE
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
