"""Valuation ingestion service — relative valuation over the candidates.

Selects the assets to analyze (the Scanner's candidates by default, §9), loads their
latest market/fundamental values, evaluates the multiples per asset, ranks by relative
attractiveness (a component ranking, not an opportunity ranking), and persists a
``ValuationRun`` with per-asset ``ValuationAssessment`` rows. Per-asset SAVEPOINT
isolation and a run record (the Sprint 02–07 pattern). No external calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from alphadex.analysis.base import load_latest_values, run_isolated, select_asset_ids
from alphadex.logging import get_logger
from alphadex.models import ValuationAssessment, ValuationRun
from alphadex.valuation.config import ValuationConfig
from alphadex.valuation.repository import VALUATION_METRICS
from alphadex.valuation.score import ValuationOutcome, evaluate

logger = get_logger(__name__)


@dataclass(frozen=True)
class ValuationSummary:
    run_id: int | None
    status: str
    analyzed_count: int
    failed_count: int


class ValuationService:
    def __init__(self, session: Session, config: ValuationConfig) -> None:
        self._session = session
        self._config = config

    def run(self) -> ValuationSummary:
        run = ValuationRun(
            status="running",
            started_at=datetime.now(UTC),
            config=self._config.as_dict(),
        )
        self._session.add(run)
        self._session.flush()

        asset_ids = select_asset_ids(self._session, scope=self._config.scope)
        values_by_asset = load_latest_values(
            self._session, asset_ids, VALUATION_METRICS
        )

        def work(asset_id: int) -> ValuationOutcome:
            outcome = evaluate(values_by_asset.get(asset_id, {}), self._config)
            self._persist(run.id, asset_id, outcome)
            return outcome

        _ok, failed = run_isolated(
            self._session, asset_ids, work, event="valuation_asset_failed"
        )
        self._assign_ranks(run.id)

        run.status = "success"
        run.finished_at = datetime.now(UTC)
        run.analyzed_count = len(asset_ids) - failed
        self._session.commit()

        logger.info(
            "valuation_complete",
            run_id=run.id,
            analyzed=run.analyzed_count,
            failed=failed,
        )
        return ValuationSummary(
            run_id=run.id,
            status="success",
            analyzed_count=run.analyzed_count,
            failed_count=failed,
        )

    def _persist(self, run_id: int, asset_id: int, outcome: ValuationOutcome) -> None:
        self._session.add(
            ValuationAssessment(
                valuation_run_id=run_id,
                asset_id=asset_id,
                valuation_score=outcome.valuation_score,
                valuation_label=outcome.valuation_label,
                price_to_fees=outcome.price_to_fees,
                price_to_revenue=outcome.price_to_revenue,
                price_to_holders_revenue=outcome.price_to_holders_revenue,
                mcap_to_tvl=outcome.mcap_to_tvl,
                data_completeness=outcome.data_completeness,
                evidence=outcome.evidence,
            )
        )
        self._session.flush()

    def _assign_ranks(self, run_id: int) -> None:
        from alphadex.valuation import repository

        assessments = repository.get_assessments(self._session, run_id, limit=100_000)
        scored = [a for a in assessments if a.valuation_score is not None]
        scored.sort(key=lambda a: a.valuation_score, reverse=True)  # type: ignore[arg-type,return-value]
        for i, assessment in enumerate(scored):
            assessment.rank = i + 1
        self._session.flush()


__all__ = ["ValuationService", "ValuationSummary"]
