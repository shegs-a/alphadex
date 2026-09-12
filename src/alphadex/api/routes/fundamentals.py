"""Fundamentals endpoints (read-only).

Surfaces the latest ``fundamental.*`` observation per (asset, metric, period).
Fees, revenue, holders-revenue, and TVL are distinct metrics (AGENTS.md §9), and
missing values are represented by ``value_status`` — never a misleading ``0``
(ADR-003). Kept separate from ``/market-data`` to preserve the domain boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from alphadex.db import get_session
from alphadex.fundamentals import repository
from alphadex.models import MetricObservation

router = APIRouter(tags=["fundamentals"])


class FundamentalObservationOut(BaseModel):
    asset_id: int
    metric: str
    value: float | None
    value_status: str
    unit: str | None
    period: str
    observed_at: datetime
    source_provider: str | None
    source_timestamp: datetime | None
    source_status: str | None
    age_seconds: float | None


def _age_seconds(observed_at: datetime) -> float | None:
    if observed_at is None:  # pragma: no cover - defensive
        return None
    ts = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - ts).total_seconds()


def _to_out(obs: MetricObservation) -> FundamentalObservationOut:
    return FundamentalObservationOut(
        asset_id=obs.asset_id,
        metric=obs.metric,
        value=float(obs.value) if obs.value is not None else None,
        value_status=obs.value_status.value,
        unit=obs.unit,
        period=obs.period,
        observed_at=obs.observed_at,
        source_provider=obs.source_provider,
        source_timestamp=obs.source_timestamp,
        source_status=obs.source_status,
        age_seconds=_age_seconds(obs.observed_at),
    )


@router.get("/fundamentals", response_model=list[FundamentalObservationOut])
def list_fundamentals(
    session: Annotated[Session, Depends(get_session)],
    asset_id: Annotated[int | None, Query()] = None,
    metric: Annotated[str | None, Query()] = None,
) -> list[FundamentalObservationOut]:
    observations = repository.latest_fundamentals(
        session, asset_id=asset_id, metric=metric
    )
    return [_to_out(o) for o in observations]
