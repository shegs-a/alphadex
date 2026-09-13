"""Valuation configuration — references, blend weights, and label cut points.

Built from application ``Settings`` and validated (blend weights sum to 1.0, bands
ordered, references positive). Snapshotted onto each ``ValuationRun`` for
reproducibility (§10). References are **heuristic baselines** — "around here reads as
mid-range for this metric" — **not** universal fair values, and the weights are
documented defaults, never fitted to known outcomes (§10, no hindsight bias).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from alphadex.config import Settings

_WEIGHT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class ValuationConfig:
    scope: str
    # Heuristic mid-range references per multiple (the point mapped to 0.5
    # attractiveness). Baselines, NOT fair values.
    ref_price_to_fees: float
    ref_price_to_revenue: float
    ref_price_to_holders_revenue: float
    ref_mcap_to_tvl: float
    # Blend weights over the four multiples (must sum to 1.0).
    weight_fees: float
    weight_revenue: float
    weight_holders_revenue: float
    weight_tvl: float
    # Label cut points on the 0..1 attractiveness (0 < expensive < cheap < 1).
    band_expensive: float
    band_cheap: float

    def __post_init__(self) -> None:
        total = (
            self.weight_fees
            + self.weight_revenue
            + self.weight_holders_revenue
            + self.weight_tvl
        )
        if abs(total - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(f"Valuation blend weights must sum to 1.0 (got {total})")
        if self.scope not in ("candidates", "all"):
            raise ValueError("valuation scope must be 'candidates' or 'all'")
        if not (0.0 < self.band_expensive < self.band_cheap < 1.0):
            raise ValueError("valuation bands must satisfy 0 < expensive < cheap < 1")
        if (
            self.ref_price_to_fees <= 0
            or self.ref_price_to_revenue <= 0
            or self.ref_price_to_holders_revenue <= 0
            or self.ref_mcap_to_tvl <= 0
        ):
            raise ValueError("valuation references must be positive")

    @classmethod
    def from_settings(cls, settings: Settings) -> ValuationConfig:
        return cls(
            scope=settings.valuation_scope,
            ref_price_to_fees=settings.valuation_ref_price_to_fees,
            ref_price_to_revenue=settings.valuation_ref_price_to_revenue,
            ref_price_to_holders_revenue=settings.valuation_ref_price_to_holders_revenue,
            ref_mcap_to_tvl=settings.valuation_ref_mcap_to_tvl,
            weight_fees=settings.valuation_weight_fees,
            weight_revenue=settings.valuation_weight_revenue,
            weight_holders_revenue=settings.valuation_weight_holders_revenue,
            weight_tvl=settings.valuation_weight_tvl,
            band_expensive=settings.valuation_band_expensive,
            band_cheap=settings.valuation_band_cheap,
        )

    def as_dict(self) -> dict:
        return asdict(self)
