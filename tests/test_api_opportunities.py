"""API tests for /opportunities and /scans (read-only)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from alphadex.api.app import app
from alphadex.db import get_session
from alphadex.fundamentals.normalize import METRIC_FEES_30D_USD
from alphadex.marketdata.normalize import (
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
)
from alphadex.models import Asset, MetricObservation, ValueStatus
from alphadex.scanner.config import ScreenConfig
from alphadex.scanner.service import ScanService

_FORBIDDEN = ("BUY", "GUARANTEED", "100% PUMP", "RISK FREE")


def _cfg() -> ScreenConfig:
    return ScreenConfig(
        market_cap_min=1e7,
        market_cap_max=None,
        min_volume_24h=1e5,
        freshness_max_hours=48.0,
        require_fundamentals=False,
        ref_fees_30d=1e8,
        ref_volume_24h=1e9,
        weight_activity=0.4,
        weight_liquidity=0.3,
        weight_momentum=0.3,
    )


def _obs(session: Session, asset_id: int, metric: str, value: float) -> None:
    session.add(
        MetricObservation(
            asset_id=asset_id,
            metric=metric,
            value=value,
            value_status=ValueStatus.OK,
            unit="USD",
            period="point",
            observed_at=datetime.now(UTC),
            source_provider="test",
        )
    )


@pytest.fixture()
def client(sqlite_engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    with factory() as seed:
        a = Asset(symbol="AAA", name="AAA Coin")
        b = Asset(symbol="CCC", name="CCC Coin")
        seed.add_all([a, b])
        seed.flush()
        # a → candidate
        _obs(seed, a.id, METRIC_MARKET_CAP_USD, 1e9)
        _obs(seed, a.id, METRIC_TOTAL_VOLUME_USD, 5e6)
        _obs(seed, a.id, METRIC_PRICE_CHANGE_PCT_30D, 10.0)
        _obs(seed, a.id, METRIC_FEES_30D_USD, 5e6)
        # b → excluded (below floor)
        _obs(seed, b.id, METRIC_MARKET_CAP_USD, 1e6)
        _obs(seed, b.id, METRIC_TOTAL_VOLUME_USD, 2e6)
        _obs(seed, b.id, METRIC_PRICE_CHANGE_PCT_30D, 1.0)
        seed.commit()
        ScanService(seed, _cfg()).run()

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


def test_list_opportunities_ranked_with_evidence(client: TestClient) -> None:
    resp = client.get("/opportunities")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    top = body[0]
    assert top["symbol"] == "AAA"
    assert top["status"] == "candidate"
    assert top["rank"] == 1
    assert top["screen_score"] is not None
    assert "gates" in top["reasons"] and "signals" in top["reasons"]


def test_filter_by_status(client: TestClient) -> None:
    resp = client.get("/opportunities", params={"status": "candidate"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(r["status"] == "candidate" for r in body)
    assert len(body) == 1


def test_excluded_asset_has_null_score(client: TestClient) -> None:
    resp = client.get("/opportunities", params={"status": "excluded"})
    body = resp.json()
    assert len(body) == 1
    assert body[0]["screen_score"] is None  # never a fake 0


def test_get_opportunity_404_for_unknown_asset(client: TestClient) -> None:
    assert client.get("/opportunities/99999").status_code == 404


def test_scans_lists_runs(client: TestClient) -> None:
    resp = client.get("/scans")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["universe_size"] == 2
    assert runs[0]["candidate_count"] == 1


def test_no_forbidden_buy_language(client: TestClient) -> None:
    payload = json.dumps(client.get("/opportunities").json()).upper()
    for term in _FORBIDDEN:
        assert term not in payload
