"""Integration tests for the market-data ingestion service (SQLite).

Exercises the full fetch→normalize→persist cycle against a throwaway database:
asset resolution by ``(provider, external_id)`` (symbol-collision safe), append-only
history on re-run, per-asset failure isolation, and the ingestion-run record.
The provider is a deterministic in-memory fake — no network.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alphadex.marketdata import service as service_module
from alphadex.marketdata.service import MarketDataService
from alphadex.models import (
    Asset,
    AssetSourceId,
    IngestionRun,
    MetricObservation,
    ValueStatus,
)
from alphadex.providers.base import MarketDataProvider, ProviderUnavailable
from alphadex.providers.base import RawMarketSnapshot as Snap

_OBSERVED = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
_METRICS_PER_SNAPSHOT = 11


def _snap(external_id: str, symbol: str, name: str, **overrides: object) -> Snap:
    base = dict(
        external_id=external_id,
        symbol=symbol,
        name=name,
        observed_at=_OBSERVED,
        price_usd=100.0,
        market_cap_usd=1000.0,
        fully_diluted_valuation_usd=1200.0,
        total_volume_usd=500.0,
        circulating_supply=10.0,
        total_supply=10.0,
        max_supply=None,
        price_change_pct_24h=1.0,
        price_change_pct_7d=2.0,
        price_change_pct_30d=3.0,
        market_cap_rank=1.0,
    )
    base.update(overrides)
    return Snap(**base)  # type: ignore[arg-type]


class FakeProvider(MarketDataProvider):
    name = "fake"

    def __init__(self, snapshots: Sequence[Snap]) -> None:
        self._snapshots = list(snapshots)

    def fetch_markets(
        self,
        *,
        ids: Sequence[str] | None = None,
        top_n: int | None = None,
    ) -> list[Snap]:
        return list(self._snapshots)


class FailingProvider(MarketDataProvider):
    name = "fake"

    def fetch_markets(
        self,
        *,
        ids: Sequence[str] | None = None,
        top_n: int | None = None,
    ) -> list[Snap]:
        raise ProviderUnavailable("down")


def test_ingest_creates_assets_source_ids_and_observations(session: Session) -> None:
    provider = FakeProvider(
        [_snap("bitcoin", "BTC", "Bitcoin"), _snap("ethereum", "ETH", "Ethereum")]
    )
    summary = MarketDataService(provider, session).ingest()

    assert summary.status == "success"
    assert summary.assets_ok == 2
    assert summary.assets_failed == 0
    assert summary.observations_written == 2 * _METRICS_PER_SNAPSHOT

    assert session.execute(select(func.count()).select_from(Asset)).scalar_one() == 2
    assert (
        session.execute(select(func.count()).select_from(AssetSourceId)).scalar_one()
        == 2
    )
    # The run is recorded (observability, §8).
    run = session.execute(select(IngestionRun)).scalar_one()
    assert run.status == "success"
    assert run.finished_at is not None


def test_missing_value_persisted_as_explicit_status_not_zero(session: Session) -> None:
    provider = FakeProvider([_snap("bitcoin", "BTC", "Bitcoin", max_supply=None)])
    MarketDataService(provider, session).ingest()

    row = session.execute(
        select(MetricObservation).where(MetricObservation.metric == "market.max_supply")
    ).scalar_one()
    assert row.value is None
    assert row.value_status is ValueStatus.NOT_AVAILABLE


def test_symbol_collision_does_not_merge_distinct_assets(session: Session) -> None:
    # Same symbol, different provider id and name → two distinct assets (§13).
    provider = FakeProvider(
        [_snap("foo-one", "FOO", "Foo One"), _snap("foo-two", "FOO", "Foo Two")]
    )
    MarketDataService(provider, session).ingest()

    assets = session.execute(select(Asset)).scalars().all()
    assert len(assets) == 2
    assert {a.name for a in assets} == {"Foo One", "Foo Two"}


def test_reingest_is_append_only_and_reuses_asset(session: Session) -> None:
    provider = FakeProvider([_snap("bitcoin", "BTC", "Bitcoin")])
    svc = MarketDataService(provider, session)
    svc.ingest()
    svc.ingest()

    # Asset resolved by source id, not recreated.
    assert session.execute(select(func.count()).select_from(Asset)).scalar_one() == 1
    # Observations accumulate as history (ADR-004).
    total_obs = session.execute(
        select(func.count()).select_from(MetricObservation)
    ).scalar_one()
    assert total_obs == 2 * _METRICS_PER_SNAPSHOT


def test_per_asset_failure_is_isolated(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = _snap("good", "GOOD", "Good Coin")
    poison = _snap("boom", "BOOM", "Boom Coin")
    provider = FakeProvider([good, poison])

    real_normalize = service_module.normalize_snapshot

    def flaky(snapshot: Snap, **kwargs: object):  # type: ignore[no-untyped-def]
        if snapshot.external_id == "boom":
            raise RuntimeError("boom during normalize")
        return real_normalize(snapshot, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service_module, "normalize_snapshot", flaky)

    summary = MarketDataService(provider, session).ingest()

    assert summary.status == "partial"
    assert summary.assets_ok == 1
    assert summary.assets_failed == 1
    # Only the good asset's observations were written.
    assert (
        session.execute(
            select(func.count()).select_from(MetricObservation)
        ).scalar_one()
        == _METRICS_PER_SNAPSHOT
    )
    # The failed asset was rolled back entirely — no orphan Asset/source id.
    assets = session.execute(select(Asset)).scalars().all()
    assert [a.symbol for a in assets] == ["GOOD"]
    assert (
        session.execute(select(func.count()).select_from(AssetSourceId)).scalar_one()
        == 1
    )


def test_provider_failure_records_failed_run(session: Session) -> None:
    summary = MarketDataService(FailingProvider(), session).ingest()
    assert summary.status == "failed"
    assert summary.error is not None

    run = session.execute(select(IngestionRun)).scalar_one()
    assert run.status == "failed"
    assert run.error is not None
    assert run.finished_at is not None
