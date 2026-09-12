"""API tests for /assets and /market-data (read-only).

Seeds a throwaway SQLite database via the ingestion service (fake provider), then
overrides the app's DB dependency to serve from it. Asserts the endpoints return
the ingested data and, crucially, surface missing values as an explicit status —
never ``0`` (ADR-003).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from alphadex.api.app import app
from alphadex.db import get_session
from alphadex.marketdata.service import MarketDataService
from alphadex.providers.base import MarketDataProvider
from alphadex.providers.base import RawMarketSnapshot as Snap

_OBSERVED = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


class FakeProvider(MarketDataProvider):
    name = "fake"

    def fetch_markets(self, *, ids=None, top_n=None):  # type: ignore[no-untyped-def]
        return [
            Snap(
                external_id="bitcoin",
                symbol="BTC",
                name="Bitcoin",
                observed_at=_OBSERVED,
                price_usd=61234.5,
                market_cap_usd=1203456789012.0,
                fully_diluted_valuation_usd=None,  # missing → NOT_AVAILABLE
                total_volume_usd=34567890123.0,
                circulating_supply=19750000.0,
                total_supply=21000000.0,
                max_supply=21000000.0,
                price_change_pct_24h=1.23,
                price_change_pct_7d=-2.5,
                price_change_pct_30d=8.9,
                market_cap_rank=1.0,
            )
        ]


@pytest.fixture()
def client(sqlite_engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    # Seed the database through the real ingestion path.
    with factory() as seed:
        MarketDataService(FakeProvider(), seed).ingest()

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


def test_list_assets(client: TestClient) -> None:
    resp = client.get("/assets")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    asset = body[0]
    assert asset["symbol"] == "BTC"
    assert asset["source_ids"] == [{"provider": "fake", "external_id": "bitcoin"}]


def test_get_asset_404(client: TestClient) -> None:
    resp = client.get("/assets/99999")
    assert resp.status_code == 404


def test_market_data_returns_observations(client: TestClient) -> None:
    resp = client.get("/market-data")
    assert resp.status_code == 200
    body = resp.json()
    metrics = {row["metric"]: row for row in body}

    price = metrics["market.price_usd"]
    assert price["value"] == 61234.5
    assert price["value_status"] == "OK"
    assert price["unit"] == "USD"
    assert price["source_provider"] == "fake"
    assert price["age_seconds"] is not None


def test_missing_metric_surfaces_status_not_zero(client: TestClient) -> None:
    resp = client.get(
        "/market-data", params={"metric": "market.fully_diluted_valuation_usd"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    row = body[0]
    # The key guarantee: absent data is a status, not a fake 0.
    assert row["value"] is None
    assert row["value_status"] == "NOT_AVAILABLE"


def test_filter_by_asset(client: TestClient) -> None:
    assets = client.get("/assets").json()
    asset_id = assets[0]["id"]
    resp = client.get("/market-data", params={"asset_id": asset_id})
    assert resp.status_code == 200
    assert all(row["asset_id"] == asset_id for row in resp.json())
