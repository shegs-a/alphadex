"""Asset universe endpoints (read-only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from alphadex.db import get_session
from alphadex.marketdata import repository
from alphadex.models import Asset

router = APIRouter(tags=["assets"])


class SourceIdOut(BaseModel):
    provider: str
    external_id: str


class AssetOut(BaseModel):
    id: int
    symbol: str
    name: str
    category: str | None
    source_ids: list[SourceIdOut]


def _to_out(asset: Asset) -> AssetOut:
    return AssetOut(
        id=asset.id,
        symbol=asset.symbol,
        name=asset.name,
        category=asset.category,
        source_ids=[
            SourceIdOut(provider=s.provider, external_id=s.external_id)
            for s in asset.source_ids
        ],
    )


@router.get("/assets", response_model=list[AssetOut])
def list_assets(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AssetOut]:
    assets = repository.list_assets(session, limit=limit, offset=offset)
    return [_to_out(a) for a in assets]


@router.get("/assets/{asset_id}", response_model=AssetOut)
def get_asset(
    asset_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> AssetOut:
    asset = repository.get_asset(session, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="asset not found"
        )
    return _to_out(asset)
