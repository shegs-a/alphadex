"""Normalization tests for fundamentals: raw snapshot → internal observations.

Asserts the mapping (metric name, unit, period), that Fees/Revenue/Holders-Revenue/
TVL stay distinct, and that an absent value becomes an explicit ``ValueStatus`` with
a ``None`` value — never ``0`` (ADR-003, AGENTS.md §9).
"""

from __future__ import annotations

from datetime import UTC, datetime

from alphadex.fundamentals import normalize
from alphadex.fundamentals.normalize import normalize_snapshot
from alphadex.models import ValueStatus
from alphadex.providers.base import RawFundamentalSnapshot

_INGESTED = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _snap(**overrides: object) -> RawFundamentalSnapshot:
    base = dict(
        slug="uniswap",
        name="Uniswap",
        gecko_id="uniswap",
        symbol="UNI",
        category="Dexes",
        observed_at=None,
        tvl_usd=5_000_000_000.0,
        fees_24h_usd=2_000_000.0,
        fees_7d_usd=1.4e7,
        fees_30d_usd=6e7,
        revenue_24h_usd=300_000.0,
        revenue_7d_usd=2.1e6,
        revenue_30d_usd=9e6,
        holders_revenue_24h_usd=50_000.0,
        holders_revenue_30d_usd=1.5e6,
    )
    base.update(overrides)
    return RawFundamentalSnapshot(**base)  # type: ignore[arg-type]


def test_maps_metrics_units_and_periods() -> None:
    obs = normalize_snapshot(_snap(), provider="defillama", ingested_at=_INGESTED)
    by_metric = {o.metric: o for o in obs}

    assert len(obs) == 9
    assert by_metric[normalize.METRIC_TVL_USD].unit == "USD"
    assert by_metric[normalize.METRIC_TVL_USD].period == "point"
    assert by_metric[normalize.METRIC_FEES_24H_USD].period == "24h"
    assert by_metric[normalize.METRIC_REVENUE_7D_USD].period == "7d"
    assert by_metric[normalize.METRIC_FEES_30D_USD].period == "30d"


def test_fees_revenue_and_tvl_are_distinct_metrics() -> None:
    obs = normalize_snapshot(_snap(), provider="defillama", ingested_at=_INGESTED)
    by_metric = {o.metric: o.value for o in obs}
    # Distinct metrics with distinct values — never conflated (§9).
    assert by_metric[normalize.METRIC_FEES_24H_USD] == 2_000_000.0
    assert by_metric[normalize.METRIC_REVENUE_24H_USD] == 300_000.0
    assert by_metric[normalize.METRIC_HOLDERS_REVENUE_24H_USD] == 50_000.0
    assert by_metric[normalize.METRIC_TVL_USD] == 5_000_000_000.0


def test_present_values_are_ok_with_provenance() -> None:
    obs = normalize_snapshot(_snap(), provider="defillama", ingested_at=_INGESTED)
    tvl = next(o for o in obs if o.metric == normalize.METRIC_TVL_USD)
    assert tvl.value_status is ValueStatus.OK
    assert tvl.source_provider == "defillama"
    assert tvl.observed_at == _INGESTED  # provider gave no per-metric timestamp


def test_absent_value_is_explicit_not_zero() -> None:
    obs = normalize_snapshot(
        _snap(revenue_24h_usd=None, tvl_usd=None),
        provider="defillama",
        ingested_at=_INGESTED,
    )
    rev = next(o for o in obs if o.metric == normalize.METRIC_REVENUE_24H_USD)
    tvl = next(o for o in obs if o.metric == normalize.METRIC_TVL_USD)
    assert rev.value is None
    assert rev.value_status is ValueStatus.NOT_AVAILABLE
    assert tvl.value is None
    assert tvl.value_status is ValueStatus.NOT_AVAILABLE
