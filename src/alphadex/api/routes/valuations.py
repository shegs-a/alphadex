"""Valuation endpoints (read-only).

Serves the latest Valuation run's assessments. Each carries the four **distinct**
multiples (market cap over annualized fees / revenue / holders-revenue, and Mcap/TVL —
distinct economic meanings, §9), a `valuation_score` (a component, not the Alpha
Score) with a label, a separate `data_completeness`, and evidence. The score is a
**relative attractiveness** against heuristic reference multiples — never a claim of
intrinsic/fair value. Missing/undefined multiples are `null` — never `0` (ADR-003).
No BUY language (§10). Ranking is by relative attractiveness, cheapest first — a
component ranking, not an opportunity ranking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from alphadex.db import get_session
from alphadex.models import ValuationAssessment, ValuationRun
from alphadex.valuation import repository

router = APIRouter(tags=["valuation"])


class ValuationAssessmentOut(BaseModel):
    asset_id: int
    symbol: str
    name: str
    valuation_score: float | None
    valuation_label: str | None
    price_to_fees: float | None
    price_to_revenue: float | None
    price_to_holders_revenue: float | None
    mcap_to_tvl: float | None
    data_completeness: float | None
    rank: int | None
    evidence: dict[str, Any]


class ValuationRunOut(BaseModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    analyzed_count: int


def _num(v: Any) -> float | None:
    return float(v) if v is not None else None


def _assessment_out(a: ValuationAssessment) -> ValuationAssessmentOut:
    return ValuationAssessmentOut(
        asset_id=a.asset_id,
        symbol=a.asset.symbol,
        name=a.asset.name,
        valuation_score=_num(a.valuation_score),
        valuation_label=a.valuation_label,
        price_to_fees=_num(a.price_to_fees),
        price_to_revenue=_num(a.price_to_revenue),
        price_to_holders_revenue=_num(a.price_to_holders_revenue),
        mcap_to_tvl=_num(a.mcap_to_tvl),
        data_completeness=_num(a.data_completeness),
        rank=a.rank,
        evidence=a.evidence,
    )


def _run_out(r: ValuationRun) -> ValuationRunOut:
    return ValuationRunOut(
        id=r.id,
        status=r.status,
        started_at=r.started_at,
        finished_at=r.finished_at,
        analyzed_count=r.analyzed_count,
    )


@router.get("/valuations", response_model=list[ValuationAssessmentOut])
def list_valuations(
    session: Annotated[Session, Depends(get_session)],
    label: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ValuationAssessmentOut]:
    latest = repository.get_latest_run(session)
    if latest is None:
        return []
    assessments = repository.get_assessments(
        session, latest.id, label=label, limit=limit, offset=offset
    )
    return [_assessment_out(a) for a in assessments]


@router.get("/valuations/{asset_id}", response_model=ValuationAssessmentOut)
def get_valuation(
    asset_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> ValuationAssessmentOut:
    a = repository.get_latest_assessment_for_asset(session, asset_id)
    if a is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found in the latest valuation run",
        )
    return _assessment_out(a)


@router.get("/valuation-runs", response_model=list[ValuationRunOut])
def list_valuation_runs(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ValuationRunOut]:
    return [_run_out(r) for r in repository.list_runs(session, limit=limit)]
