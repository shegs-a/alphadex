"""Data access for the Divergence Engine.

Loads the observation history each asset needs (present values only, ordered by
``observed_at`` — ADR-004), selects the analysis set (the Scanner's candidates or
all assets), and reads back divergence runs and signals for the API.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from alphadex.divergence.inputs import AssetSeries, ObsPoint
from alphadex.fundamentals.normalize import (
    METRIC_FEES_7D_USD,
    METRIC_FEES_30D_USD,
    METRIC_TVL_USD,
)
from alphadex.marketdata.normalize import (
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_PRICE_USD,
)
from alphadex.models import (
    Asset,
    DivergenceRun,
    DivergenceSignal,
    MetricObservation,
    ScanResult,
    ScanRun,
    ValueStatus,
)

# The metrics the engine reads.
DIVERGENCE_METRICS = (
    METRIC_FEES_7D_USD,
    METRIC_FEES_30D_USD,
    METRIC_TVL_USD,
    METRIC_PRICE_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_MARKET_CAP_USD,
)

# Scanner classifications that pass into deeper analysis (tiered pipeline, §9).
_ANALYZED_SCAN_STATUSES = ("candidate", "watch")


def select_asset_ids(session: Session, *, scope: str) -> list[int]:
    """Choose the assets to analyze: latest scan's candidates+watch, or all."""
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


def load_series(session: Session, asset_ids: list[int]) -> dict[int, AssetSeries]:
    """Load present-valued observation history for the given assets and metrics."""
    if not asset_ids:
        return {}
    stmt = (
        select(MetricObservation)
        .where(
            MetricObservation.asset_id.in_(asset_ids),
            MetricObservation.metric.in_(DIVERGENCE_METRICS),
            MetricObservation.value_status == ValueStatus.OK,
        )
        .order_by(MetricObservation.asset_id, MetricObservation.observed_at)
    )
    out: dict[int, AssetSeries] = {aid: AssetSeries(asset_id=aid) for aid in asset_ids}
    for obs in session.execute(stmt).scalars():
        if obs.value is None:  # defensive; OK rows always have a value
            continue
        out[obs.asset_id].series.setdefault(obs.metric, []).append(
            ObsPoint(observed_at=obs.observed_at, value=float(obs.value))
        )
    return out


def get_latest_divergence_run(session: Session) -> DivergenceRun | None:
    return session.execute(
        select(DivergenceRun)
        .where(DivergenceRun.status == "success")
        .order_by(DivergenceRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def list_divergence_runs(session: Session, *, limit: int = 20) -> list[DivergenceRun]:
    return list(
        session.execute(
            select(DivergenceRun).order_by(DivergenceRun.id.desc()).limit(limit)
        ).scalars()
    )


def get_signals(
    session: Session,
    run_id: int,
    *,
    classification: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[DivergenceSignal]:
    stmt = (
        select(DivergenceSignal)
        .options(selectinload(DivergenceSignal.asset))
        .where(DivergenceSignal.divergence_run_id == run_id)
    )
    if classification is not None:
        stmt = stmt.where(DivergenceSignal.classification == classification)
    stmt = (
        stmt.order_by(
            DivergenceSignal.rank.is_(None),
            DivergenceSignal.rank,
            DivergenceSignal.asset_id,
        )
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars())


def get_latest_signal_for_asset(
    session: Session, asset_id: int
) -> DivergenceSignal | None:
    latest = get_latest_divergence_run(session)
    if latest is None:
        return None
    return session.execute(
        select(DivergenceSignal)
        .options(selectinload(DivergenceSignal.asset))
        .where(
            DivergenceSignal.divergence_run_id == latest.id,
            DivergenceSignal.asset_id == asset_id,
        )
    ).scalar_one_or_none()
