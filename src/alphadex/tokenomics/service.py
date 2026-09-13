"""Tokenomics ingestion service — Token Value Capture over the candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from alphadex.analysis.base import (
    load_latest_values,
    run_isolated,
    select_asset_ids,
)
from alphadex.logging import get_logger
from alphadex.models import TokenomicsRun, TokenomicsSignal
from alphadex.tokenomics.config import TokenomicsConfig
from alphadex.tokenomics.repository import TOKENOMICS_METRICS
from alphadex.tokenomics.score import TokenomicsOutcome, evaluate

logger = get_logger(__name__)


@dataclass(frozen=True)
class TokenomicsSummary:
    run_id: int | None
    status: str
    analyzed_count: int
    failed_count: int


class TokenomicsService:
    def __init__(self, session: Session, config: TokenomicsConfig) -> None:
        self._session = session
        self._config = config

    def run(self) -> TokenomicsSummary:
        run = TokenomicsRun(
            status="running",
            started_at=datetime.now(UTC),
            config=self._config.as_dict(),
        )
        self._session.add(run)
        self._session.flush()

        asset_ids = select_asset_ids(self._session, scope=self._config.scope)
        values_by_asset = load_latest_values(
            self._session, asset_ids, TOKENOMICS_METRICS
        )

        def work(asset_id: int) -> TokenomicsOutcome:
            outcome = evaluate(values_by_asset.get(asset_id, {}), self._config)
            self._persist(run.id, asset_id, outcome)
            return outcome

        _ok, failed = run_isolated(
            self._session, asset_ids, work, event="tokenomics_asset_failed"
        )
        self._assign_ranks(run.id)

        run.status = "success"
        run.finished_at = datetime.now(UTC)
        run.analyzed_count = len(asset_ids) - failed
        self._session.commit()

        logger.info(
            "tokenomics_complete",
            run_id=run.id,
            analyzed=run.analyzed_count,
            failed=failed,
        )
        return TokenomicsSummary(
            run_id=run.id,
            status="success",
            analyzed_count=run.analyzed_count,
            failed_count=failed,
        )

    def _persist(self, run_id: int, asset_id: int, outcome: TokenomicsOutcome) -> None:
        self._session.add(
            TokenomicsSignal(
                tokenomics_run_id=run_id,
                asset_id=asset_id,
                value_capture_score=outcome.value_capture_score,
                value_capture_label=outcome.value_capture_label,
                float_ratio=outcome.float_ratio,
                revenue_to_fees=outcome.revenue_to_fees,
                holders_to_revenue=outcome.holders_to_revenue,
                real_yield=outcome.real_yield,
                data_completeness=outcome.data_completeness,
                evidence=outcome.evidence,
            )
        )
        self._session.flush()

    def _assign_ranks(self, run_id: int) -> None:
        from alphadex.tokenomics import repository

        signals = repository.get_signals(self._session, run_id, limit=100_000)
        scored = [s for s in signals if s.value_capture_score is not None]
        scored.sort(key=lambda s: s.value_capture_score, reverse=True)  # type: ignore[arg-type,return-value]
        for i, signal in enumerate(scored):
            signal.rank = i + 1
        self._session.flush()


__all__ = ["TokenomicsService", "TokenomicsSummary"]
