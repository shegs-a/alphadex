"""API tests for /divergences and /divergence-runs (read-only)."""

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
from alphadex.divergence.config import DivergenceConfig
from alphadex.divergence.service import DivergenceService
from alphadex.fundamentals.normalize import METRIC_FEES_7D_USD, METRIC_FEES_30D_USD
from alphadex.marketdata.normalize import METRIC_PRICE_CHANGE_PCT_30D
from alphadex.models import Asset, MetricObservation, ValueStatus

_FORBIDDEN = ("BUY", "GUARANTEED", "100% PUMP", "RISK FREE")


def _cfg() -> DivergenceConfig:
    return DivergenceConfig(
        scope="all",
        min_history_days=5.0,
        threshold=0.15,
        weakening_threshold=-0.15,
        min_fundamentals_improvement=0.05,
        weight_gap=0.7,
        weight_valuation=0.3,
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
        seed.add(a)
        seed.flush()
        _obs(seed, a.id, METRIC_FEES_7D_USD, 12.0)
        _obs(seed, a.id, METRIC_FEES_30D_USD, 30.0)
        _obs(seed, a.id, METRIC_PRICE_CHANGE_PCT_30D, -15.0)
        seed.commit()
        DivergenceService(seed, _cfg()).run()

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


def test_list_divergences_with_evidence(client: TestClient) -> None:
    resp = client.get("/divergences")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    sig = body[0]
    assert sig["symbol"] == "AAA"
    assert sig["classification"] == "fundamental_divergence"
    assert sig["rank"] == 1
    assert sig["divergence_score"] is not None
    assert sig["method"] == "growth_window"
    assert "what_changed" in sig["evidence"]


def test_filter_by_classification(client: TestClient) -> None:
    resp = client.get("/divergences", params={"classification": "thesis_weakening"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_divergence_404(client: TestClient) -> None:
    assert client.get("/divergences/99999").status_code == 404


def test_divergence_runs_listed(client: TestClient) -> None:
    resp = client.get("/divergence-runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["analyzed_count"] == 1
    assert runs[0]["divergence_count"] == 1


def test_no_buy_language(client: TestClient) -> None:
    payload = json.dumps(client.get("/divergences").json()).upper()
    for term in _FORBIDDEN:
        assert term not in payload
