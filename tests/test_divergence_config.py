"""Tests for divergence configuration validation."""

from __future__ import annotations

import pytest

from alphadex.config import Settings
from alphadex.divergence.config import DivergenceConfig


def _cfg(**o: object) -> DivergenceConfig:
    base = dict(
        scope="candidates",
        min_history_days=5.0,
        threshold=0.15,
        min_fundamentals_improvement=0.05,
        price_stagnant_ceiling=0.05,
        price_strong_threshold=0.50,
        weight_gap=0.7,
        weight_valuation=0.3,
    )
    base.update(o)
    return DivergenceConfig(**base)  # type: ignore[arg-type]


def test_valid_config_accepted() -> None:
    assert _cfg().weight_gap == 0.7


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        _cfg(weight_gap=0.6, weight_valuation=0.3)


def test_invalid_scope_rejected() -> None:
    with pytest.raises(ValueError, match="scope"):
        _cfg(scope="everything")


def test_price_ceiling_must_be_below_strong_threshold() -> None:
    with pytest.raises(ValueError, match="price_stagnant_ceiling"):
        _cfg(price_stagnant_ceiling=0.6, price_strong_threshold=0.5)


def test_from_settings() -> None:
    cfg = DivergenceConfig.from_settings(Settings(divergence_scope="all"))
    assert cfg.scope == "all"
    assert "weight_gap" in cfg.as_dict()
