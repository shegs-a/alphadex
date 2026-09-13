"""Divergence engine — measure the economic-price gap, then interpret it.

This module separates two things AlphaDex must never conflate:

- **Divergence measurement** — the signed economic-price gap (``divergence_gap`` =
  fundamentals trend − price trend), its blended ``divergence_score`` (in [-1, 1],
  a component, **not** the Alpha Score), and ``signal_strength`` (its magnitude).
- **Opportunity interpretation** — the ``classification``, which reads the price
  *regime* to distinguish genuine divergence from repricing/momentum.

A positive gap does not by itself mean an undiscovered mispricing exists (see
ADR-005). ``data_quality`` is kept separate from signal strength and does not alter
the score. Missing core inputs yield ``insufficient_data`` with a ``None`` score —
never ``0`` (ADR-003). No blind BUY language (§10).
"""

from __future__ import annotations

from dataclasses import dataclass

from alphadex.divergence.config import DivergenceConfig
from alphadex.divergence.inputs import AssetSeries
from alphadex.divergence.trends import (
    METHOD_CROSS_TIME,
    METHOD_GROWTH_WINDOW,
    TrendResult,
    fundamentals_trend,
    price_trend,
    valuation_multiple,
    valuation_trend,
)

# Opportunity interpretations (see ADR-005).
CLASS_POTENTIAL_MISPRICING = "potential_mispricing"
CLASS_DIVERGENCE = "fundamental_divergence"
CLASS_REPRICING = "fundamental_repricing"
CLASS_MOMENTUM = "momentum"
CLASS_WEAKENING = "thesis_weakening"
CLASS_WATCH = "watch"
CLASS_INSUFFICIENT = "insufficient_data"

# Evidence-strength labels.
EVIDENCE_LOW = "low"
EVIDENCE_MEDIUM = "medium"


@dataclass(frozen=True)
class DivergenceOutcome:
    classification: str
    # Measurement (kept distinct — §10):
    divergence_score: float | None  # blended, signed, [-1, 1]
    divergence_gap: float | None  # raw fundamentals_trend - price_trend
    signal_strength: float | None  # magnitude of the measurement, [0, 1]
    fundamentals_trend: float | None
    price_trend: float | None
    valuation_trend: float | None
    valuation_level: float | None  # the multiple (informational)
    # Provenance / confidence (separate from signal strength):
    window: str | None
    method: str | None
    data_quality: float | None
    evidence: dict


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def _classify(ft: float, pt: float, gap: float, config: DivergenceConfig) -> str:
    """Interpret the measured gap by fundamentals materiality and price regime.

    Heuristic and configurable (ADR-005) — not a universal market truth.
    """
    improving = ft >= config.min_fundamentals_improvement
    declining = ft <= -config.min_fundamentals_improvement
    price_strong = pt >= config.price_strong_threshold
    price_flat_or_down = pt <= config.price_stagnant_ceiling

    if declining:
        return CLASS_WEAKENING
    if price_strong:
        # Price has already repriced strongly.
        return CLASS_REPRICING if improving else CLASS_MOMENTUM
    if improving and gap >= config.threshold:
        return CLASS_POTENTIAL_MISPRICING if price_flat_or_down else CLASS_DIVERGENCE
    return CLASS_WATCH


def evaluate(series: AssetSeries, config: DivergenceConfig) -> DivergenceOutcome:
    ft = fundamentals_trend(series, config)
    pt = price_trend(series, config)
    vt = valuation_trend(series, config)
    vmult = valuation_multiple(series)

    # Divergence is undefined without both a fundamentals and a price trend.
    if not ft.available or not pt.available:
        return DivergenceOutcome(
            classification=CLASS_INSUFFICIENT,
            divergence_score=None,
            divergence_gap=None,
            signal_strength=None,
            fundamentals_trend=ft.value,
            price_trend=pt.value,
            valuation_trend=vt.value,
            valuation_level=vmult,
            window=None,
            method=None,
            data_quality=0.0,
            evidence={
                "what_changed": "insufficient data to assess divergence",
                "why_now": "not enough fundamentals or price signal",
                "evidence_strength": EVIDENCE_LOW,
                "evidence_strength_reason": (
                    "required fundamentals and/or price trend unavailable"
                ),
                "what_supports": [],
                "what_contradicts": [],
                "what_invalidates": "n/a",
                "major_risk": "no reliable trend — do not infer a signal",
                "fundamentals_note": ft.note,
                "price_note": pt.note,
                "valuation_multiple": vmult,
            },
        )

    assert ft.value is not None and pt.value is not None
    gap_raw = ft.value - pt.value
    gap = _clamp(gap_raw)

    # Blended measurement (gap + optional cross-time valuation compression).
    components: list[tuple[float, float]] = [(config.weight_gap, gap)]
    val_signal: float | None = None
    if vt.available and vt.value is not None:
        val_signal = _clamp(-vt.value)  # falling multiple = positive divergence
        components.append((config.weight_valuation, val_signal))
    total_w = sum(w for w, _ in components)
    score = sum(w * v for w, v in components) / total_w
    signal_strength = _clamp(abs(score), 0.0, 1.0)

    uses_growth_window = METHOD_GROWTH_WINDOW in (ft.method, pt.method)
    method = (
        METHOD_CROSS_TIME
        if ft.method == METHOD_CROSS_TIME and pt.method == METHOD_CROSS_TIME
        else METHOD_GROWTH_WINDOW
    )
    window = "history" if method == METHOD_CROSS_TIME else "7d/30d"
    completeness = len(components) / 2.0
    data_quality = completeness * (0.6 if uses_growth_window else 1.0)

    classification = _classify(ft.value, pt.value, gap, config)

    evidence = _build_evidence(
        ft=ft,
        pt=pt,
        vt=vt,
        vmult=vmult,
        val_signal=val_signal,
        classification=classification,
        method=method,
    )

    return DivergenceOutcome(
        classification=classification,
        divergence_score=score,
        divergence_gap=gap_raw,
        signal_strength=signal_strength,
        fundamentals_trend=ft.value,
        price_trend=pt.value,
        valuation_trend=vt.value,
        valuation_level=vmult,
        window=window,
        method=method,
        data_quality=data_quality,
        evidence=evidence,
    )


def _fundamentals_phrase(ft: TrendResult) -> str:
    """Accurate wording that does not overclaim a long-term trend."""
    if ft.method == METHOD_GROWTH_WINDOW:
        return (
            f"recent 7-day fee run-rate is approximately {_pct(ft.value)} "
            "vs the 30-day baseline"
        )
    return f"fundamentals changed {_pct(ft.value)} vs an earlier observation"


def _build_evidence(
    *,
    ft: TrendResult,
    pt: TrendResult,
    vt: TrendResult,
    vmult: float | None,
    val_signal: float | None,
    classification: str,
    method: str,
) -> dict:
    supports: list[str] = []
    contradicts: list[str] = []

    if ft.value is not None and ft.value > 0:
        supports.append(f"fundamentals improving ({_fundamentals_phrase(ft)})")
    if pt.value is not None and pt.value <= 0:
        supports.append(f"price lagging ({_pct(pt.value)})")
    if val_signal is not None and val_signal > 0:
        supports.append("valuation multiple compressing over time")

    if classification in (CLASS_REPRICING, CLASS_MOMENTUM):
        contradicts.append(
            f"price has already repriced substantially ({_pct(pt.value)}) — "
            "the market may already recognize this"
        )
    elif pt.value is not None and pt.value > 0:
        contradicts.append(f"price already moved ({_pct(pt.value)})")
    if ft.value is not None and ft.value < 0:
        contradicts.append(f"fundamentals declining ({_pct(ft.value)})")
    if val_signal is not None and val_signal < 0:
        contradicts.append("valuation multiple expanding")

    if method == METHOD_GROWTH_WINDOW:
        evidence_strength = EVIDENCE_LOW
        evidence_strength_reason = (
            "signal relies on a single snapshot (7d vs 30d windows), "
            "not a persistent historical series"
        )
    else:
        evidence_strength = EVIDENCE_MEDIUM
        evidence_strength_reason = "signal derived from cross-time observations"

    what_changed = (
        f"Fundamentals: {_fundamentals_phrase(ft)}. Price {_pct(pt.value)} ({pt.note})."
    )
    why_now = (
        "based on cross-time history"
        if method == METHOD_CROSS_TIME
        else "based on provider 7d/30d growth windows (single snapshot)"
    )
    risks: list[str] = []
    if method == METHOD_GROWTH_WINDOW:
        risks.append(
            "7d/30d comparison is not proof of a long-term trend — "
            "confirm as history accumulates"
        )
    risks.append("fee growth may be incentive-driven, not organic")

    return {
        "what_changed": what_changed,
        "why_now": why_now,
        "evidence_strength": evidence_strength,
        "evidence_strength_reason": evidence_strength_reason,
        "what_supports": supports,
        "what_contradicts": contradicts,
        "what_invalidates": (
            "fundamentals reversing, or price catching up to fundamentals"
        ),
        "major_risk": "; ".join(risks),
        "valuation_multiple": vmult,
        "classification_note": classification.replace("_", " "),
    }
