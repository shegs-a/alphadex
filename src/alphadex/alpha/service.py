"""Alpha Scoring service.

Runs one scoring pass: select the assets to analyze (the Scanner's candidates by
default, §9), read each asset's latest divergence signal, tokenomics signal, risk
assessment, and market observations, assemble the components, compute the three
separate outputs (Alpha / Risk / Confidence) and a decision status, then persist an
``AlphaRun`` with per-asset ``AlphaScore`` rows. Per-asset failure isolation and a run
record (the Sprint 02–06 pattern). No external calls — it combines internal data only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from alphadex.alpha import repository
from alphadex.alpha.components import ComponentInputs, build_components
from alphadex.alpha.config import AlphaConfig
from alphadex.alpha.score import AlphaAssessment, UpstreamContext, score
from alphadex.analysis.base import load_latest_values, run_isolated, select_asset_ids
from alphadex.logging import get_logger
from alphadex.models import (
    AlphaRun,
    AlphaScore,
    DivergenceSignal,
    RiskAssessment,
    TokenomicsSignal,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class AlphaSummary:
    run_id: int | None
    status: str
    analyzed_count: int
    scored_count: int
    failed_count: int


def _num(v: object) -> float | None:
    return float(v) if v is not None else None  # type: ignore[arg-type]


class AlphaService:
    def __init__(self, session: Session, config: AlphaConfig) -> None:
        self._session = session
        self._config = config

    def run(self) -> AlphaSummary:
        run = AlphaRun(
            status="running",
            started_at=datetime.now(UTC),
            config=self._config.as_dict(),
        )
        self._session.add(run)
        self._session.flush()

        asset_ids = select_asset_ids(self._session, scope=self._config.scope)
        market_values = load_latest_values(
            self._session, asset_ids, repository.ALPHA_MARKET_METRICS
        )
        divergence_by = repository.load_latest_divergence(self._session, asset_ids)
        tokenomics_by = repository.load_latest_tokenomics(self._session, asset_ids)
        risk_by = repository.load_latest_risk(self._session, asset_ids)

        def work(asset_id: int) -> AlphaAssessment:
            assessment = self._assess(
                market_values.get(asset_id, {}),
                divergence_by.get(asset_id),
                tokenomics_by.get(asset_id),
                risk_by.get(asset_id),
            )
            self._persist(run.id, asset_id, assessment)
            return assessment

        ok, failed = run_isolated(
            self._session, asset_ids, work, event="alpha_asset_failed"
        )
        scored = sum(1 for _aid, a in ok if a.alpha_score is not None)
        self._assign_ranks(run.id)

        run.status = "success"
        run.finished_at = datetime.now(UTC)
        run.analyzed_count = len(asset_ids) - failed
        run.scored_count = scored
        self._session.commit()

        logger.info(
            "alpha_complete",
            run_id=run.id,
            analyzed=run.analyzed_count,
            scored=scored,
            failed=failed,
        )
        return AlphaSummary(
            run_id=run.id,
            status="success",
            analyzed_count=run.analyzed_count,
            scored_count=scored,
            failed_count=failed,
        )

    def _assess(
        self,
        market_values: dict[str, float],
        div: DivergenceSignal | None,
        tok: TokenomicsSignal | None,
        risk: RiskAssessment | None,
    ) -> AlphaAssessment:
        inputs = ComponentInputs(
            fundamentals_trend=_num(div.fundamentals_trend) if div else None,
            divergence_classification=div.classification if div else None,
            divergence_signal_strength=_num(div.signal_strength) if div else None,
            value_capture_score=_num(tok.value_capture_score) if tok else None,
            float_ratio=_num(tok.float_ratio) if tok else None,
            market_values=market_values,
        )
        components = build_components(inputs, self._config)
        context = UpstreamContext(
            divergence_classification=div.classification if div else None,
            divergence_quality=_num(div.data_quality) if div else None,
            tokenomics_quality=_num(tok.data_completeness) if tok else None,
            risk_score=_num(risk.risk_score) if risk else None,
            risk_band=risk.risk_band if risk else None,
            risk_quality=_num(risk.data_quality) if risk else None,
        )
        return score(components, context, self._config)

    def _persist(self, run_id: int, asset_id: int, assessment: AlphaAssessment) -> None:
        self._session.add(
            AlphaScore(
                alpha_run_id=run_id,
                asset_id=asset_id,
                alpha_score=assessment.alpha_score,
                alpha_band=assessment.alpha_band,
                risk_score=assessment.risk_score,
                risk_band=assessment.risk_band,
                confidence=assessment.confidence,
                confidence_band=assessment.confidence_band,
                model_completeness=assessment.model_completeness,
                status=assessment.status,
                components=assessment.components,
                evidence=assessment.evidence,
            )
        )
        self._session.flush()

    def _assign_ranks(self, run_id: int) -> None:
        """Rank scored assets by Alpha Score desc, ties broken by completeness desc."""
        scores = repository.get_scores(self._session, run_id, limit=100_000)
        scored = [s for s in scores if s.alpha_score is not None]
        scored.sort(
            key=lambda s: (
                -float(s.alpha_score),  # type: ignore[arg-type]
                -float(s.model_completeness or 0.0),
            )
        )
        for i, s in enumerate(scored):
            s.rank = i + 1
        self._session.flush()


__all__ = ["AlphaService", "AlphaSummary"]
