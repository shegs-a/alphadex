"""Divergence ingestion service.

Runs one divergence pass: select the assets to analyze (the Scanner's candidates by
default, §9), load their observation history, evaluate the engine per asset, rank the
signals, and persist a ``DivergenceRun`` with per-asset ``DivergenceSignal`` rows
(evidence included). Per-asset failure isolation and a run record (reuses the
Sprint 02–04 pattern). No external calls; a component, not the Alpha Score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from alphadex.divergence import repository
from alphadex.divergence.config import DivergenceConfig
from alphadex.divergence.engine import (
    CLASS_DIVERGENCE,
    CLASS_POTENTIAL_MISPRICING,
    DivergenceOutcome,
    evaluate,
)
from alphadex.divergence.inputs import AssetSeries
from alphadex.logging import get_logger
from alphadex.models import DivergenceRun, DivergenceSignal

logger = get_logger(__name__)

# The classifications counted as genuine divergence opportunities (not repricing/
# momentum/weakening/watch). Ranking is a separate, measurement-only concern.
_OPPORTUNITY_CLASSES = (CLASS_POTENTIAL_MISPRICING, CLASS_DIVERGENCE)


@dataclass(frozen=True)
class DivergenceSummary:
    run_id: int | None
    status: str
    analyzed_count: int
    divergence_count: int
    failed_count: int


class DivergenceService:
    def __init__(self, session: Session, config: DivergenceConfig) -> None:
        self._session = session
        self._config = config

    def run(self) -> DivergenceSummary:
        started_at = datetime.now(UTC)
        run = DivergenceRun(
            status="running",
            started_at=started_at,
            config=self._config.as_dict(),
        )
        self._session.add(run)
        self._session.flush()

        asset_ids = repository.select_asset_ids(self._session, scope=self._config.scope)
        series_by_asset = repository.load_series(self._session, asset_ids)

        analyzed = 0
        failed = 0
        divergences = 0
        outcomes: list[tuple[int, DivergenceOutcome]] = []
        for asset_id in asset_ids:
            series = series_by_asset.get(asset_id, AssetSeries(asset_id=asset_id))
            try:
                with self._session.begin_nested():
                    outcome = evaluate(series, self._config)
                    self._persist_signal(run.id, asset_id, outcome)
                outcomes.append((asset_id, outcome))
                analyzed += 1
                if outcome.classification in _OPPORTUNITY_CLASSES:
                    divergences += 1
            except Exception as exc:  # isolate one asset's failure (§8)
                failed += 1
                logger.error(
                    "divergence_asset_failed", asset_id=asset_id, error=str(exc)
                )

        self._assign_ranks(run.id)

        run.status = "success"
        run.finished_at = datetime.now(UTC)
        run.analyzed_count = analyzed
        run.divergence_count = divergences
        self._session.commit()

        logger.info(
            "divergence_complete",
            run_id=run.id,
            analyzed=analyzed,
            divergences=divergences,
            failed=failed,
        )
        return DivergenceSummary(
            run_id=run.id,
            status="success",
            analyzed_count=analyzed,
            divergence_count=divergences,
            failed_count=failed,
        )

    def _persist_signal(
        self, run_id: int, asset_id: int, outcome: DivergenceOutcome
    ) -> None:
        self._session.add(
            DivergenceSignal(
                divergence_run_id=run_id,
                asset_id=asset_id,
                classification=outcome.classification,
                divergence_score=outcome.divergence_score,
                divergence_gap=outcome.divergence_gap,
                signal_strength=outcome.signal_strength,
                fundamentals_trend=outcome.fundamentals_trend,
                price_trend=outcome.price_trend,
                valuation_trend=outcome.valuation_trend,
                valuation_level=outcome.valuation_level,
                window=outcome.window,
                method=outcome.method,
                data_quality=outcome.data_quality,
                evidence=outcome.evidence,
            )
        )
        self._session.flush()

    def _assign_ranks(self, run_id: int) -> None:
        """Rank scored signals by divergence score, descending."""
        signals = repository.get_signals(self._session, run_id, limit=100_000)
        scored = [s for s in signals if s.divergence_score is not None]
        scored.sort(key=lambda s: s.divergence_score, reverse=True)  # type: ignore[arg-type,return-value]
        for i, signal in enumerate(scored):
            signal.rank = i + 1
        self._session.flush()


__all__ = ["DivergenceService", "DivergenceSummary"]
