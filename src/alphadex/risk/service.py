"""Risk ingestion service — a separate Risk output over the candidates (§10)."""

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
from alphadex.models import RiskAssessment, RiskRun
from alphadex.risk.config import RiskConfig
from alphadex.risk.repository import RISK_METRICS
from alphadex.risk.score import RiskOutcome, evaluate

logger = get_logger(__name__)


@dataclass(frozen=True)
class RiskSummary:
    run_id: int | None
    status: str
    analyzed_count: int
    failed_count: int


class RiskService:
    def __init__(self, session: Session, config: RiskConfig) -> None:
        self._session = session
        self._config = config

    def run(self) -> RiskSummary:
        run = RiskRun(
            status="running",
            started_at=datetime.now(UTC),
            config=self._config.as_dict(),
        )
        self._session.add(run)
        self._session.flush()

        asset_ids = select_asset_ids(self._session, scope=self._config.scope)
        values_by_asset = load_latest_values(self._session, asset_ids, RISK_METRICS)

        def work(asset_id: int) -> RiskOutcome:
            outcome = evaluate(values_by_asset.get(asset_id, {}), self._config)
            self._persist(run.id, asset_id, outcome)
            return outcome

        _ok, failed = run_isolated(
            self._session, asset_ids, work, event="risk_asset_failed"
        )
        self._assign_ranks(run.id)

        run.status = "success"
        run.finished_at = datetime.now(UTC)
        run.analyzed_count = len(asset_ids) - failed
        self._session.commit()

        logger.info(
            "risk_complete", run_id=run.id, analyzed=run.analyzed_count, failed=failed
        )
        return RiskSummary(
            run_id=run.id,
            status="success",
            analyzed_count=run.analyzed_count,
            failed_count=failed,
        )

    def _persist(self, run_id: int, asset_id: int, outcome: RiskOutcome) -> None:
        self._session.add(
            RiskAssessment(
                risk_run_id=run_id,
                asset_id=asset_id,
                risk_score=outcome.risk_score,
                risk_band=outcome.risk_band,
                liquidity_risk=outcome.liquidity_risk,
                volatility_risk=outcome.volatility_risk,
                dilution_risk=outcome.dilution_risk,
                size_risk=outcome.size_risk,
                concentration_risk=outcome.concentration_risk,
                data_quality=outcome.data_quality,
                evidence=outcome.evidence,
            )
        )
        self._session.flush()

    def _assign_ranks(self, run_id: int) -> None:
        """Order by risk score, highest first (riskiest = rank 1). Not an opportunity
        ranking — high risk is a warning, not a recommendation."""
        from alphadex.risk import repository

        rows = repository.get_assessments(self._session, run_id, limit=100_000)
        scored = [a for a in rows if a.risk_score is not None]
        scored.sort(key=lambda a: a.risk_score, reverse=True)  # type: ignore[arg-type,return-value]
        for i, assessment in enumerate(scored):
            assessment.rank = i + 1
        self._session.flush()


__all__ = ["RiskService", "RiskSummary"]
