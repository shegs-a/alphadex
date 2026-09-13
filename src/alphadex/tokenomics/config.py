"""Tokenomics configuration — weights and references for one run."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from alphadex.config import Settings

_WEIGHT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class TokenomicsConfig:
    scope: str
    ref_real_yield: float
    weight_dilution: float
    weight_value_capture: float

    def __post_init__(self) -> None:
        total = self.weight_dilution + self.weight_value_capture
        if abs(total - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(
                f"Tokenomics weights must sum to 1.0 (dilution+value_capture = {total})"
            )
        if self.scope not in ("candidates", "all"):
            raise ValueError("tokenomics scope must be 'candidates' or 'all'")
        if self.ref_real_yield <= 0:
            raise ValueError("ref_real_yield must be positive")

    @classmethod
    def from_settings(cls, settings: Settings) -> TokenomicsConfig:
        return cls(
            scope=settings.tokenomics_scope,
            ref_real_yield=settings.tokenomics_ref_real_yield,
            weight_dilution=settings.tokenomics_weight_dilution,
            weight_value_capture=settings.tokenomics_weight_value_capture,
        )

    def as_dict(self) -> dict:
        return asdict(self)
