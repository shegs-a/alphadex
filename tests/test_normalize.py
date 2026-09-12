"""Normalization tests: raw snapshot → internal observations.

Asserts the raw→normalized mapping (metric name, unit, period) and the central
missing-data rule: an absent value becomes an explicit ``ValueStatus`` with a
``None`` value, never ``0`` (ADR-003).
"""

from __future__ import annotations

from datetime import UTC, datetime

from alphadex.marketdata import normalize
from alphadex.marketdata.normalize import normalize_snapshot
from alphadex.models import ValueStatus
from alphadex.providers.base import RawMarketSnapshot

_OBSERVED = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _snapshot(**overrides: object) -> RawMarketSnapshot:
    base = dict(
        external_id="bitcoin",
        symbol="BTC",
        name="Bitcoin",
        observed_at=_OBSERVED,
        price_usd=61234.5,
        market_cap_usd=1203456789012.0,
        fully_diluted_valuation_usd=1287654321098.0,
        total_volume_usd=34567890123.0,
        circulating_supply=19750000.0,
        total_supply=21000000.0,
        max_supply=21000000.0,
        price_change_pct_24h=1.23,
        price_change_pct_7d=-2.5,
        price_change_pct_30d=8.9,
        market_cap_rank=1.0,
    )
    base.update(overrides)
    return RawMarketSnapshot(**base)  # type: ignore[arg-type]


def test_maps_all_metrics_with_units_and_periods() -> None:
    obs = normalize_snapshot(_snapshot(), provider="coingecko", ingested_at=_OBSERVED)
    by_metric = {o.metric: o for o in obs}

    assert by_metric[normalize.METRIC_PRICE_USD].unit == "USD"
    assert by_metric[normalize.METRIC_PRICE_USD].period == "point"
    assert by_metric[normalize.METRIC_TOTAL_VOLUME_USD].period == "24h"
    assert by_metric[normalize.METRIC_PRICE_CHANGE_PCT_7D].unit == "percent"
    assert by_metric[normalize.METRIC_PRICE_CHANGE_PCT_7D].period == "7d"
    assert by_metric[normalize.METRIC_MARKET_CAP_RANK].unit == "rank"
    # Every mapped metric is produced.
    assert len(obs) == 11


def test_present_values_are_ok() -> None:
    obs = normalize_snapshot(_snapshot(), provider="coingecko", ingested_at=_OBSERVED)
    price = next(o for o in obs if o.metric == normalize.METRIC_PRICE_USD)
    assert price.value_status is ValueStatus.OK
    assert price.value == 61234.5
    assert price.source_provider == "coingecko"
    assert price.source_timestamp == _OBSERVED


def test_absent_value_is_explicit_not_zero() -> None:
    obs = normalize_snapshot(
        _snapshot(fully_diluted_valuation_usd=None, max_supply=None),
        provider="coingecko",
        ingested_at=_OBSERVED,
    )
    fdv = next(o for o in obs if o.metric == normalize.METRIC_FDV_USD)
    max_supply = next(o for o in obs if o.metric == normalize.METRIC_MAX_SUPPLY)

    assert fdv.value is None
    assert fdv.value_status is ValueStatus.NOT_AVAILABLE
    assert max_supply.value is None
    assert max_supply.value_status is ValueStatus.NOT_AVAILABLE


def test_missing_provider_timestamp_falls_back_to_ingested_at() -> None:
    ingested = datetime(2026, 9, 12, 13, 0, tzinfo=UTC)
    obs = normalize_snapshot(
        _snapshot(observed_at=None), provider="coingecko", ingested_at=ingested
    )
    price = next(o for o in obs if o.metric == normalize.METRIC_PRICE_USD)
    assert price.observed_at == ingested
    assert price.source_timestamp is None
    assert price.source_status == "no_timestamp"
