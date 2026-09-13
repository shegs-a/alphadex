"""Data access for the Risk engine."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from alphadex.marketdata.normalize import (
    METRIC_CIRCULATING_SUPPLY,
    METRIC_FDV_USD,
    METRIC_MARKET_CAP_USD,
    METRIC_MAX_SUPPLY,
    METRIC_PRICE_CHANGE_PCT_7D,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_SUPPLY,
    METRIC_TOTAL_VOLUME_USD,
)
from alphadex.models import RiskAssessment, RiskRun

RISK_METRICS = (
    METRIC_MARKET_CAP_USD,
    METRIC_FDV_USD,
    METRIC_CIRCULATING_SUPPLY,
    METRIC_TOTAL_SUPPLY,
    METRIC_MAX_SUPPLY,
    METRIC_TOTAL_VOLUME_USD,
    METRIC_PRICE_CHANGE_PCT_7D,
    METRIC_PRICE_CHANGE_PCT_30D,
)


def get_latest_run(session: Session) -> RiskRun | None:
    return session.execute(
        select(RiskRun)
        .where(RiskRun.status == "success")
        .order_by(RiskRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def list_runs(session: Session, *, limit: int = 20) -> list[RiskRun]:
    return list(
        session.execute(
            select(RiskRun).order_by(RiskRun.id.desc()).limit(limit)
        ).scalars()
    )


def get_assessments(
    session: Session,
    run_id: int,
    *,
    band: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[RiskAssessment]:
    stmt = (
        select(RiskAssessment)
        .options(selectinload(RiskAssessment.asset))
        .where(RiskAssessment.risk_run_id == run_id)
    )
    if band is not None:
        stmt = stmt.where(RiskAssessment.risk_band == band)
    stmt = (
        stmt.order_by(
            RiskAssessment.rank.is_(None),
            RiskAssessment.rank,
            RiskAssessment.asset_id,
        )
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars())


def get_latest_assessment_for_asset(
    session: Session, asset_id: int
) -> RiskAssessment | None:
    latest = get_latest_run(session)
    if latest is None:
        return None
    return session.execute(
        select(RiskAssessment)
        .options(selectinload(RiskAssessment.asset))
        .where(
            RiskAssessment.risk_run_id == latest.id,
            RiskAssessment.asset_id == asset_id,
        )
    ).scalar_one_or_none()
