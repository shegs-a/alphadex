"""Tests for the screen configuration and its validation."""

from __future__ import annotations

import pytest

from alphadex.config import Settings
from alphadex.scanner.config import ScreenConfig


def _config(**overrides: object) -> ScreenConfig:
    base = dict(
        market_cap_min=1e7,
        market_cap_max=None,
        min_volume_24h=1e5,
        freshness_max_hours=48.0,
        require_fundamentals=False,
        ref_fees_30d=1e8,
        ref_volume_24h=1e9,
        weight_activity=0.4,
        weight_liquidity=0.3,
        weight_momentum=0.3,
    )
    base.update(overrides)
    return ScreenConfig(**base)  # type: ignore[arg-type]


def test_valid_weights_accepted() -> None:
    cfg = _config()
    assert cfg.weight_activity + cfg.weight_liquidity + cfg.weight_momentum == 1.0


def test_weights_not_summing_to_one_rejected() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        _config(weight_activity=0.5, weight_liquidity=0.3, weight_momentum=0.3)


def test_non_positive_reference_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        _config(ref_fees_30d=0.0)


def test_from_settings_round_trips_and_snapshots() -> None:
    settings = Settings(
        scan_weight_activity=0.5,
        scan_weight_liquidity=0.25,
        scan_weight_momentum=0.25,
    )
    cfg = ScreenConfig.from_settings(settings)
    assert cfg.weight_activity == 0.5
    snap = cfg.as_dict()
    assert snap["weight_activity"] == 0.5
    assert "market_cap_min" in snap
