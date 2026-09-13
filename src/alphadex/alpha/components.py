"""Alpha component adapters — pure functions turning each engine's latest output into
a normalized **attractiveness contribution** in [0, 1] (higher = more attractive).

Each adapter reports whether it was **available**: a missing input yields
``available=False`` with ``contribution=None`` (never ``0`` — ADR-003), so the Alpha
Score is computed only over the components that are present (weights renormalized) and
the absence flows into Confidence (ADR-006). A *genuine* low reading (e.g. declining
fundamentals, a ``thesis_weakening`` divergence) is available with a real low
contribution — that is signal, not missing data.

One component is **not implemented yet** — Technical Setup. It always reports
``available=False`` and is absorbed by renormalization + Confidence, exactly like any
missing input, until it lands. Valuation **graduated** in Sprint 08 and now consumes
the Valuation engine's score (available when measured, unavailable when ``None``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from alphadex.alpha.config import AlphaConfig
from alphadex.divergence.engine import (
    CLASS_DIVERGENCE,
    CLASS_MOMENTUM,
    CLASS_POTENTIAL_MISPRICING,
    CLASS_REPRICING,
    CLASS_WATCH,
    CLASS_WEAKENING,
)
from alphadex.marketdata.normalize import (
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_TOTAL_VOLUME_USD,
)

# Component names (stable identifiers persisted in the components breakdown).
NAME_ECONOMIC_GROWTH = "economic_growth"
NAME_DIVERGENCE = "divergence"
NAME_VALUATION = "valuation"
NAME_TOKEN_VALUE_CAPTURE = "token_value_capture"
NAME_MARKET_STRENGTH = "market_strength"
NAME_TOKENOMICS = "tokenomics"
NAME_TECHNICAL_SETUP = "technical_setup"

# Not-implemented reason (distinguished from per-asset missing data).
REASON_NOT_IMPLEMENTED = "not_implemented"

# Opportunity attractiveness by divergence classification (ADR-005 → Alpha, ADR-006).
# The divergence *interpretation* feeds Alpha, never the raw gap — so repricing and
# momentum contribute little (the market has already moved) and a weakening thesis
# contributes nothing, avoiding the VVV trap and double-counting price. Missing /
# insufficient_data is not in this map → the component is unavailable.
_CLASS_ATTRACTIVENESS: dict[str, float] = {
    CLASS_POTENTIAL_MISPRICING: 1.0,
    CLASS_DIVERGENCE: 0.7,
    CLASS_WATCH: 0.3,
    CLASS_REPRICING: 0.2,
    CLASS_MOMENTUM: 0.1,
    CLASS_WEAKENING: 0.0,
}

Values = Mapping[str, float]


@dataclass(frozen=True)
class AlphaComponent:
    """One weighted attractiveness contribution to the Alpha Score."""

    name: str
    weight: float  # target weight from the full 7-component vector
    contribution: float | None  # normalized [0,1], or None when unavailable
    available: bool
    detail: str

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "weight": self.weight,
            "contribution": self.contribution,
            "available": self.available,
            "detail": self.detail,
        }


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _unavailable(name: str, weight: float, detail: str) -> AlphaComponent:
    return AlphaComponent(
        name=name, weight=weight, contribution=None, available=False, detail=detail
    )


def economic_growth(
    fundamentals_trend: float | None, config: AlphaConfig
) -> AlphaComponent:
    """Fundamentals trend (fee/revenue growth) normalized against a reference.

    Declining fundamentals are a *genuine* zero (available), not missing data.
    """
    if fundamentals_trend is None:
        return _unavailable(
            NAME_ECONOMIC_GROWTH,
            config.weight_economic_growth,
            "no fundamentals trend available",
        )
    contribution = _clamp(fundamentals_trend / config.ref_fundamentals_growth)
    return AlphaComponent(
        name=NAME_ECONOMIC_GROWTH,
        weight=config.weight_economic_growth,
        contribution=contribution,
        available=True,
        detail=f"fundamentals trend {fundamentals_trend * 100:+.1f}%",
    )


def divergence(
    classification: str | None,
    signal_strength: float | None,
    config: AlphaConfig,
) -> AlphaComponent:
    """Attractiveness from the divergence **classification** (ADR-005), not the gap."""
    if classification is None or classification not in _CLASS_ATTRACTIVENESS:
        return _unavailable(
            NAME_DIVERGENCE,
            config.weight_divergence,
            f"no usable divergence signal ({classification or 'none'})",
        )
    contribution = _CLASS_ATTRACTIVENESS[classification]
    strength = "n/a" if signal_strength is None else f"{signal_strength:.2f}"
    return AlphaComponent(
        name=NAME_DIVERGENCE,
        weight=config.weight_divergence,
        contribution=contribution,
        available=True,
        detail=f"{classification.replace('_', ' ')} (signal strength {strength})",
    )


def token_value_capture(
    value_capture_score: float | None, config: AlphaConfig
) -> AlphaComponent:
    """Token value capture from the Sprint 06 score (``None`` → unavailable)."""
    if value_capture_score is None:
        return _unavailable(
            NAME_TOKEN_VALUE_CAPTURE,
            config.weight_token_value_capture,
            "value capture not measured",
        )
    return AlphaComponent(
        name=NAME_TOKEN_VALUE_CAPTURE,
        weight=config.weight_token_value_capture,
        contribution=_clamp(value_capture_score),
        available=True,
        detail=f"value capture score {value_capture_score:.2f}",
    )


def market_strength(values: Values, config: AlphaConfig) -> AlphaComponent:
    """Market momentum (30d price change) + liquidity turnover, averaged.

    A small-weight component, distinct from divergence (which is classification-driven
    and does not use raw price) — so momentum is not double-counted as opportunity.
    """
    parts: list[float] = []
    notes: list[str] = []
    pct_30d = values.get(METRIC_PRICE_CHANGE_PCT_30D)
    if pct_30d is not None:
        parts.append(_clamp((pct_30d / 100.0) / config.ref_market_momentum))
        notes.append(f"30d momentum {pct_30d:+.1f}%")
    vol = values.get(METRIC_TOTAL_VOLUME_USD)
    mc = values.get(METRIC_MARKET_CAP_USD)
    if vol is not None and mc is not None and mc > 0:
        parts.append(_clamp((vol / mc) / config.ref_market_turnover))
        notes.append(f"turnover {(vol / mc) * 100:.1f}% of market cap")
    if not parts:
        return _unavailable(
            NAME_MARKET_STRENGTH,
            config.weight_market_strength,
            "no market momentum or liquidity data",
        )
    return AlphaComponent(
        name=NAME_MARKET_STRENGTH,
        weight=config.weight_market_strength,
        contribution=sum(parts) / len(parts),
        available=True,
        detail="; ".join(notes),
    )


def tokenomics(float_ratio: float | None, config: AlphaConfig) -> AlphaComponent:
    """Dilution/float health from the Sprint 06 ``float_ratio`` (higher = healthier)."""
    if float_ratio is None:
        return _unavailable(
            NAME_TOKENOMICS, config.weight_tokenomics, "float/supply data unavailable"
        )
    return AlphaComponent(
        name=NAME_TOKENOMICS,
        weight=config.weight_tokenomics,
        contribution=_clamp(float_ratio),
        available=True,
        detail=f"circulating is {float_ratio * 100:.0f}% of fully diluted",
    )


def valuation(valuation_score: float | None, config: AlphaConfig) -> AlphaComponent:
    """Relative valuation attractiveness from the Sprint 08 score.

    A *relative* cheapness reading (higher = cheaper vs the economics generated), never
    an intrinsic/fair-value claim; ``None`` when no multiple was measurable →
    unavailable (renormalized out, reflected in Confidence — ADR-006).
    """
    if valuation_score is None:
        return _unavailable(
            NAME_VALUATION, config.weight_valuation, "valuation not measured"
        )
    return AlphaComponent(
        name=NAME_VALUATION,
        weight=config.weight_valuation,
        contribution=_clamp(valuation_score),
        available=True,
        detail=f"relative valuation score {valuation_score:.2f}",
    )


def technical_setup(config: AlphaConfig) -> AlphaComponent:
    """Not implemented — the Technical Setup engine is a later sprint (see ADR-006)."""
    return _unavailable(
        NAME_TECHNICAL_SETUP, config.weight_technical_setup, REASON_NOT_IMPLEMENTED
    )


@dataclass(frozen=True)
class ComponentInputs:
    """The upstream fields each component adapter needs (extracted from ORM rows)."""

    fundamentals_trend: float | None = None
    divergence_classification: str | None = None
    divergence_signal_strength: float | None = None
    valuation_score: float | None = None
    value_capture_score: float | None = None
    float_ratio: float | None = None
    market_values: Values | None = None


def build_components(
    inputs: ComponentInputs, config: AlphaConfig
) -> list[AlphaComponent]:
    """Assemble all seven components in the canonical order."""
    return [
        economic_growth(inputs.fundamentals_trend, config),
        divergence(
            inputs.divergence_classification,
            inputs.divergence_signal_strength,
            config,
        ),
        valuation(inputs.valuation_score, config),
        token_value_capture(inputs.value_capture_score, config),
        market_strength(inputs.market_values or {}, config),
        tokenomics(inputs.float_ratio, config),
        technical_setup(config),
    ]
