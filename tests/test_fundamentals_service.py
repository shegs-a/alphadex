"""Integration tests for the fundamentals ingestion service (SQLite).

Exercises gecko_id matching to existing assets, skipping of unmatched protocols
(Phase 1), source-id attach + category enrichment, per-protocol failure isolation,
and the ingestion-run record. The provider is a deterministic in-memory fake.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alphadex.fundamentals import service as service_module
from alphadex.fundamentals.service import FundamentalDataService
from alphadex.models import (
    Asset,
    AssetSourceId,
    IngestionRun,
    MetricObservation,
    ValueStatus,
)
from alphadex.providers.base import FundamentalDataProvider, ProviderUnavailable
from alphadex.providers.base import RawFundamentalSnapshot as Snap

_METRICS_PER_SNAPSHOT = 9


def _snap(slug: str, gecko_id: str | None, **overrides: object) -> Snap:
    base = dict(
        slug=slug,
        name=slug.title(),
        gecko_id=gecko_id,
        symbol="SYM",
        category="Dexes",
        observed_at=None,
        tvl_usd=1000.0,
        fees_24h_usd=10.0,
        fees_7d_usd=70.0,
        fees_30d_usd=300.0,
        revenue_24h_usd=None,  # missing → NOT_AVAILABLE
        revenue_7d_usd=None,
        revenue_30d_usd=None,
        holders_revenue_24h_usd=None,
        holders_revenue_30d_usd=None,
    )
    base.update(overrides)
    return Snap(**base)  # type: ignore[arg-type]


class FakeProvider(FundamentalDataProvider):
    name = "defillama"

    def __init__(self, snapshots: Sequence[Snap]) -> None:
        self._snapshots = list(snapshots)

    def fetch_fundamentals(self) -> list[Snap]:
        return list(self._snapshots)


class FailingProvider(FundamentalDataProvider):
    name = "defillama"

    def fetch_fundamentals(self) -> list[Snap]:
        raise ProviderUnavailable("down")


def _seed_asset(
    session: Session, *, gecko_id: str, category: str | None = None
) -> Asset:
    asset = Asset(symbol=gecko_id[:6].upper(), name=gecko_id.title(), category=category)
    session.add(asset)
    session.flush()
    session.add(
        AssetSourceId(asset_id=asset.id, provider="coingecko", external_id=gecko_id)
    )
    session.flush()
    return asset


def test_matches_by_gecko_id_and_writes_fundamentals(session: Session) -> None:
    asset = _seed_asset(session, gecko_id="uniswap")
    provider = FakeProvider([_snap("uniswap", "uniswap")])

    summary = FundamentalDataService(provider, session).ingest()

    assert summary.status == "success"
    assert summary.assets_ok == 1
    assert summary.assets_skipped == 0
    assert summary.observations_written == _METRICS_PER_SNAPSHOT

    # A defillama source id is attached to the SAME asset.
    src = session.execute(
        select(AssetSourceId).where(AssetSourceId.provider == "defillama")
    ).scalar_one()
    assert src.asset_id == asset.id
    assert src.external_id == "uniswap"
    # No new asset was created.
    assert session.execute(select(func.count()).select_from(Asset)).scalar_one() == 1


def test_unmatched_protocol_is_skipped_not_created(session: Session) -> None:
    _seed_asset(session, gecko_id="uniswap")
    provider = FakeProvider(
        [_snap("uniswap", "uniswap"), _snap("unknowndex", "unknown-coin")]
    )

    summary = FundamentalDataService(provider, session).ingest()

    assert summary.assets_ok == 1
    assert summary.assets_skipped == 1
    # The unmatched protocol did not create an asset.
    assert session.execute(select(func.count()).select_from(Asset)).scalar_one() == 1


def test_missing_revenue_is_explicit_not_zero(session: Session) -> None:
    _seed_asset(session, gecko_id="uniswap")
    FundamentalDataService(
        FakeProvider([_snap("uniswap", "uniswap")]), session
    ).ingest()

    rev = session.execute(
        select(MetricObservation).where(
            MetricObservation.metric == "fundamental.revenue_usd.24h"
        )
    ).scalar_one()
    assert rev.value is None
    assert rev.value_status is ValueStatus.NOT_AVAILABLE


def test_category_enrichment_fills_only_when_absent(session: Session) -> None:
    _seed_asset(session, gecko_id="uniswap", category=None)
    _seed_asset(session, gecko_id="aave", category="Existing")
    provider = FakeProvider(
        [
            _snap("uniswap", "uniswap", category="Dexes"),
            _snap("aave", "aave", category="Lending"),
        ]
    )
    FundamentalDataService(provider, session).ingest()

    uni = session.execute(select(Asset).where(Asset.name == "Uniswap")).scalar_one()
    aave = session.execute(select(Asset).where(Asset.name == "Aave")).scalar_one()
    assert uni.category == "Dexes"  # filled
    assert aave.category == "Existing"  # not overwritten


def test_reingest_is_append_only_and_idempotent_source_id(session: Session) -> None:
    _seed_asset(session, gecko_id="uniswap")
    svc = FundamentalDataService(FakeProvider([_snap("uniswap", "uniswap")]), session)
    svc.ingest()
    svc.ingest()

    # source id attached once, observations accumulate as history.
    assert (
        session.execute(
            select(func.count())
            .select_from(AssetSourceId)
            .where(AssetSourceId.provider == "defillama")
        ).scalar_one()
        == 1
    )
    assert (
        session.execute(
            select(func.count()).select_from(MetricObservation)
        ).scalar_one()
        == 2 * _METRICS_PER_SNAPSHOT
    )


def test_per_protocol_failure_is_isolated(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_asset(session, gecko_id="uniswap")
    _seed_asset(session, gecko_id="aave")
    provider = FakeProvider([_snap("uniswap", "uniswap"), _snap("boom", "aave")])

    real = service_module.normalize_snapshot

    def flaky(snapshot: Snap, **kwargs: object):  # type: ignore[no-untyped-def]
        if snapshot.slug == "boom":
            raise RuntimeError("boom")
        return real(snapshot, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service_module, "normalize_snapshot", flaky)

    summary = FundamentalDataService(provider, session).ingest()

    assert summary.status == "partial"
    assert summary.assets_ok == 1
    assert summary.assets_failed == 1
    # Only the good protocol's observations and its defillama source id remain.
    assert (
        session.execute(
            select(func.count()).select_from(MetricObservation)
        ).scalar_one()
        == _METRICS_PER_SNAPSHOT
    )
    assert (
        session.execute(
            select(func.count())
            .select_from(AssetSourceId)
            .where(AssetSourceId.provider == "defillama")
        ).scalar_one()
        == 1
    )


def test_provider_failure_records_failed_run(session: Session) -> None:
    summary = FundamentalDataService(FailingProvider(), session).ingest()
    assert summary.status == "failed"
    assert summary.error is not None
    run = session.execute(select(IngestionRun)).scalar_one()
    assert run.status == "failed"
    assert run.finished_at is not None
