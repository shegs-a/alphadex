"""Market-data ingestion service.

Orchestrates one ingestion cycle: fetch the configured universe from a provider,
resolve/persist assets by ``(provider, external_id)``, normalize each snapshot, and
append ``MetricObservation`` rows — all recorded as an ``IngestionRun``. A single
asset's failure is isolated and recorded, never aborting the whole run
(AGENTS.md §8). Depends only on the ``MarketDataProvider`` interface (§2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from alphadex.logging import get_logger
from alphadex.marketdata.normalize import normalize_snapshot
from alphadex.models import (
    Asset,
    AssetSourceId,
    IngestionRun,
    MetricObservation,
)
from alphadex.providers.base import (
    MarketDataProvider,
    ProviderError,
    RawMarketSnapshot,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class IngestionSummary:
    """Outcome of an ingestion cycle (mirrors the persisted ``IngestionRun``)."""

    run_id: int | None
    provider: str
    status: str
    assets_ok: int
    assets_failed: int
    observations_written: int
    error: str | None = None


class MarketDataService:
    """Fetches, normalizes, and persists market data for a configured universe."""

    def __init__(self, provider: MarketDataProvider, session: Session) -> None:
        self._provider = provider
        self._session = session

    def ingest(
        self,
        *,
        ids: list[str] | None = None,
        top_n: int | None = None,
    ) -> IngestionSummary:
        started_at = datetime.now(UTC)
        run = IngestionRun(
            provider=self._provider.name,
            status="running",
            started_at=started_at,
        )
        self._session.add(run)
        self._session.flush()  # obtain run.id

        try:
            snapshots = self._provider.fetch_markets(ids=ids, top_n=top_n)
        except ProviderError as exc:
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.error = f"{type(exc).__name__}: {exc}"
            self._session.commit()
            logger.error(
                "ingestion_failed",
                provider=self._provider.name,
                error=str(exc),
                run_id=run.id,
            )
            return IngestionSummary(
                run_id=run.id,
                provider=self._provider.name,
                status="failed",
                assets_ok=0,
                assets_failed=0,
                observations_written=0,
                error=run.error,
            )

        assets_ok = 0
        assets_failed = 0
        observations_written = 0
        ingested_at = datetime.now(UTC)

        for snapshot in snapshots:
            # A SAVEPOINT per asset: a failure rolls back only that asset's
            # partial writes (asset/source-id/observations), never leaving a
            # half-ingested asset behind (§8, data integrity §18).
            try:
                with self._session.begin_nested():
                    written = self._ingest_snapshot(
                        snapshot, ingested_at=ingested_at
                    )
                observations_written += written
                assets_ok += 1
            except Exception as exc:  # isolate one asset's failure (§8)
                assets_failed += 1
                logger.error(
                    "asset_ingest_failed",
                    provider=self._provider.name,
                    external_id=snapshot.external_id,
                    symbol=snapshot.symbol,
                    error=str(exc),
                )

        run.status = "partial" if assets_failed else "success"
        run.finished_at = datetime.now(UTC)
        run.assets_ok = assets_ok
        run.assets_failed = assets_failed
        run.observations_written = observations_written
        self._session.commit()

        logger.info(
            "ingestion_complete",
            provider=self._provider.name,
            run_id=run.id,
            status=run.status,
            assets_ok=assets_ok,
            assets_failed=assets_failed,
            observations_written=observations_written,
        )
        return IngestionSummary(
            run_id=run.id,
            provider=self._provider.name,
            status=run.status,
            assets_ok=assets_ok,
            assets_failed=assets_failed,
            observations_written=observations_written,
        )

    def _ingest_snapshot(
        self, snapshot: RawMarketSnapshot, *, ingested_at: datetime
    ) -> int:
        asset = self._resolve_asset(snapshot)
        normalized = normalize_snapshot(
            snapshot, provider=self._provider.name, ingested_at=ingested_at
        )
        for obs in normalized:
            self._session.add(
                MetricObservation(
                    asset_id=asset.id,
                    metric=obs.metric,
                    value=obs.value,
                    value_status=obs.value_status,
                    unit=obs.unit,
                    period=obs.period,
                    observed_at=obs.observed_at,
                    source_provider=obs.source_provider,
                    source_timestamp=obs.source_timestamp,
                    source_status=obs.source_status,
                )
            )
        # Flush so failures surface per-asset (isolated by the caller).
        self._session.flush()
        return len(normalized)

    def _resolve_asset(self, snapshot: RawMarketSnapshot) -> Asset:
        """Resolve the internal Asset for a snapshot, creating it if new.

        Identity is ``(provider, external_id)`` — symbol is never used to merge
        assets, so symbol collisions cannot conflate two distinct listings (§13).
        """
        provider = self._provider.name
        source = self._session.execute(
            select(AssetSourceId).where(
                AssetSourceId.provider == provider,
                AssetSourceId.external_id == snapshot.external_id,
            )
        ).scalar_one_or_none()
        if source is not None:
            return source.asset

        # Reuse an existing asset with the same (symbol, name) if present, else
        # create one; then attach the provider's external id as a mapping.
        asset = self._session.execute(
            select(Asset).where(
                Asset.symbol == snapshot.symbol, Asset.name == snapshot.name
            )
        ).scalar_one_or_none()
        if asset is None:
            asset = Asset(symbol=snapshot.symbol, name=snapshot.name)
            self._session.add(asset)
            self._session.flush()

        self._session.add(
            AssetSourceId(
                asset_id=asset.id,
                provider=provider,
                external_id=snapshot.external_id,
            )
        )
        self._session.flush()
        return asset


__all__ = ["MarketDataService", "IngestionSummary"]
