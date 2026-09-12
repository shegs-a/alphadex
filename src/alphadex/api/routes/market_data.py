"""Market-data endpoints (read-only).

Surfaces the latest observation per (asset, metric, period). Missing values are
represented by ``value_status`` (e.g. ``NOT_AVAILABLE``) — never a misleading
``0`` (ADR-003). Each item carries provenance and a computed freshness so a
consumer can judge staleness.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from alphadex.db import get_session
from alphadex.marketdata import repository
from alphadex.models import MetricObservation

router = APIRouter(tags=["market-data"])


class MarketObservationOut(BaseModel):
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
    """Seconds since the observation, treating naive timestamps as UTC."""
    if observed_at is None:  # pragma: no cover - defensive
        return None
    ts = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - ts).total_seconds()


def _to_out(obs: MetricObservation) -> MarketObservationOut:
    return MarketObservationOut(
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


@router.get("/market-data", response_model=list[MarketObservationOut])
def list_market_data(
    session: Annotated[Session, Depends(get_session)],
    asset_id: Annotated[int | None, Query()] = None,
    metric: Annotated[str | None, Query()] = None,
) -> list[MarketObservationOut]:
    observations = repository.latest_observations(
        session, asset_id=asset_id, metric=metric
    )
    return [_to_out(o) for o in observations]
