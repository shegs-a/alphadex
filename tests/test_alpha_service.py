"""Integration + API tests for the Alpha Scoring Engine (SQLite, end-to-end).

Seeds observations, runs the real upstream engines (divergence → tokenomics → risk),
then the Alpha engine, and asserts the three separate outputs are persisted, ranking is
completeness-aware, per-asset failure is isolated, and the API exposes it with no BUY
language.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from alphadex.alpha import service as service_module
from alphadex.alpha.config import AlphaConfig
from alphadex.alpha.service import AlphaService
from alphadex.api.app import app
from alphadex.db import get_session
from alphadex.divergence.config import DivergenceConfig
from alphadex.divergence.service import DivergenceService
from alphadex.fundamentals.normalize import (
    METRIC_FEES_7D_USD,
    METRIC_FEES_30D_USD,
    METRIC_HOLDERS_REVENUE_30D_USD,
    METRIC_REVENUE_30D_USD,
)
from alphadex.marketdata.normalize import (
    METRIC_FDV_USD,
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
)
from alphadex.models import AlphaScore, Asset, MetricObservation, ValueStatus
from alphadex.risk.config import RiskConfig
from alphadex.risk.service import RiskService
from alphadex.tokenomics.config import TokenomicsConfig
from alphadex.tokenomics.service import TokenomicsService

_FORBIDDEN = ("BUY", "GUARANTEED", "100% PUMP", "RISK FREE")


def _alpha_cfg() -> AlphaConfig:
    return AlphaConfig(
        scope="all",
        weight_economic_growth=0.25,
        weight_divergence=0.20,
        weight_valuation=0.15,
        weight_token_value_capture=0.15,
        weight_market_strength=0.10,
        weight_tokenomics=0.10,
        weight_technical_setup=0.05,
        ref_fundamentals_growth=0.50,
        ref_market_momentum=0.50,
        ref_market_turnover=0.10,
        conf_weight_completeness=0.60,
        conf_weight_data_quality=0.40,
        confidence_band_moderate=0.40,
        confidence_band_high=0.70,
        status_moderate=0.45,
        status_strong=0.65,
    )


def _div_cfg() -> DivergenceConfig:
    return DivergenceConfig(
        scope="all",
        min_history_days=5.0,
        threshold=0.15,
        min_fundamentals_improvement=0.05,
        price_stagnant_ceiling=0.05,
        price_strong_threshold=0.50,
        weight_gap=0.7,
        weight_valuation=0.3,
    )


def _tok_cfg() -> TokenomicsConfig:
    return TokenomicsConfig(
        scope="all",
        ref_real_yield=0.10,
        weight_dilution=0.5,
        weight_value_capture=0.5,
    )


def _risk_cfg() -> RiskConfig:
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


def _seed_asset(session: Session, symbol: str, *, price_30d: float) -> Asset:
    a = Asset(symbol=symbol, name=f"{symbol} Coin")
    session.add(a)
    session.flush()
    # Fundamentals accelerating (7d run-rate > 30d run-rate).
    _obs(session, a.id, METRIC_FEES_7D_USD, 12.0)
    _obs(session, a.id, METRIC_FEES_30D_USD, 30.0)
    _obs(session, a.id, METRIC_REVENUE_30D_USD, 15.0)  # rev/fees 0.5
    _obs(session, a.id, METRIC_HOLDERS_REVENUE_30D_USD, 7.5)  # holders/rev 0.5
    _obs(session, a.id, METRIC_MARKET_CAP_USD, 5e8)
    _obs(session, a.id, METRIC_FDV_USD, 1e9)  # float ratio 0.5
    _obs(session, a.id, METRIC_TOTAL_VOLUME_USD, 5e7)  # turnover 10%
    _obs(session, a.id, METRIC_PRICE_CHANGE_PCT_30D, price_30d)
    return a


def _run_pipeline(session: Session) -> None:
    DivergenceService(session, _div_cfg()).run()
    TokenomicsService(session, _tok_cfg()).run()
    RiskService(session, _risk_cfg()).run()


def test_alpha_run_persists_three_separate_outputs(session: Session) -> None:
    a = _seed_asset(session, "AAA", price_30d=-15.0)  # price lagging → mispricing
    session.commit()
    _run_pipeline(session)

    summary = AlphaService(session, _alpha_cfg()).run()
    assert summary.status == "success"
    assert summary.analyzed_count == 1
    assert summary.scored_count == 1

    row = session.execute(
        select(AlphaScore).where(AlphaScore.asset_id == a.id)
    ).scalar_one()
    # Three separate outputs, each present and explainable.
    assert row.alpha_score is not None
    assert row.risk_score is not None
    assert row.confidence is not None
    assert row.alpha_band in ("strong", "moderate", "weak")
    assert row.risk_band in ("low", "moderate", "elevated", "high")
    assert row.confidence_band in ("high", "moderate", "low")
    # Valuation + technical unimplemented → completeness below 1.0, reflected honestly.
    assert row.model_completeness is not None and row.model_completeness < 1.0
    assert row.rank == 1
    assert row.status in (
        "high_interest",
        "potential_opportunity",
        "watch",
        "risk_elevated",
        "low_confidence",
        "thesis_weakening",
    )
    missing = row.evidence["missing_components"]
    assert "valuation" in missing and "technical_setup" in missing


def test_missing_upstream_runs_do_not_crash(session: Session) -> None:
    # No divergence/tokenomics/risk runs at all — alpha still runs, degrades cleanly.
    a = _seed_asset(session, "AAA", price_30d=10.0)
    session.commit()

    summary = AlphaService(session, _alpha_cfg()).run()
    assert summary.status == "success"
    row = session.execute(
        select(AlphaScore).where(AlphaScore.asset_id == a.id)
    ).scalar_one()
    # Only market_strength is available → a low-completeness, low-confidence score.
    assert row.model_completeness is not None and row.model_completeness <= 0.10
    assert row.confidence_band == "low"


def test_per_asset_isolation(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_asset(session, "AAA", price_30d=-15.0)
    _seed_asset(session, "BBB", price_30d=-10.0)
    session.commit()
    _run_pipeline(session)

    real = service_module.score
    calls = {"n": 0}

    def failing(components, context, config):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return real(components, context, config)

    monkeypatch.setattr(service_module, "score", failing)
    summary = AlphaService(session, _alpha_cfg()).run()
    assert summary.failed_count == 1
    assert (
        session.execute(select(func.count()).select_from(AlphaScore)).scalar_one() == 1
    )


@pytest.fixture()
def client(sqlite_engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    with factory() as seed:
        _seed_asset(seed, "AAA", price_30d=-15.0)
        seed.commit()
        _run_pipeline(seed)
        AlphaService(seed, _alpha_cfg()).run()

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


def test_api_scores(client: TestClient) -> None:
    resp = client.get("/scores")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    s = body[0]
    assert s["symbol"] == "AAA"
    # Three separate outputs surfaced side by side.
    assert s["alpha_score"] is not None
    assert s["risk_score"] is not None
    assert s["confidence"] is not None
    assert s["rank"] == 1
    assert s["model_completeness"] < 1.0
    assert len(s["components"]) == 7
    assert any(c["name"] == "valuation" and not c["available"] for c in s["components"])


def test_api_404_runs_and_no_buy(client: TestClient) -> None:
    assert client.get("/scores/99999").status_code == 404
    runs = client.get("/score-runs").json()
    assert len(runs) == 1 and runs[0]["scored_count"] == 1
    payload = json.dumps(client.get("/scores").json()).upper()
    for term in _FORBIDDEN:
        assert term not in payload


def test_api_empty_when_no_run(sqlite_engine: Engine) -> None:
    factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)

    def _override() -> Iterator[Session]:
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        assert c.get("/scores").json() == []
        assert c.get("/score-runs").json() == []
    app.dependency_overrides.clear()
