"""Fundamentals ingestion service.

Fetches protocol fundamentals, matches each protocol to an asset **already in the
universe** by ``gecko_id`` (Phase 1 — see docs/sprints/sprint-03-plan.md), attaches
a provider source id to that same asset, normalizes, and appends distinct
``fundamental.*`` observations. Protocols with no matching in-universe asset are
skipped and counted (tiered processing, §9). Reuses the Sprint 02 ingestion
infrastructure: per-asset SAVEPOINT isolation and an ``ingestion_runs`` record.
Depends only on the ``FundamentalDataProvider`` interface (§2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from alphadex.fundamentals.normalize import normalize_snapshot
from alphadex.logging import get_logger
from alphadex.models import (
    Asset,
    AssetSourceId,
    IngestionRun,
    MetricObservation,
)
from alphadex.providers.base import (
    FundamentalDataProvider,
    ProviderError,
    RawFundamentalSnapshot,
)

logger = get_logger(__name__)

# gecko_id is inherently a CoinGecko concept; match against that provider's ids.
_MATCH_PROVIDER = "coingecko"


@dataclass(frozen=True)
class FundamentalsSummary:
    """Outcome of a fundamentals ingestion cycle."""

    run_id: int | None
    provider: str
    status: str
    assets_ok: int
    assets_failed: int
    assets_skipped: int
    observations_written: int
    error: str | None = None


class FundamentalDataService:
    """Fetches, matches, normalizes, and persists protocol fundamentals."""

    def __init__(
        self,
        provider: FundamentalDataProvider,
        session: Session,
        *,
        match_provider: str = _MATCH_PROVIDER,
    ) -> None:
        self._provider = provider
        self._session = session
        self._match_provider = match_provider

    def ingest(self) -> FundamentalsSummary:
        started_at = datetime.now(UTC)
        run = IngestionRun(
            provider=self._provider.name,
            status="running",
            started_at=started_at,
        )
        self._session.add(run)
        self._session.flush()

        try:
            snapshots = self._provider.fetch_fundamentals()
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
            return FundamentalsSummary(
                run_id=run.id,
                provider=self._provider.name,
                status="failed",
                assets_ok=0,
                assets_failed=0,
                assets_skipped=0,
                observations_written=0,
                error=run.error,
            )

        assets_ok = 0
        assets_failed = 0
        assets_skipped = 0
        observations_written = 0
        ingested_at = datetime.now(UTC)

        for snapshot in snapshots:
            asset = self._find_asset(snapshot)
            if asset is None:
                assets_skipped += 1
                continue
            try:
                with self._session.begin_nested():
                    written = self._write_fundamentals(
                        snapshot, asset, ingested_at=ingested_at
                    )
                observations_written += written
                assets_ok += 1
            except Exception as exc:  # isolate one protocol's failure (§8)
                assets_failed += 1
                logger.error(
                    "asset_ingest_failed",
                    provider=self._provider.name,
                    slug=snapshot.slug,
                    gecko_id=snapshot.gecko_id,
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
            assets_skipped=assets_skipped,
            observations_written=observations_written,
        )
        return FundamentalsSummary(
            run_id=run.id,
            provider=self._provider.name,
            status=run.status,
            assets_ok=assets_ok,
            assets_failed=assets_failed,
            assets_skipped=assets_skipped,
            observations_written=observations_written,
        )

    def _find_asset(self, snapshot: RawFundamentalSnapshot) -> Asset | None:
        """Match a protocol to an existing asset by gecko_id (Phase 1).

        Returns ``None`` when the protocol is not in the universe — the caller
        skips it rather than creating an asset with no market data.
        """
        if not snapshot.gecko_id:
            return None
        source = self._session.execute(
            select(AssetSourceId).where(
                AssetSourceId.provider == self._match_provider,
                AssetSourceId.external_id == snapshot.gecko_id,
            )
        ).scalar_one_or_none()
        return source.asset if source is not None else None

    def _write_fundamentals(
        self,
        snapshot: RawFundamentalSnapshot,
        asset: Asset,
        *,
        ingested_at: datetime,
    ) -> int:
        # Attach this provider's source id to the same asset (idempotent).
        existing = self._session.execute(
            select(AssetSourceId).where(
                AssetSourceId.provider == self._provider.name,
                AssetSourceId.external_id == snapshot.slug,
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(
                AssetSourceId(
                    asset_id=asset.id,
                    provider=self._provider.name,
                    external_id=snapshot.slug,
                )
            )

        # Optional enrichment: fill an unknown category, never overwrite one.
        if asset.category is None and snapshot.category:
            asset.category = snapshot.category

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
        self._session.flush()
        return len(normalized)


__all__ = ["FundamentalDataService", "FundamentalsSummary"]
