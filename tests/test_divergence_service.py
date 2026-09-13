"""Integration tests for the divergence service (SQLite)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alphadex.divergence import service as service_module
from alphadex.divergence.config import DivergenceConfig
from alphadex.divergence.service import DivergenceService
from alphadex.fundamentals.normalize import METRIC_FEES_7D_USD, METRIC_FEES_30D_USD
from alphadex.marketdata.normalize import METRIC_PRICE_CHANGE_PCT_30D
from alphadex.models import (
    Asset,
    DivergenceRun,
    DivergenceSignal,
    MetricObservation,
    ScanResult,
    ScanRun,
    ValueStatus,
)


def _cfg(**o: object) -> DivergenceConfig:
    base = dict(
        scope="all",
        min_history_days=5.0,
        threshold=0.15,
        weakening_threshold=-0.15,
        min_fundamentals_improvement=0.05,
        weight_gap=0.7,
        weight_valuation=0.3,
    )
    base.update(o)
    return DivergenceConfig(**base)  # type: ignore[arg-type]


def _asset(session: Session, symbol: str) -> Asset:
    a = Asset(symbol=symbol, name=f"{symbol} Coin")
    session.add(a)
    session.flush()
    return a


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


def _diverging(session: Session, asset: Asset) -> None:
    _obs(session, asset.id, METRIC_FEES_7D_USD, 12.0)
    _obs(session, asset.id, METRIC_FEES_30D_USD, 30.0)
    _obs(session, asset.id, METRIC_PRICE_CHANGE_PCT_30D, -15.0)


def _signal(session: Session, run_id: int, asset_id: int) -> DivergenceSignal:
    return session.execute(
        select(DivergenceSignal).where(
            DivergenceSignal.divergence_run_id == run_id,
            DivergenceSignal.asset_id == asset_id,
        )
    ).scalar_one()


def test_run_persists_ranked_signals(session: Session) -> None:
    a = _asset(session, "AAA")
    _diverging(session, a)
    b = _asset(session, "BBB")
    _obs(session, b.id, METRIC_PRICE_CHANGE_PCT_30D, 5.0)  # insufficient (no fees)
    session.commit()

    summary = DivergenceService(session, _cfg()).run()

    assert summary.status == "success"
    assert summary.analyzed_count == 2
    assert summary.divergence_count == 1

    run = session.execute(select(DivergenceRun)).scalar_one()
    assert run.config["weight_gap"] == 0.7

    sa = _signal(session, run.id, a.id)
    sb = _signal(session, run.id, b.id)
    assert sa.classification == "fundamental_divergence"
    assert sa.divergence_score is not None and sa.rank == 1
    # Insufficient asset: null score, not ranked, never 0.
    assert sb.classification == "insufficient_data"
    assert sb.divergence_score is None and sb.rank is None


def test_scope_candidates_uses_latest_scan(session: Session) -> None:
    a = _asset(session, "AAA")
    _diverging(session, a)
    b = _asset(session, "BBB")
    _diverging(session, b)
    # A scan marking only A as candidate.
    scan = ScanRun(status="success", started_at=datetime.now(UTC), config={})
    session.add(scan)
    session.flush()
    session.add(
        ScanResult(scan_run_id=scan.id, asset_id=a.id, status="candidate", passed=True)
    )
    session.add(
        ScanResult(scan_run_id=scan.id, asset_id=b.id, status="excluded", passed=False)
    )
    session.commit()

    summary = DivergenceService(session, _cfg(scope="candidates")).run()
    assert summary.analyzed_count == 1  # only the candidate
    assert (
        session.execute(select(func.count()).select_from(DivergenceSignal)).scalar_one()
        == 1
    )


def test_per_asset_failure_isolated(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _asset(session, "AAA")
    _diverging(session, a)
    b = _asset(session, "BBB")
    _diverging(session, b)
    session.commit()

    real = service_module.evaluate

    def flaky(series, config):  # type: ignore[no-untyped-def]
        if series.asset_id == b.id:
            raise RuntimeError("boom")
        return real(series, config)

    monkeypatch.setattr(service_module, "evaluate", flaky)

    summary = DivergenceService(session, _cfg()).run()
    assert summary.analyzed_count == 1
    assert summary.failed_count == 1
    # Only A's signal persisted.
    assert (
        session.execute(select(func.count()).select_from(DivergenceSignal)).scalar_one()
        == 1
    )


def test_rerun_keeps_history(session: Session) -> None:
    a = _asset(session, "AAA")
    _diverging(session, a)
    session.commit()
    svc = DivergenceService(session, _cfg())
    svc.run()
    svc.run()
    assert (
        session.execute(select(func.count()).select_from(DivergenceRun)).scalar_one()
        == 2
    )
