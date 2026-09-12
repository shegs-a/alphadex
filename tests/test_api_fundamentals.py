"""API tests for /fundamentals (read-only).

Seeds a throwaway SQLite database (an asset with a coingecko source id, then a
fundamentals ingestion via a fake provider) and overrides the app's DB dependency
to serve from it. Asserts fundamentals are returned with distinct metrics and that
missing values surface as an explicit status — never ``0`` (ADR-003).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from alphadex.api.app import app
from alphadex.db import get_session
from alphadex.fundamentals.service import FundamentalDataService
from alphadex.models import Asset, AssetSourceId
from alphadex.providers.base import FundamentalDataProvider
from alphadex.providers.base import RawFundamentalSnapshot as Snap


class FakeProvider(FundamentalDataProvider):
    name = "defillama"

    def fetch_fundamentals(self):  # type: ignore[no-untyped-def]
        return [
            Snap(
                slug="uniswap",
                name="Uniswap",
                gecko_id="uniswap",
                symbol="UNI",
                category="Dexes",
                observed_at=None,
                tvl_usd=5_000_000_000.0,
                fees_24h_usd=2_000_000.0,
                fees_7d_usd=1.4e7,
                fees_30d_usd=6e7,
                revenue_24h_usd=None,  # missing → NOT_AVAILABLE
                revenue_7d_usd=None,
                revenue_30d_usd=None,
                holders_revenue_24h_usd=None,
                holders_revenue_30d_usd=None,
            )
        ]


@pytest.fixture()
def client(sqlite_engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    with factory() as seed:
        asset = Asset(symbol="UNI", name="Uniswap")
        seed.add(asset)
        seed.flush()
        seed.add(
            AssetSourceId(
                asset_id=asset.id, provider="coingecko", external_id="uniswap"
            )
        )
        seed.commit()
        FundamentalDataService(FakeProvider(), seed).ingest()

    def _override() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_fundamentals_returns_distinct_metrics(client: TestClient) -> None:
    resp = client.get("/fundamentals")
    assert resp.status_code == 200
    body = resp.json()
    metrics = {row["metric"]: row for row in body}

    fees = metrics["fundamental.fees_usd.24h"]
    assert fees["value"] == 2_000_000.0
    assert fees["value_status"] == "OK"
    assert fees["unit"] == "USD"
    assert fees["source_provider"] == "defillama"
    tvl = metrics["fundamental.tvl_usd"]
    assert tvl["value"] == 5_000_000_000.0
    assert tvl["period"] == "point"


def test_missing_revenue_surfaces_status_not_zero(client: TestClient) -> None:
    resp = client.get("/fundamentals", params={"metric": "fundamental.revenue_usd.24h"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["value"] is None
    assert body[0]["value_status"] == "NOT_AVAILABLE"


def test_market_data_endpoint_excludes_fundamentals(client: TestClient) -> None:
    # /market-data must not return fundamental.* rows (domain separation).
    resp = client.get("/market-data")
    assert resp.status_code == 200
    assert resp.json() == []
