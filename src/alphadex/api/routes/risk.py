"""Risk endpoints (read-only).

Serves the latest Risk run's assessments — a **separate** output from the Alpha Score
(§10). Each carries the distinct risk factors, a blended `risk_score` and `risk_band`
(`low`/`moderate`/`elevated`/`high`/`unknown`), a separate `data_quality`, and
evidence. `concentration_risk` is `null` (no on-chain data — a surfaced gap). A
missing score is `null` with a band, never `0` (ADR-003). Language is *risk elevated /
risk high*, never BUY/GUARANTEED. Ordered by risk score, highest first (a warning
ordering, not an opportunity ranking).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from alphadex.db import get_session
from alphadex.models import RiskAssessment, RiskRun
from alphadex.risk import repository

router = APIRouter(tags=["risk"])


class RiskAssessmentOut(BaseModel):
    asset_id: int
    symbol: str
    name: str
    risk_score: float | None
    risk_band: str | None
    liquidity_risk: float | None
    volatility_risk: float | None
    dilution_risk: float | None
    size_risk: float | None
    concentration_risk: float | None
    data_quality: float | None
    rank: int | None
    evidence: dict[str, Any]


class RiskRunOut(BaseModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    analyzed_count: int


def _num(v: Any) -> float | None:
    return float(v) if v is not None else None


def _assessment_out(a: RiskAssessment) -> RiskAssessmentOut:
    return RiskAssessmentOut(
        asset_id=a.asset_id,
        symbol=a.asset.symbol,
        name=a.asset.name,
        risk_score=_num(a.risk_score),
        risk_band=a.risk_band,
        liquidity_risk=_num(a.liquidity_risk),
        volatility_risk=_num(a.volatility_risk),
        dilution_risk=_num(a.dilution_risk),
        size_risk=_num(a.size_risk),
        concentration_risk=_num(a.concentration_risk),
        data_quality=_num(a.data_quality),
        rank=a.rank,
        evidence=a.evidence,
    )


def _run_out(r: RiskRun) -> RiskRunOut:
    return RiskRunOut(
        id=r.id,
        status=r.status,
        started_at=r.started_at,
        finished_at=r.finished_at,
        analyzed_count=r.analyzed_count,
    )


@router.get("/risk", response_model=list[RiskAssessmentOut])
def list_risk(
    session: Annotated[Session, Depends(get_session)],
    band: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RiskAssessmentOut]:
    latest = repository.get_latest_run(session)
    if latest is None:
        return []
    rows = repository.get_assessments(
        session, latest.id, band=band, limit=limit, offset=offset
    )
    return [_assessment_out(a) for a in rows]


@router.get("/risk/{asset_id}", response_model=RiskAssessmentOut)
def get_risk(
    asset_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> RiskAssessmentOut:
    assessment = repository.get_latest_assessment_for_asset(session, asset_id)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found in the latest risk run",
        )
    return _assessment_out(assessment)


@router.get("/risk-runs", response_model=list[RiskRunOut])
def list_risk_runs(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RiskRunOut]:
    return [_run_out(r) for r in repository.list_runs(session, limit=limit)]
