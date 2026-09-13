"""Alpha Score endpoints (read-only) — the ranked opportunity list.

Each item exposes the **three separate outputs** (§10, ADR-006): an Alpha Score (+
band), a Risk Score (+ band, from the Risk engine — not folded into Alpha), and a
Confidence (+ band), plus ``model_completeness``, the decision ``status`` (allowed
vocabulary only — never BUY), a per-component breakdown, and evidence. Ranking is by
Alpha Score (ties broken toward higher completeness); Risk and Confidence are shown
alongside so a human weighs them. Missing scores are ``null`` with a status — never
``0`` (ADR-003).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from alphadex.alpha import repository
from alphadex.db import get_session
from alphadex.models import AlphaRun, AlphaScore

router = APIRouter(tags=["scores"])


class AlphaScoreOut(BaseModel):
    asset_id: int
    symbol: str
    name: str
    alpha_score: float | None
    alpha_band: str | None
    risk_score: float | None
    risk_band: str | None
    confidence: float | None
    confidence_band: str | None
    model_completeness: float | None
    status: str
    rank: int | None
    components: list[dict[str, Any]]
    evidence: dict[str, Any]


class AlphaRunOut(BaseModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    analyzed_count: int
    scored_count: int


def _num(v: Any) -> float | None:
    return float(v) if v is not None else None


def _score_out(s: AlphaScore) -> AlphaScoreOut:
    return AlphaScoreOut(
        asset_id=s.asset_id,
        symbol=s.asset.symbol,
        name=s.asset.name,
        alpha_score=_num(s.alpha_score),
        alpha_band=s.alpha_band,
        risk_score=_num(s.risk_score),
        risk_band=s.risk_band,
        confidence=_num(s.confidence),
        confidence_band=s.confidence_band,
        model_completeness=_num(s.model_completeness),
        status=s.status,
        rank=s.rank,
        components=s.components,
        evidence=s.evidence,
    )


def _run_out(r: AlphaRun) -> AlphaRunOut:
    return AlphaRunOut(
        id=r.id,
        status=r.status,
        started_at=r.started_at,
        finished_at=r.finished_at,
        analyzed_count=r.analyzed_count,
        scored_count=r.scored_count,
    )


@router.get("/scores", response_model=list[AlphaScoreOut])
def list_scores(
    session: Annotated[Session, Depends(get_session)],
    status: Annotated[str | None, Query()] = None,
    risk_band: Annotated[str | None, Query()] = None,
    confidence_band: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AlphaScoreOut]:
    latest = repository.get_latest_run(session)
    if latest is None:
        return []
    scores = repository.get_scores(
        session,
        latest.id,
        status=status,
        risk_band=risk_band,
        confidence_band=confidence_band,
        limit=limit,
        offset=offset,
    )
    return [_score_out(s) for s in scores]


@router.get("/scores/{asset_id}", response_model=AlphaScoreOut)
def get_score(
    asset_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> AlphaScoreOut:
    s = repository.get_latest_score_for_asset(session, asset_id)
    if s is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="asset not found in the latest alpha run",
        )
    return _score_out(s)


@router.get("/score-runs", response_model=list[AlphaRunOut])
def list_score_runs(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[AlphaRunOut]:
    return [_run_out(r) for r in repository.list_runs(session, limit=limit)]
