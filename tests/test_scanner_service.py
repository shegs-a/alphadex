"""Integration tests for the scan service (SQLite)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from alphadex.fundamentals.normalize import METRIC_FEES_30D_USD
from alphadex.marketdata.normalize import (
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
)
from alphadex.models import Asset, MetricObservation, ScanResult, ScanRun, ValueStatus
from alphadex.scanner.config import ScreenConfig
from alphadex.scanner.service import ScanService


def _cfg(**o: object) -> ScreenConfig:
    base = dict(
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
    base.update(o)
    return ScreenConfig(**base)  # type: ignore[arg-type]


def _asset(session: Session, symbol: str) -> Asset:
    asset = Asset(symbol=symbol, name=f"{symbol} Coin")
    session.add(asset)
    session.flush()
    return asset


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


def _market(
    session: Session, asset: Asset, *, mc: float, vol: float, chg: float
) -> None:
    _obs(session, asset.id, METRIC_MARKET_CAP_USD, mc)
    _obs(session, asset.id, METRIC_TOTAL_VOLUME_USD, vol)
    _obs(session, asset.id, METRIC_PRICE_CHANGE_PCT_30D, chg)


def _result(session: Session, run_id: int, asset_id: int) -> ScanResult:
    return session.execute(
        select(ScanResult).where(
            ScanResult.scan_run_id == run_id, ScanResult.asset_id == asset_id
        )
    ).scalar_one()


def test_scan_classifies_ranks_and_persists(session: Session) -> None:
    a = _asset(session, "AAA")  # full data → candidate
    _market(session, a, mc=1e9, vol=5e6, chg=10.0)
    _obs(session, a.id, METRIC_FEES_30D_USD, 5e6)
    b = _asset(session, "BBB")  # market only → watch
    _market(session, b, mc=8e8, vol=3e6, chg=5.0)
    c = _asset(session, "CCC")  # below floor → excluded
    _market(session, c, mc=1e6, vol=2e6, chg=1.0)
    session.commit()

    summary = ScanService(session, _cfg()).run()

    assert summary.status == "success"
    assert summary.universe_size == 3
    assert summary.candidate_count == 1
    assert summary.watch_count == 1
    assert summary.excluded_count == 1

    run = session.execute(select(ScanRun)).scalar_one()
    assert run.status == "success"
    assert run.config["weight_activity"] == 0.4  # config snapshotted

    ra, rb, rc = (
        _result(session, run.id, a.id),
        _result(session, run.id, b.id),
        _result(session, run.id, c.id),
    )
    assert ra.status == "candidate"
    assert rb.status == "watch"
    assert rc.status == "excluded"
    # Candidate + watch are scored and ranked; excluded is not.
    assert ra.screen_score is not None and ra.rank is not None
    assert rb.screen_score is not None and rb.rank is not None
    assert rc.screen_score is None and rc.rank is None


def test_excluded_asset_score_is_null_not_zero(session: Session) -> None:
    c = _asset(session, "CCC")
    _market(session, c, mc=1e6, vol=2e6, chg=1.0)  # below floor
    session.commit()

    run_id = ScanService(session, _cfg()).run().run_id
    assert run_id is not None
    rc = _result(session, run_id, c.id)
    # The key guarantee: an excluded asset is NULL, never a fake 0 score.
    assert rc.screen_score is None
    assert rc.data_completeness is None


def test_require_fundamentals_marks_insufficient(session: Session) -> None:
    b = _asset(session, "BBB")  # market only
    _market(session, b, mc=8e8, vol=3e6, chg=5.0)
    session.commit()

    summary = ScanService(session, _cfg(require_fundamentals=True)).run()
    assert summary.insufficient_count == 1
    assert summary.candidate_count == 0
    rb = _result(session, summary.run_id, b.id)  # type: ignore[arg-type]
    assert rb.status == "insufficient_data"
    assert rb.screen_score is None  # not ranked without required data


def test_rerun_creates_new_scan_keeping_history(session: Session) -> None:
    a = _asset(session, "AAA")
    _market(session, a, mc=1e9, vol=5e6, chg=10.0)
    _obs(session, a.id, METRIC_FEES_30D_USD, 5e6)
    session.commit()

    svc = ScanService(session, _cfg())
    svc.run()
    svc.run()
    runs = session.execute(select(ScanRun)).scalars().all()
    assert len(runs) == 2  # history preserved
