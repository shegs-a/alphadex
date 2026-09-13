"""Divergence endpoints (read-only).

Serves the latest divergence run's ranked signals and the run history. Each signal is
explainable — it carries the fundamentals/price/valuation trends, the method used, a
divergence score, a data-quality figure, and the §10 evidence. Classifications are
``fundamental_divergence`` / ``watch`` / ``thesis_weakening`` / ``insufficient_data``;
there is no BUY language (§10). A missing score is ``null`` with a classification,
never ``0`` (ADR-003).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from alphadex.db import get_session
from alphadex.divergence import repository
from alphadex.models import DivergenceRun, DivergenceSignal

router = APIRouter(tags=["divergences"])


class DivergenceSignalOut(BaseModel):
    asset_id: int
    symbol: str
    name: str
    classification: str
    divergence_score: float | None
    fundamentals_trend: float | None
    price_trend: float | None
    valuation_trend: float | None
    window: str | None
    method: str | None
    data_quality: float | None
    rank: int | None
    evidence: dict[str, Any]


class DivergenceRunOut(BaseModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    analyzed_count: int
    divergence_count: int


def _num(value: Any) -> float | None:
    return float(value) if value is not None else None


def _signal_out(signal: DivergenceSignal) -> DivergenceSignalOut:
    return DivergenceSignalOut(
        asset_id=signal.asset_id,
        symbol=signal.asset.symbol,
        name=signal.asset.name,
        classification=signal.classification,
        divergence_score=_num(signal.divergence_score),
        fundamentals_trend=_num(signal.fundamentals_trend),
        price_trend=_num(signal.price_trend),
        valuation_trend=_num(signal.valuation_trend),
        window=signal.window,
        method=signal.method,
        data_quality=_num(signal.data_quality),
        rank=signal.rank,
        evidence=signal.evidence,
    )


def _run_out(run: DivergenceRun) -> DivergenceRunOut:
    return DivergenceRunOut(
        id=run.id,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        analyzed_count=run.analyzed_count,
        divergence_count=run.divergence_count,
    )


@router.get("/divergences", response_model=list[DivergenceSignalOut])
def list_divergences(
    session: Annotated[Session, Depends(get_session)],
    classification: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DivergenceSignalOut]:
    latest = repository.get_latest_divergence_run(session)
    if latest is None:
        return []
    signals = repository.get_signals(
        session, latest.id, classification=classification, limit=limit, offset=offset
    )
    return [_signal_out(s) for s in signals]


@router.get("/divergences/{asset_id}", response_model=DivergenceSignalOut)
def get_divergence(
    asset_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> DivergenceSignalOut:
    signal = repository.get_latest_signal_for_asset(session, asset_id)
    if signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found in the latest divergence run",
        )
    return _signal_out(signal)


@router.get("/divergence-runs", response_model=list[DivergenceRunOut])
def list_divergence_runs(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[DivergenceRunOut]:
    return [_run_out(r) for r in repository.list_divergence_runs(session, limit=limit)]
