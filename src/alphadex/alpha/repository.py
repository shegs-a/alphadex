"""Data access for the Alpha Scoring Engine.

Reads the other engines' latest persisted outputs (divergence, tokenomics, risk) plus
the market observations the market-strength component needs, and reads back alpha runs
and scores for the API. The engine depends on no provider — it combines internal data.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from alphadex.marketdata.normalize import (
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
)
from alphadex.models import (
    AlphaRun,
    AlphaScore,
    DivergenceRun,
    DivergenceSignal,
    RiskAssessment,
    RiskRun,
    TokenomicsRun,
    TokenomicsSignal,
    ValuationAssessment,
    ValuationRun,
)

# Market metrics the market-strength component reads.
ALPHA_MARKET_METRICS = (
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
    METRIC_MARKET_CAP_USD,
)


def load_latest_divergence(
    session: Session, asset_ids: list[int]
) -> dict[int, DivergenceSignal]:
    """Latest successful divergence run's signals, keyed by asset id."""
    if not asset_ids:
        return {}
    latest = session.execute(
        select(DivergenceRun)
        .where(DivergenceRun.status == "success")
        .order_by(DivergenceRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return {}
    rows = session.execute(
        select(DivergenceSignal).where(
            DivergenceSignal.divergence_run_id == latest.id,
            DivergenceSignal.asset_id.in_(asset_ids),
        )
    ).scalars()
    return {r.asset_id: r for r in rows}


def load_latest_tokenomics(
    session: Session, asset_ids: list[int]
) -> dict[int, TokenomicsSignal]:
    """Latest successful tokenomics run's signals, keyed by asset id."""
    if not asset_ids:
        return {}
    latest = session.execute(
        select(TokenomicsRun)
        .where(TokenomicsRun.status == "success")
        .order_by(TokenomicsRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return {}
    rows = session.execute(
        select(TokenomicsSignal).where(
            TokenomicsSignal.tokenomics_run_id == latest.id,
            TokenomicsSignal.asset_id.in_(asset_ids),
        )
    ).scalars()
    return {r.asset_id: r for r in rows}


def load_latest_risk(
    session: Session, asset_ids: list[int]
) -> dict[int, RiskAssessment]:
    """Latest successful risk run's assessments, keyed by asset id."""
    if not asset_ids:
        return {}
    latest = session.execute(
        select(RiskRun)
        .where(RiskRun.status == "success")
        .order_by(RiskRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return {}
    rows = session.execute(
        select(RiskAssessment).where(
            RiskAssessment.risk_run_id == latest.id,
            RiskAssessment.asset_id.in_(asset_ids),
        )
    ).scalars()
    return {r.asset_id: r for r in rows}


def load_latest_valuation(
    session: Session, asset_ids: list[int]
) -> dict[int, ValuationAssessment]:
    """Latest successful valuation run's assessments, keyed by asset id."""
    if not asset_ids:
        return {}
    latest = session.execute(
        select(ValuationRun)
        .where(ValuationRun.status == "success")
        .order_by(ValuationRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return {}
    rows = session.execute(
        select(ValuationAssessment).where(
            ValuationAssessment.valuation_run_id == latest.id,
            ValuationAssessment.asset_id.in_(asset_ids),
        )
    ).scalars()
    return {r.asset_id: r for r in rows}


def get_latest_run(session: Session) -> AlphaRun | None:
    return session.execute(
        select(AlphaRun)
        .where(AlphaRun.status == "success")
        .order_by(AlphaRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def list_runs(session: Session, *, limit: int = 20) -> list[AlphaRun]:
    return list(
        session.execute(
            select(AlphaRun).order_by(AlphaRun.id.desc()).limit(limit)
        ).scalars()
    )


def get_scores(
    session: Session,
    run_id: int,
    *,
    status: str | None = None,
    risk_band: str | None = None,
    confidence_band: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[AlphaScore]:
    stmt = (
        select(AlphaScore)
        .options(selectinload(AlphaScore.asset))
        .where(AlphaScore.alpha_run_id == run_id)
    )
    if status is not None:
        stmt = stmt.where(AlphaScore.status == status)
    if risk_band is not None:
        stmt = stmt.where(AlphaScore.risk_band == risk_band)
    if confidence_band is not None:
        stmt = stmt.where(AlphaScore.confidence_band == confidence_band)
    stmt = (
        stmt.order_by(
            AlphaScore.rank.is_(None),
            AlphaScore.rank,
            AlphaScore.asset_id,
        )
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars())


def get_latest_score_for_asset(session: Session, asset_id: int) -> AlphaScore | None:
    latest = get_latest_run(session)
    if latest is None:
        return None
    return session.execute(
        select(AlphaScore)
        .options(selectinload(AlphaScore.asset))
        .where(
            AlphaScore.alpha_run_id == latest.id,
            AlphaScore.asset_id == asset_id,
        )
    ).scalar_one_or_none()
