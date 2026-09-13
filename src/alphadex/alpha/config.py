"""Alpha Scoring configuration — the component weight vector, references, and bands.

Built from application ``Settings`` and validated (the full 7-component vector sums to
1.0, confidence weights sum to 1.0, bands and thresholds are ordered). Snapshotted onto
each ``AlphaRun`` for reproducibility (§10). Weights are the documented AGENTS.md
defaults — never fitted to known outcomes (§10, no hindsight bias).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from alphadex.config import Settings

_WEIGHT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class AlphaConfig:
    scope: str
    # Full 7-component target weight vector (sums to 1.0). Valuation and
    # technical_setup are not implemented yet; their weight is renormalized over the
    # available components and their absence lowers Confidence (never zero-filled).
    weight_economic_growth: float
    weight_divergence: float
    weight_valuation: float
    weight_token_value_capture: float
    weight_market_strength: float
    weight_tokenomics: float
    weight_technical_setup: float
    # Component normalization references.
    ref_fundamentals_growth: float
    ref_market_momentum: float
    ref_market_turnover: float
    # Confidence blend + bands.
    conf_weight_completeness: float
    conf_weight_data_quality: float
    confidence_band_moderate: float
    confidence_band_high: float
    # Decision-status Alpha thresholds.
    status_moderate: float
    status_strong: float

    def __post_init__(self) -> None:
        total = (
            self.weight_economic_growth
            + self.weight_divergence
            + self.weight_valuation
            + self.weight_token_value_capture
            + self.weight_market_strength
            + self.weight_tokenomics
            + self.weight_technical_setup
        )
        if abs(total - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(f"Alpha component weights must sum to 1.0 (got {total})")
        conf_total = self.conf_weight_completeness + self.conf_weight_data_quality
        if abs(conf_total - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(
                f"Alpha confidence weights must sum to 1.0 (got {conf_total})"
            )
        if self.scope not in ("candidates", "all"):
            raise ValueError("alpha scope must be 'candidates' or 'all'")
        if not (0.0 < self.confidence_band_moderate < self.confidence_band_high < 1.0):
            raise ValueError("confidence bands must satisfy 0 < moderate < high < 1")
        if not (0.0 < self.status_moderate < self.status_strong < 1.0):
            raise ValueError("status thresholds must satisfy 0 < moderate < strong < 1")
        if (
            self.ref_fundamentals_growth <= 0
            or self.ref_market_momentum <= 0
            or self.ref_market_turnover <= 0
        ):
            raise ValueError("alpha normalization references must be positive")

    @classmethod
    def from_settings(cls, settings: Settings) -> AlphaConfig:
        return cls(
            scope=settings.alpha_scope,
            weight_economic_growth=settings.alpha_weight_economic_growth,
            weight_divergence=settings.alpha_weight_divergence,
            weight_valuation=settings.alpha_weight_valuation,
            weight_token_value_capture=settings.alpha_weight_token_value_capture,
            weight_market_strength=settings.alpha_weight_market_strength,
            weight_tokenomics=settings.alpha_weight_tokenomics,
            weight_technical_setup=settings.alpha_weight_technical_setup,
            ref_fundamentals_growth=settings.alpha_ref_fundamentals_growth,
            ref_market_momentum=settings.alpha_ref_market_momentum,
            ref_market_turnover=settings.alpha_ref_market_turnover,
            conf_weight_completeness=settings.alpha_conf_weight_completeness,
            conf_weight_data_quality=settings.alpha_conf_weight_data_quality,
            confidence_band_moderate=settings.alpha_confidence_band_moderate,
            confidence_band_high=settings.alpha_confidence_band_high,
            status_moderate=settings.alpha_status_moderate,
            status_strong=settings.alpha_status_strong,
        )

    def as_dict(self) -> dict:
        return asdict(self)
