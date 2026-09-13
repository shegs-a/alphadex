"""Risk configuration — factor weights, normalization refs, and band cut points."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from alphadex.config import Settings

_WEIGHT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class RiskConfig:
    scope: str
    ref_turnover: float
    ref_volatility: float
    ref_market_cap: float
    weight_liquidity: float
    weight_volatility: float
    weight_dilution: float
    weight_size: float
    band_moderate: float
    band_elevated: float
    band_high: float

    def __post_init__(self) -> None:
        total = (
            self.weight_liquidity
            + self.weight_volatility
            + self.weight_dilution
            + self.weight_size
        )
        if abs(total - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(f"Risk weights must sum to 1.0 (got {total})")
        if self.scope not in ("candidates", "all"):
            raise ValueError("risk scope must be 'candidates' or 'all'")
        if not (0.0 < self.band_moderate < self.band_elevated < self.band_high < 1.0):
            raise ValueError(
                "risk bands must satisfy 0 < moderate < elevated < high < 1"
            )
        if (
            self.ref_turnover <= 0
            or self.ref_volatility <= 0
            or self.ref_market_cap <= 0
        ):
            raise ValueError("risk normalization references must be positive")

    @classmethod
    def from_settings(cls, settings: Settings) -> RiskConfig:
        return cls(
            scope=settings.risk_scope,
            ref_turnover=settings.risk_ref_turnover,
            ref_volatility=settings.risk_ref_volatility,
            ref_market_cap=settings.risk_ref_market_cap,
            weight_liquidity=settings.risk_weight_liquidity,
            weight_volatility=settings.risk_weight_volatility,
            weight_dilution=settings.risk_weight_dilution,
            weight_size=settings.risk_weight_size,
            band_moderate=settings.risk_band_moderate,
            band_elevated=settings.risk_band_elevated,
            band_high=settings.risk_band_high,
        )

    def as_dict(self) -> dict:
        return asdict(self)
