"""Divergence configuration — thresholds and weights for one run.

Built from application ``Settings`` and validated (component weights sum to 1.0).
Snapshotted onto each ``DivergenceRun`` for reproducibility (§10).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from alphadex.config import Settings

_WEIGHT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class DivergenceConfig:
    """Immutable divergence-engine settings for one run."""

    scope: str
    min_history_days: float
    threshold: float
    min_fundamentals_improvement: float
    price_stagnant_ceiling: float
    price_strong_threshold: float
    weight_gap: float
    weight_valuation: float

    def __post_init__(self) -> None:
        total = self.weight_gap + self.weight_valuation
        if abs(total - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(
                f"Divergence weights must sum to 1.0 (gap+valuation = {total})"
            )
        if self.scope not in ("candidates", "all"):
            raise ValueError("divergence scope must be 'candidates' or 'all'")
        if not (self.price_stagnant_ceiling < self.price_strong_threshold):
            raise ValueError(
                "price_stagnant_ceiling must be below price_strong_threshold"
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> DivergenceConfig:
        return cls(
            scope=settings.divergence_scope,
            min_history_days=settings.divergence_min_history_days,
            threshold=settings.divergence_threshold,
            min_fundamentals_improvement=settings.divergence_min_fundamentals_improvement,
            price_stagnant_ceiling=settings.divergence_price_stagnant_ceiling,
            price_strong_threshold=settings.divergence_price_strong_threshold,
            weight_gap=settings.divergence_weight_gap,
            weight_valuation=settings.divergence_weight_valuation,
        )

    def as_dict(self) -> dict:
        return asdict(self)
