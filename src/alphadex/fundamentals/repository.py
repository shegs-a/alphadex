"""Read queries for fundamental observations.

Separate from ingestion so the read API never depends on provider or write logic.
Queries are portable across SQLite and PostgreSQL.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alphadex.models import MetricObservation

# All fundamentals metrics share this namespace prefix.
FUNDAMENTAL_PREFIX = "fundamental."


def latest_fundamentals(
    session: Session,
    *,
    asset_id: int | None = None,
    metric: str | None = None,
) -> list[MetricObservation]:
    """Return the most recent ``fundamental.*`` observation per (asset, metric, period).

    "Current value" is a query over the append-only history (ADR-004). Filters by
    asset and/or an exact metric when provided.
    """
    latest = (
        select(
            MetricObservation.asset_id.label("asset_id"),
            MetricObservation.metric.label("metric"),
            MetricObservation.period.label("period"),
            func.max(MetricObservation.observed_at).label("max_observed"),
        )
        .where(MetricObservation.metric.like(f"{FUNDAMENTAL_PREFIX}%"))
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
