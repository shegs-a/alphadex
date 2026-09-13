"""Divergence inputs — an asset's observation history for the metrics it needs.

Only present values are included (missing data is simply absent, never ``0`` —
ADR-003). ``AssetSeries`` exposes the latest point and a "prior" point far enough
back for a cross-time (Track B) trend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class ObsPoint:
    observed_at: datetime
    value: float

    @property
    def ts(self) -> datetime:
        return (
            self.observed_at
            if self.observed_at.tzinfo
            else self.observed_at.replace(tzinfo=UTC)
        )


@dataclass
class AssetSeries:
    """Per-metric observation history for one asset (each list sorted ascending)."""

    asset_id: int
    series: dict[str, list[ObsPoint]] = field(default_factory=dict)

    def latest(self, metric: str) -> ObsPoint | None:
        points = self.series.get(metric)
        return points[-1] if points else None

    def latest_value(self, metric: str) -> float | None:
        point = self.latest(metric)
        return point.value if point is not None else None

    def prior(self, metric: str, *, min_gap_days: float) -> ObsPoint | None:
        """The most recent point at least ``min_gap_days`` before the latest one."""
        points = self.series.get(metric)
        if not points or len(points) < 2:
            return None
        cutoff = points[-1].ts - timedelta(days=min_gap_days)
        candidates = [p for p in points[:-1] if p.ts <= cutoff]
        return candidates[-1] if candidates else None
