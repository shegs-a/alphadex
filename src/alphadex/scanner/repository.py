"""Data access for the scanner: load scan inputs and read scan results.

The loader reads the latest value of each needed metric per asset (a query over the
append-only history, ADR-004). Read queries back the ``/opportunities`` and
``/scans`` endpoints. Portable across SQLite and PostgreSQL.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from alphadex.fundamentals.normalize import METRIC_FEES_30D_USD
from alphadex.marketdata.normalize import (
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
)
from alphadex.models import Asset, MetricObservation, ScanResult, ScanRun
from alphadex.scanner.inputs import AssetSnapshot, ObsValue

# The exact metrics the screen consumes.
_SCAN_METRICS = (
    METRIC_MARKET_CAP_USD,
    METRIC_TOTAL_VOLUME_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_FEES_30D_USD,
)


def load_snapshots(session: Session) -> list[AssetSnapshot]:
    """Build an ``AssetSnapshot`` for every asset from its latest observations."""
    latest = (
        select(
            MetricObservation.asset_id.label("asset_id"),
            MetricObservation.metric.label("metric"),
            func.max(MetricObservation.observed_at).label("max_observed"),
        )
        .where(MetricObservation.metric.in_(_SCAN_METRICS))
        .group_by(MetricObservation.asset_id, MetricObservation.metric)
        .subquery()
    )
    stmt = select(MetricObservation).join(
        latest,
        (MetricObservation.asset_id == latest.c.asset_id)
        & (MetricObservation.metric == latest.c.metric)
        & (MetricObservation.observed_at == latest.c.max_observed),
    )

    by_asset: dict[int, dict[str, ObsValue]] = {}
    for obs in session.execute(stmt).scalars().all():
        by_asset.setdefault(obs.asset_id, {})[obs.metric] = ObsValue(
            value=float(obs.value) if obs.value is not None else None,
            status=obs.value_status.value,
            observed_at=obs.observed_at,
        )

    # Every asset is scanned, even those with no observations yet.
    asset_ids = session.execute(select(Asset.id)).scalars().all()
    snapshots: list[AssetSnapshot] = []
    for asset_id in asset_ids:
        metrics = by_asset.get(asset_id, {})
        snapshots.append(
            AssetSnapshot(
                asset_id=asset_id,
                market_cap=metrics.get(METRIC_MARKET_CAP_USD, ObsValue.missing()),
                volume_24h=metrics.get(METRIC_TOTAL_VOLUME_USD, ObsValue.missing()),
                price_change_30d=metrics.get(
                    METRIC_PRICE_CHANGE_PCT_30D, ObsValue.missing()
                ),
                fees_30d=metrics.get(METRIC_FEES_30D_USD, ObsValue.missing()),
            )
        )
    return snapshots


def get_latest_scan_run(session: Session) -> ScanRun | None:
    """Return the most recent successful scan run, or ``None``."""
    stmt = (
        select(ScanRun)
        .where(ScanRun.status == "success")
        .order_by(ScanRun.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def list_scan_runs(session: Session, *, limit: int = 20) -> list[ScanRun]:
    stmt = select(ScanRun).order_by(ScanRun.id.desc()).limit(limit)
    return list(session.execute(stmt).scalars().all())


def get_results(
    session: Session,
    scan_run_id: int,
    *,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[ScanResult]:
    """Ranked results for a scan (ranked first, then unranked), with the asset."""
    stmt = (
        select(ScanResult)
        .options(selectinload(ScanResult.asset))
        .where(ScanResult.scan_run_id == scan_run_id)
    )
    if status is not None:
        stmt = stmt.where(ScanResult.status == status)
    stmt = (
        stmt.order_by(ScanResult.rank.is_(None), ScanResult.rank, ScanResult.asset_id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars().all())


def get_latest_result_for_asset(session: Session, asset_id: int) -> ScanResult | None:
    """The asset's result from the most recent scan run, or ``None``."""
    latest = get_latest_scan_run(session)
    if latest is None:
        return None
    stmt = (
        select(ScanResult)
        .options(selectinload(ScanResult.asset))
        .where(
            ScanResult.scan_run_id == latest.id,
            ScanResult.asset_id == asset_id,
        )
    )
    return session.execute(stmt).scalar_one_or_none()
