"""Data access for the Valuation engine."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from alphadex.fundamentals.normalize import (
    METRIC_FEES_30D_USD,
    METRIC_HOLDERS_REVENUE_30D_USD,
    METRIC_REVENUE_30D_USD,
    METRIC_TVL_USD,
)
from alphadex.marketdata.normalize import METRIC_MARKET_CAP_USD
from alphadex.models import ValuationAssessment, ValuationRun

VALUATION_METRICS = (
    METRIC_MARKET_CAP_USD,
    METRIC_FEES_30D_USD,
    METRIC_REVENUE_30D_USD,
    METRIC_HOLDERS_REVENUE_30D_USD,
    METRIC_TVL_USD,
)


def get_latest_run(session: Session) -> ValuationRun | None:
    return session.execute(
        select(ValuationRun)
        .where(ValuationRun.status == "success")
        .order_by(ValuationRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def list_runs(session: Session, *, limit: int = 20) -> list[ValuationRun]:
    return list(
        session.execute(
            select(ValuationRun).order_by(ValuationRun.id.desc()).limit(limit)
        ).scalars()
    )


def get_assessments(
    session: Session,
    run_id: int,
    *,
    label: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[ValuationAssessment]:
    stmt = (
        select(ValuationAssessment)
        .options(selectinload(ValuationAssessment.asset))
        .where(ValuationAssessment.valuation_run_id == run_id)
    )
    if label is not None:
        stmt = stmt.where(ValuationAssessment.valuation_label == label)
    stmt = (
        stmt.order_by(
            ValuationAssessment.rank.is_(None),
            ValuationAssessment.rank,
            ValuationAssessment.asset_id,
        )
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars())


def get_latest_assessment_for_asset(
    session: Session, asset_id: int
) -> ValuationAssessment | None:
    latest = get_latest_run(session)
    if latest is None:
        return None
    return session.execute(
        select(ValuationAssessment)
        .options(selectinload(ValuationAssessment.asset))
        .where(
            ValuationAssessment.valuation_run_id == latest.id,
            ValuationAssessment.asset_id == asset_id,
        )
    ).scalar_one_or_none()
