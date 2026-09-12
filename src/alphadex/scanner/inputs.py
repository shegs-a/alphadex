"""Normalized scan inputs — the latest observation values a screen needs.

An ``ObsValue`` distinguishes a present value from explicit absence (ADR-003): a
metric with no usable value is never treated as ``0``. ``AssetSnapshot`` bundles the
specific metrics the screen reads for one asset.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ObsValue:
    """One metric's latest value for an asset, with its status and timestamp."""

    value: float | None
    status: str  # "OK", "NOT_AVAILABLE", "UNKNOWN", "NOT_APPLICABLE", or "MISSING"
    observed_at: datetime | None

    @property
    def present(self) -> bool:
        """True only when a real value is available (never for missing data)."""
        return self.value is not None and self.status == "OK"

    @classmethod
    def missing(cls) -> ObsValue:
        """No observation row exists at all for this metric."""
        return cls(value=None, status="MISSING", observed_at=None)


@dataclass(frozen=True)
class AssetSnapshot:
    """The screen's view of one asset — latest values for the metrics it uses."""

    asset_id: int
    market_cap: ObsValue
    volume_24h: ObsValue
    price_change_30d: ObsValue
    fees_30d: ObsValue
