"""Screen configuration — the thresholds and weights a scan uses.

Built from application ``Settings`` and validated (weights must sum to 1.0). The
config is snapshotted onto each ``ScanRun`` so results are reproducible (§10).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from alphadex.config import Settings

_WEIGHT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class ScreenConfig:
    """Immutable screen definition for one scan."""

    market_cap_min: float
    market_cap_max: float | None
    min_volume_24h: float
    freshness_max_hours: float
    require_fundamentals: bool
    ref_fees_30d: float
    ref_volume_24h: float
    weight_activity: float
    weight_liquidity: float
    weight_momentum: float

    def __post_init__(self) -> None:
        total = self.weight_activity + self.weight_liquidity + self.weight_momentum
        if abs(total - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(
                "Screen Score weights must sum to 1.0 "
                f"(activity+liquidity+momentum = {total})"
            )
        if self.ref_fees_30d <= 0 or self.ref_volume_24h <= 0:
            raise ValueError("Normalization references must be positive")

    @classmethod
    def from_settings(cls, settings: Settings) -> ScreenConfig:
        return cls(
            market_cap_min=settings.scan_market_cap_min,
            market_cap_max=settings.scan_market_cap_max,
            min_volume_24h=settings.scan_min_volume_24h,
            freshness_max_hours=settings.scan_freshness_max_hours,
            require_fundamentals=settings.scan_require_fundamentals,
            ref_fees_30d=settings.scan_ref_fees_30d,
            ref_volume_24h=settings.scan_ref_volume_24h,
            weight_activity=settings.scan_weight_activity,
            weight_liquidity=settings.scan_weight_liquidity,
            weight_momentum=settings.scan_weight_momentum,
        )

    def as_dict(self) -> dict:
        """Serializable snapshot for persistence on the scan run."""
        return asdict(self)
