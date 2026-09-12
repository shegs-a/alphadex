"""Opportunity Scanner endpoints (read-only).

Serves the latest scan's ranked candidates and the scan-run history. Results are
explainable — each carries a preliminary Screen Score, a data-completeness figure,
and the per-criterion evidence. Statuses are ``candidate`` / ``watch`` /
``insufficient_data`` / ``excluded``; there is no BUY language (§10). A missing
score is ``null`` with a status, never ``0`` (ADR-003).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from alphadex.db import get_session
from alphadex.models import ScanResult, ScanRun
from alphadex.scanner import repository

router = APIRouter(tags=["opportunities"])


class ScanResultOut(BaseModel):
    asset_id: int
    symbol: str
    name: str
    status: str
    screen_score: float | None
    rank: int | None
    data_completeness: float | None
    reasons: dict[str, Any]


class ScanRunOut(BaseModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    universe_size: int
    candidate_count: int


def _result_out(result: ScanResult) -> ScanResultOut:
    return ScanResultOut(
        asset_id=result.asset_id,
        symbol=result.asset.symbol,
        name=result.asset.name,
        status=result.status,
        screen_score=float(result.screen_score)
        if result.screen_score is not None
        else None,
        rank=result.rank,
        data_completeness=float(result.data_completeness)
        if result.data_completeness is not None
        else None,
        reasons=result.reasons,
    )


def _run_out(run: ScanRun) -> ScanRunOut:
    return ScanRunOut(
        id=run.id,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        universe_size=run.universe_size,
        candidate_count=run.candidate_count,
    )


@router.get("/opportunities", response_model=list[ScanResultOut])
def list_opportunities(
    session: Annotated[Session, Depends(get_session)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ScanResultOut]:
    """Ranked results from the latest successful scan (default: all statuses)."""
    latest = repository.get_latest_scan_run(session)
    if latest is None:
        return []
    results = repository.get_results(
        session, latest.id, status=status_filter, limit=limit, offset=offset
    )
    return [_result_out(r) for r in results]


@router.get("/opportunities/{asset_id}", response_model=ScanResultOut)
def get_opportunity(
    asset_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> ScanResultOut:
    """One asset's result from the latest scan; 404 if it was not scanned."""
    result = repository.get_latest_result_for_asset(session, asset_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found in the latest scan",
        )
    return _result_out(result)


@router.get("/scans", response_model=list[ScanRunOut])
def list_scans(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ScanRunOut]:
    """Recent scan runs with their metadata and counts."""
    return [_run_out(r) for r in repository.list_scan_runs(session, limit=limit)]
