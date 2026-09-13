"""Shared analytical helpers: candidate selection and isolated per-asset runs.

Keeps the tiered-pipeline selection (§9) and the per-asset SAVEPOINT isolation (§8)
in one place so analytical engines stay small and consistent.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alphadex.logging import get_logger
from alphadex.models import Asset, MetricObservation, ScanResult, ScanRun, ValueStatus

logger = get_logger(__name__)

# Scanner classifications that pass into deeper analysis (tiered pipeline, §9).
_ANALYZED_SCAN_STATUSES = ("candidate", "watch")

T = TypeVar("T")


def select_asset_ids(session: Session, *, scope: str) -> list[int]:
    """Choose the assets to analyze: the latest scan's candidates+watch, or all.

    ``scope`` is ``"candidates"`` or ``"all"``. With no successful scan, the
    candidates scope yields an empty list (nothing has been screened yet).
    """
    if scope == "all":
        return list(session.execute(select(Asset.id).order_by(Asset.id)).scalars())

    latest_scan = session.execute(
        select(ScanRun)
        .where(ScanRun.status == "success")
        .order_by(ScanRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest_scan is None:
        return []
    stmt = (
        select(ScanResult.asset_id)
        .where(
            ScanResult.scan_run_id == latest_scan.id,
            ScanResult.status.in_(_ANALYZED_SCAN_STATUSES),
        )
        .order_by(ScanResult.asset_id)
    )
    return list(session.execute(stmt).scalars())


def load_latest_values(
    session: Session, asset_ids: Sequence[int], metrics: Sequence[str]
) -> dict[int, dict[str, float]]:
    """Latest **present** (OK) value of each metric per asset.

    Missing/non-OK observations are simply absent from the map (never ``0`` —
    ADR-003); callers must treat absence as explicit missing-data.
    """
    if not asset_ids:
        return {}
    latest = (
        select(
            MetricObservation.asset_id.label("asset_id"),
            MetricObservation.metric.label("metric"),
            func.max(MetricObservation.observed_at).label("max_observed"),
        )
        .where(
            MetricObservation.asset_id.in_(list(asset_ids)),
            MetricObservation.metric.in_(list(metrics)),
            MetricObservation.value_status == ValueStatus.OK,
        )
        .group_by(MetricObservation.asset_id, MetricObservation.metric)
        .subquery()
    )
    stmt = select(MetricObservation).join(
        latest,
        (MetricObservation.asset_id == latest.c.asset_id)
        & (MetricObservation.metric == latest.c.metric)
        & (MetricObservation.observed_at == latest.c.max_observed),
    )
    out: dict[int, dict[str, float]] = {aid: {} for aid in asset_ids}
    for obs in session.execute(stmt).scalars():
        if obs.value is not None:
            out[obs.asset_id][obs.metric] = float(obs.value)
    return out


def run_isolated(
    session: Session,
    asset_ids: Sequence[int],
    work: Callable[[int], T],
    *,
    event: str,
) -> tuple[list[tuple[int, T]], int]:
    """Run ``work(asset_id)`` for each asset in its own SAVEPOINT.

    A single asset's failure is rolled back and recorded, never aborting the run
    (§8). Returns ``(successful [(asset_id, result)], failed_count)``.
    """
    ok: list[tuple[int, T]] = []
    failed = 0
    for asset_id in asset_ids:
        try:
            with session.begin_nested():
                result = work(asset_id)
            ok.append((asset_id, result))
        except Exception as exc:  # isolate one asset's failure (§8)
            failed += 1
            logger.error(event, asset_id=asset_id, error=str(exc))
    return ok, failed
