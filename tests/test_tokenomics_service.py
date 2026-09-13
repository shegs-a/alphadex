"""Integration + API tests for the Tokenomics engine (SQLite)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from alphadex.api.app import app
from alphadex.db import get_session
from alphadex.fundamentals.normalize import (
    METRIC_FEES_30D_USD,
    METRIC_HOLDERS_REVENUE_30D_USD,
    METRIC_REVENUE_30D_USD,
)
from alphadex.marketdata.normalize import METRIC_FDV_USD, METRIC_MARKET_CAP_USD
from alphadex.models import Asset, MetricObservation, TokenomicsSignal, ValueStatus
from alphadex.tokenomics import service as service_module
from alphadex.tokenomics.config import TokenomicsConfig
from alphadex.tokenomics.service import TokenomicsService

_FORBIDDEN = ("BUY", "GUARANTEED", "100% PUMP", "RISK FREE")


def _cfg() -> TokenomicsConfig:
    return TokenomicsConfig(
        scope="all", ref_real_yield=0.10, weight_dilution=0.5, weight_value_capture=0.5
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


def _seed_full(session: Session, symbol: str) -> Asset:
    a = Asset(symbol=symbol, name=f"{symbol} Coin")
    session.add(a)
    session.flush()
    _obs(session, a.id, METRIC_MARKET_CAP_USD, 5e8)
    _obs(session, a.id, METRIC_FDV_USD, 1e9)
    _obs(session, a.id, METRIC_FEES_30D_USD, 100.0)
    _obs(session, a.id, METRIC_REVENUE_30D_USD, 30.0)
    _obs(session, a.id, METRIC_HOLDERS_REVENUE_30D_USD, 15.0)
    return a


def test_run_persists_and_ranks(session: Session) -> None:
    a = _seed_full(session, "AAA")
    b = Asset(symbol="BBB", name="BBB Coin")  # no data → unknown
    session.add(b)
    session.flush()
    session.commit()

    summary = TokenomicsService(session, _cfg()).run()
    assert summary.status == "success"
    assert summary.analyzed_count == 2

    sa = session.execute(
        select(TokenomicsSignal).where(TokenomicsSignal.asset_id == a.id)
    ).scalar_one()
    sb = session.execute(
        select(TokenomicsSignal).where(TokenomicsSignal.asset_id == b.id)
    ).scalar_one()
    assert sa.value_capture_score is not None and sa.rank == 1
    assert sa.revenue_to_fees is not None
    # No-data asset: null score + unknown label, never 0, not ranked.
    assert sb.value_capture_score is None
    assert sb.value_capture_label == "unknown"
    assert sb.rank is None


def test_per_asset_isolation(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_full(session, "AAA")
    _seed_full(session, "BBB")
    session.commit()

    real = service_module.evaluate
    calls = {"n": 0}

    def failing(values, config):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:  # fail the second asset only
            raise RuntimeError("boom")
        return real(values, config)

    monkeypatch.setattr(service_module, "evaluate", failing)
    summary = TokenomicsService(session, _cfg()).run()
    assert summary.failed_count == 1
    assert summary.analyzed_count == 1
    assert (
        session.execute(select(func.count()).select_from(TokenomicsSignal)).scalar_one()
        == 1
    )


@pytest.fixture()
def client(sqlite_engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    with factory() as seed:
        _seed_full(seed, "AAA")
        seed.commit()
        TokenomicsService(seed, _cfg()).run()

    def _override() -> Iterator[Session]:
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_api_tokenomics(client: TestClient) -> None:
    resp = client.get("/tokenomics")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    sig = body[0]
    assert sig["symbol"] == "AAA"
    assert sig["value_capture_score"] is not None
    assert sig["revenue_to_fees"] == 0.3
    assert sig["holders_to_revenue"] == 0.5
    assert sig["value_capture_label"] in ("strong", "moderate", "weak")


def test_api_404_and_runs_and_no_buy(client: TestClient) -> None:
    assert client.get("/tokenomics/99999").status_code == 404
    runs = client.get("/tokenomics-runs").json()
    assert len(runs) == 1 and runs[0]["analyzed_count"] == 1
    payload = json.dumps(client.get("/tokenomics").json()).upper()
    for term in _FORBIDDEN:
        assert term not in payload
