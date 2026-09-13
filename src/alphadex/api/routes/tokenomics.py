"""Tokenomics endpoints (read-only).

Serves the latest Token Value Capture run's signals. Each carries the distinct
component ratios (float ratio, revenue/fees, holders/revenue, real yield), a
`value_capture_score` (a component, not the Alpha Score) with a label, a separate
`data_completeness`, and evidence. Missing components are `null` — never `0`
(ADR-003). No BUY language (§10). Ranking is by value-capture score, highest first
— a component ranking, not an opportunity ranking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from alphadex.db import get_session
from alphadex.models import TokenomicsRun, TokenomicsSignal
from alphadex.tokenomics import repository

router = APIRouter(tags=["tokenomics"])


class TokenomicsSignalOut(BaseModel):
    asset_id: int
    symbol: str
    name: str
    value_capture_score: float | None
    value_capture_label: str | None
    float_ratio: float | None
    revenue_to_fees: float | None
    holders_to_revenue: float | None
    real_yield: float | None
    data_completeness: float | None
    rank: int | None
    evidence: dict[str, Any]


class TokenomicsRunOut(BaseModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    analyzed_count: int


def _num(v: Any) -> float | None:
    return float(v) if v is not None else None


def _signal_out(s: TokenomicsSignal) -> TokenomicsSignalOut:
    return TokenomicsSignalOut(
        asset_id=s.asset_id,
        symbol=s.asset.symbol,
        name=s.asset.name,
        value_capture_score=_num(s.value_capture_score),
        value_capture_label=s.value_capture_label,
        float_ratio=_num(s.float_ratio),
        revenue_to_fees=_num(s.revenue_to_fees),
        holders_to_revenue=_num(s.holders_to_revenue),
        real_yield=_num(s.real_yield),
        data_completeness=_num(s.data_completeness),
        rank=s.rank,
        evidence=s.evidence,
    )


def _run_out(r: TokenomicsRun) -> TokenomicsRunOut:
    return TokenomicsRunOut(
        id=r.id,
        status=r.status,
        started_at=r.started_at,
        finished_at=r.finished_at,
        analyzed_count=r.analyzed_count,
    )


@router.get("/tokenomics", response_model=list[TokenomicsSignalOut])
def list_tokenomics(
    session: Annotated[Session, Depends(get_session)],
    label: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TokenomicsSignalOut]:
    latest = repository.get_latest_run(session)
    if latest is None:
        return []
    signals = repository.get_signals(
        session, latest.id, label=label, limit=limit, offset=offset
    )
    return [_signal_out(s) for s in signals]


@router.get("/tokenomics/{asset_id}", response_model=TokenomicsSignalOut)
def get_tokenomics(
    asset_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> TokenomicsSignalOut:
    signal = repository.get_latest_signal_for_asset(session, asset_id)
    if signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found in the latest tokenomics run",
        )
    return _signal_out(signal)


@router.get("/tokenomics-runs", response_model=list[TokenomicsRunOut])
def list_tokenomics_runs(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[TokenomicsRunOut]:
    return [_run_out(r) for r in repository.list_runs(session, limit=limit)]
