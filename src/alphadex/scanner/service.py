"""Opportunity Scanner service.

Runs one scan: load the universe's latest observations, evaluate the inclusion
gates and the preliminary Screen Score for each asset, classify and rank, and
persist a ``ScanRun`` with per-asset ``ScanResult`` rows (evidence included). No
external calls; no divergence/valuation/risk (later sprints). Missing data is
classified explicitly and never zero-scored (§9, §10, ADR-003).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from alphadex.logging import get_logger
from alphadex.models import ScanResult, ScanRun
from alphadex.scanner import repository
from alphadex.scanner.config import ScreenConfig
from alphadex.scanner.criteria import evaluate_gates
from alphadex.scanner.inputs import AssetSnapshot
from alphadex.scanner.score import compute_score

logger = get_logger(__name__)

STATUS_CANDIDATE = "candidate"
STATUS_WATCH = "watch"
STATUS_INSUFFICIENT = "insufficient_data"
STATUS_EXCLUDED = "excluded"


@dataclass(frozen=True)
class ScanSummary:
    run_id: int | None
    status: str
    universe_size: int
    candidate_count: int
    watch_count: int
    insufficient_count: int
    excluded_count: int


@dataclass
class _Evaluation:
    asset_id: int
    status: str
    passed: bool
    screen_score: float | None
    data_completeness: float | None
    reasons: dict


class ScanService:
    """Evaluates the universe against the screen and persists a scan."""

    def __init__(self, session: Session, config: ScreenConfig) -> None:
        self._session = session
        self._config = config

    def run(self) -> ScanSummary:
        started_at = datetime.now(UTC)
        run = ScanRun(
            status="running",
            started_at=started_at,
            config=self._config.as_dict(),
        )
        self._session.add(run)
        self._session.flush()

        snapshots = repository.load_snapshots(self._session)
        now = datetime.now(UTC)
        evaluations = [self._evaluate(s, now=now) for s in snapshots]

        # Rank scored results (candidate + watch) by Screen Score, descending.
        scored = [e for e in evaluations if e.screen_score is not None]
        scored.sort(key=lambda e: e.screen_score, reverse=True)  # type: ignore[arg-type,return-value]
        rank_by_asset = {e.asset_id: i + 1 for i, e in enumerate(scored)}

        counts = {
            STATUS_CANDIDATE: 0,
            STATUS_WATCH: 0,
            STATUS_INSUFFICIENT: 0,
            STATUS_EXCLUDED: 0,
        }
        for ev in evaluations:
            counts[ev.status] += 1
            self._session.add(
                ScanResult(
                    scan_run_id=run.id,
                    asset_id=ev.asset_id,
                    status=ev.status,
                    passed=ev.passed,
                    screen_score=ev.screen_score,
                    data_completeness=ev.data_completeness,
                    rank=rank_by_asset.get(ev.asset_id),
                    reasons=ev.reasons,
                )
            )

        run.status = "success"
        run.finished_at = datetime.now(UTC)
        run.universe_size = len(snapshots)
        run.candidate_count = counts[STATUS_CANDIDATE]
        self._session.commit()

        logger.info(
            "scan_complete",
            run_id=run.id,
            universe_size=len(snapshots),
            **{f"count_{k}": v for k, v in counts.items()},
        )
        return ScanSummary(
            run_id=run.id,
            status="success",
            universe_size=len(snapshots),
            candidate_count=counts[STATUS_CANDIDATE],
            watch_count=counts[STATUS_WATCH],
            insufficient_count=counts[STATUS_INSUFFICIENT],
            excluded_count=counts[STATUS_EXCLUDED],
        )

    def _evaluate(self, snapshot: AssetSnapshot, *, now: datetime) -> _Evaluation:
        gates = evaluate_gates(snapshot, self._config, now=now)
        score = compute_score(snapshot, self._config)
        reasons: dict = {
            "gates": [g.as_dict() for g in gates.gates],
            "signals": score.signals_as_dict(),
        }

        if not gates.passed:
            reasons["exclusion_reason"] = gates.exclusion_reason
            return _Evaluation(
                asset_id=snapshot.asset_id,
                status=STATUS_EXCLUDED,
                passed=False,
                screen_score=None,
                data_completeness=None,
                reasons=reasons,
            )

        has_fundamentals = snapshot.fees_30d.present
        if self._config.require_fundamentals and not has_fundamentals:
            reasons["note"] = "passed gates but fundamentals required and unavailable"
            return _Evaluation(
                asset_id=snapshot.asset_id,
                status=STATUS_INSUFFICIENT,
                passed=True,
                screen_score=None,
                data_completeness=score.completeness,
                reasons=reasons,
            )

        status = STATUS_CANDIDATE if has_fundamentals else STATUS_WATCH
        if status == STATUS_WATCH:
            reasons["note"] = "no fundamentals yet — held for watch"
        return _Evaluation(
            asset_id=snapshot.asset_id,
            status=status,
            passed=True,
            screen_score=score.score,
            data_completeness=score.completeness,
            reasons=reasons,
        )


__all__ = ["ScanService", "ScanSummary"]
