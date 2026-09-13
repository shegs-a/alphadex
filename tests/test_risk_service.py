"""Integration + API tests for the Risk engine (SQLite)."""

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
from alphadex.marketdata.normalize import (
    METRIC_FDV_USD,
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
)
from alphadex.models import Asset, MetricObservation, RiskAssessment, ValueStatus
from alphadex.risk import service as service_module
from alphadex.risk.config import RiskConfig
from alphadex.risk.service import RiskService

_FORBIDDEN = ("BUY", "GUARANTEED", "100% PUMP", "RISK FREE")


def _cfg() -> RiskConfig:
    return RiskConfig(
        scope="all",
        ref_turnover=0.10,
        ref_volatility=0.50,
        ref_market_cap=1e10,
        weight_liquidity=0.30,
        weight_volatility=0.30,
        weight_dilution=0.20,
        weight_size=0.20,
        band_moderate=0.25,
        band_elevated=0.50,
        band_high=0.75,
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


def _seed(session: Session, symbol: str) -> Asset:
    a = Asset(symbol=symbol, name=f"{symbol} Coin")
    session.add(a)
    session.flush()
    _obs(session, a.id, METRIC_MARKET_CAP_USD, 1e9)
    _obs(session, a.id, METRIC_FDV_USD, 2e9)
    _obs(session, a.id, METRIC_TOTAL_VOLUME_USD, 1e7)
    _obs(session, a.id, METRIC_PRICE_CHANGE_PCT_30D, 60.0)
    return a


def test_run_persists_with_band_and_data_quality(session: Session) -> None:
    a = _seed(session, "AAA")
    session.commit()

    summary = RiskService(session, _cfg()).run()
    assert summary.status == "success"
    assert summary.analyzed_count == 1

    ra = session.execute(
        select(RiskAssessment).where(RiskAssessment.asset_id == a.id)
    ).scalar_one()
    assert ra.risk_score is not None
    assert ra.risk_band in ("moderate", "elevated", "high")
    assert ra.concentration_risk is None  # data gap surfaced, never guessed
    assert ra.data_quality is not None and ra.data_quality < 1.0


def test_per_asset_isolation(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(session, "AAA")
    _seed(session, "BBB")
    session.commit()

    real = service_module.evaluate
    calls = {"n": 0}

    def failing(values, config):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return real(values, config)

    monkeypatch.setattr(service_module, "evaluate", failing)
    summary = RiskService(session, _cfg()).run()
    assert summary.failed_count == 1
    assert (
        session.execute(select(func.count()).select_from(RiskAssessment)).scalar_one()
        == 1
    )


@pytest.fixture()
def client(sqlite_engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    with factory() as seed:
        _seed(seed, "AAA")
        seed.commit()
        RiskService(seed, _cfg()).run()

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


def test_api_risk(client: TestClient) -> None:
    resp = client.get("/risk")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    a = body[0]
    assert a["symbol"] == "AAA"
    assert a["risk_score"] is not None
    assert a["risk_band"] in ("moderate", "elevated", "high")
    assert a["concentration_risk"] is None
    assert a["liquidity_risk"] is not None


def test_api_404_runs_and_no_buy(client: TestClient) -> None:
    assert client.get("/risk/99999").status_code == 404
    runs = client.get("/risk-runs").json()
    assert len(runs) == 1 and runs[0]["analyzed_count"] == 1
    payload = json.dumps(client.get("/risk").json()).upper()
    for term in _FORBIDDEN:
        assert term not in payload
