"""Data access for the Tokenomics engine."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from alphadex.fundamentals.normalize import (
    METRIC_FEES_30D_USD,
    METRIC_HOLDERS_REVENUE_30D_USD,
    METRIC_REVENUE_30D_USD,
)
from alphadex.marketdata.normalize import (
    METRIC_CIRCULATING_SUPPLY,
    METRIC_FDV_USD,
    METRIC_MARKET_CAP_USD,
    METRIC_MAX_SUPPLY,
    METRIC_TOTAL_SUPPLY,
)
from alphadex.models import TokenomicsRun, TokenomicsSignal

TOKENOMICS_METRICS = (
    METRIC_MARKET_CAP_USD,
    METRIC_FDV_USD,
    METRIC_CIRCULATING_SUPPLY,
    METRIC_TOTAL_SUPPLY,
    METRIC_MAX_SUPPLY,
    METRIC_FEES_30D_USD,
    METRIC_REVENUE_30D_USD,
    METRIC_HOLDERS_REVENUE_30D_USD,
)


def get_latest_run(session: Session) -> TokenomicsRun | None:
    return session.execute(
        select(TokenomicsRun)
        .where(TokenomicsRun.status == "success")
        .order_by(TokenomicsRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def list_runs(session: Session, *, limit: int = 20) -> list[TokenomicsRun]:
    return list(
        session.execute(
            select(TokenomicsRun).order_by(TokenomicsRun.id.desc()).limit(limit)
        ).scalars()
    )


def get_signals(
    session: Session,
    run_id: int,
    *,
    label: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[TokenomicsSignal]:
    stmt = (
        select(TokenomicsSignal)
        .options(selectinload(TokenomicsSignal.asset))
        .where(TokenomicsSignal.tokenomics_run_id == run_id)
    )
    if label is not None:
        stmt = stmt.where(TokenomicsSignal.value_capture_label == label)
    stmt = (
        stmt.order_by(
            TokenomicsSignal.rank.is_(None),
            TokenomicsSignal.rank,
            TokenomicsSignal.asset_id,
        )
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars())


def get_latest_signal_for_asset(
    session: Session, asset_id: int
) -> TokenomicsSignal | None:
    latest = get_latest_run(session)
    if latest is None:
        return None
    return session.execute(
        select(TokenomicsSignal)
        .options(selectinload(TokenomicsSignal.asset))
        .where(
            TokenomicsSignal.tokenomics_run_id == latest.id,
            TokenomicsSignal.asset_id == asset_id,
        )
    ).scalar_one_or_none()
