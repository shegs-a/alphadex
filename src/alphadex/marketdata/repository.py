"""Read queries for assets and market observations.

Kept separate from the ingestion service so the read API never depends on
provider or write logic. Queries are portable across SQLite and PostgreSQL
(no dialect-specific constructs).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from alphadex.models import Asset, MetricObservation

# All market metrics share this namespace prefix (kept distinct from fundamentals).
MARKET_PREFIX = "market."


def list_assets(session: Session, *, limit: int = 100, offset: int = 0) -> list[Asset]:
    """Return a page of assets ordered by id, with their source-id mappings."""
    stmt = (
        select(Asset)
        .options(selectinload(Asset.source_ids))
        .order_by(Asset.id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars().all())


def get_asset(session: Session, asset_id: int) -> Asset | None:
    """Return one asset by id (with source ids), or ``None`` if not found."""
    stmt = (
        select(Asset)
        .options(selectinload(Asset.source_ids))
        .where(Asset.id == asset_id)
    )
    return session.execute(stmt).scalar_one_or_none()


def latest_observations(
    session: Session,
    *,
    asset_id: int | None = None,
    metric: str | None = None,
) -> list[MetricObservation]:
    """Return the most recent observation for each (asset, metric, period).

    "Current value" is a query over the append-only history (ADR-004), not a
    stored field. Filters by asset and/or metric when provided.
    """
    # Latest observed_at per (asset, metric, period), scoped to market metrics.
    latest = (
        select(
            MetricObservation.asset_id.label("asset_id"),
            MetricObservation.metric.label("metric"),
            MetricObservation.period.label("period"),
            func.max(MetricObservation.observed_at).label("max_observed"),
        )
        .where(MetricObservation.metric.like(f"{MARKET_PREFIX}%"))
        .group_by(
            MetricObservation.asset_id,
            MetricObservation.metric,
            MetricObservation.period,
        )
    )
    if asset_id is not None:
        latest = latest.where(MetricObservation.asset_id == asset_id)
    if metric is not None:
        latest = latest.where(MetricObservation.metric == metric)
    latest_sq = latest.subquery()

    stmt = (
        select(MetricObservation)
        .join(
            latest_sq,
            (MetricObservation.asset_id == latest_sq.c.asset_id)
            & (MetricObservation.metric == latest_sq.c.metric)
            & (MetricObservation.period == latest_sq.c.period)
            & (MetricObservation.observed_at == latest_sq.c.max_observed),
        )
        .order_by(MetricObservation.asset_id, MetricObservation.metric)
    )
    return list(session.execute(stmt).scalars().all())
