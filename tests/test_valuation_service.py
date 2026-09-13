"""Integration + API tests for the Valuation engine (SQLite), and the Alpha
integration (valuation graduating from not_implemented lifts model_completeness)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

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
    METRIC_TVL_USD,
)
from alphadex.marketdata.normalize import (
    METRIC_FDV_USD,
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
)
from alphadex.models import (
    AlphaScore,
    Asset,
    MetricObservation,
    ValuationAssessment,
    ValueStatus,
)
from alphadex.risk.config import RiskConfig
from alphadex.risk.service import RiskService
from alphadex.tokenomics.config import TokenomicsConfig
from alphadex.tokenomics.service import TokenomicsService
from alphadex.valuation import service as service_module
from alphadex.valuation.config import ValuationConfig
from alphadex.valuation.service import ValuationService

_FORBIDDEN = ("BUY", "GUARANTEED", "100% PUMP", "RISK FREE")


def _val_cfg() -> ValuationConfig:
    return ValuationConfig(
        scope="all",
        ref_price_to_fees=30.0,
        ref_price_to_revenue=40.0,
        ref_price_to_holders_revenue=20.0,
        ref_mcap_to_tvl=1.0,
        weight_fees=0.30,
        weight_revenue=0.30,
        weight_holders_revenue=0.25,
        weight_tvl=0.15,
        band_expensive=0.40,
        band_cheap=0.66,
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
    _obs(session, a.id, METRIC_MARKET_CAP_USD, 5e8)
    _obs(session, a.id, METRIC_FEES_30D_USD, 3e6)
    _obs(session, a.id, METRIC_REVENUE_30D_USD, 1.5e6)
    _obs(session, a.id, METRIC_HOLDERS_REVENUE_30D_USD, 7.5e5)
    _obs(session, a.id, METRIC_TVL_USD, 4e8)
    return a


def test_run_persists_score_multiples_and_rank(session: Session) -> None:
    a = _seed(session, "AAA")
    session.commit()

    summary = ValuationService(session, _val_cfg()).run()
    assert summary.status == "success"
    assert summary.analyzed_count == 1

    va = session.execute(
        select(ValuationAssessment).where(ValuationAssessment.asset_id == a.id)
    ).scalar_one()
    assert va.valuation_score is not None
    assert va.valuation_label in ("cheap", "fair", "expensive")
    # Distinct multiples all measurable here.
    assert va.price_to_fees is not None
    assert va.price_to_revenue is not None
    assert va.price_to_holders_revenue is not None
    assert va.mcap_to_tvl is not None
    assert va.data_completeness == 1.0
    assert va.rank == 1


def test_dilution_only_style_asset_is_unscored(session: Session) -> None:
    # An asset with market cap but no flows/TVL → no measurable multiple → unscored.
    a = Asset(symbol="ZZZ", name="ZZZ Coin")
    session.add(a)
    session.flush()
    _obs(session, a.id, METRIC_MARKET_CAP_USD, 1e9)
    session.commit()

    ValuationService(session, _val_cfg()).run()
    va = session.execute(
        select(ValuationAssessment).where(ValuationAssessment.asset_id == a.id)
    ).scalar_one()
    assert va.valuation_score is None
    assert va.valuation_label == "unknown"
    assert va.rank is None  # unscored → unranked


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
    summary = ValuationService(session, _val_cfg()).run()
    assert summary.failed_count == 1
    assert (
        session.execute(
            select(func.count()).select_from(ValuationAssessment)
        ).scalar_one()
        == 1
    )


def test_valuation_lifts_alpha_completeness(session: Session) -> None:
    # Seed an asset rich enough for all five built components, then run the full
    # pipeline including valuation. The Alpha valuation component must be available and
    # model_completeness must reach ~0.95 (only technical_setup remains unimplemented).
    a = _seed(session, "AAA")
    _obs(session, a.id, METRIC_FEES_7D_USD, 1.2e6)  # 7d run-rate for divergence
    _obs(session, a.id, METRIC_FDV_USD, 1e9)  # float ratio for tokenomics
    _obs(session, a.id, METRIC_TOTAL_VOLUME_USD, 5e7)  # market strength
    _obs(session, a.id, METRIC_PRICE_CHANGE_PCT_30D, -10.0)
    session.commit()

    DivergenceService(
        session,
        DivergenceConfig(
            scope="all",
            min_history_days=5.0,
            threshold=0.15,
            min_fundamentals_improvement=0.05,
            price_stagnant_ceiling=0.05,
            price_strong_threshold=0.50,
            weight_gap=0.7,
            weight_valuation=0.3,
        ),
    ).run()
    TokenomicsService(
        session,
        TokenomicsConfig(
            scope="all",
            ref_real_yield=0.10,
            weight_dilution=0.5,
            weight_value_capture=0.5,
        ),
    ).run()
    RiskService(
        session,
        RiskConfig(
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
        ),
    ).run()
    ValuationService(session, _val_cfg()).run()

    AlphaService(
        session,
        AlphaConfig(
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
        ),
    ).run()

    row = session.execute(
        select(AlphaScore).where(AlphaScore.asset_id == a.id)
    ).scalar_one()
    val_comp = next(c for c in row.components if c["name"] == "valuation")
    assert val_comp["available"] is True  # graduated from not_implemented
    tech_comp = next(c for c in row.components if c["name"] == "technical_setup")
    assert tech_comp["available"] is False  # still not implemented
    assert float(row.model_completeness) == pytest.approx(0.95)


@pytest.fixture()
def client(sqlite_engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    with factory() as seed:
        _seed(seed, "AAA")
        seed.commit()
        ValuationService(seed, _val_cfg()).run()

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


def test_api_valuations(client: TestClient) -> None:
    resp = client.get("/valuations")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    v = body[0]
    assert v["symbol"] == "AAA"
    assert v["valuation_score"] is not None
    assert v["price_to_fees"] is not None
    assert v["mcap_to_tvl"] is not None
    assert v["rank"] == 1


def test_api_404_runs_and_no_buy(client: TestClient) -> None:
    assert client.get("/valuations/99999").status_code == 404
    runs = client.get("/valuation-runs").json()
    assert len(runs) == 1 and runs[0]["analyzed_count"] == 1
    payload = json.dumps(client.get("/valuations").json()).upper()
    for term in _FORBIDDEN:
        assert term not in payload
