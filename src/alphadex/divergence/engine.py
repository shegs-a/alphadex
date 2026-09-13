"""Divergence engine — turn trends into a classified, explainable signal.

Combines the fundamentals and price/valuation trends into a signed divergence score
(a component in [-1, 1], **not** the Alpha Score), classifies the signal, and
assembles evidence answering the §10 questions. A missing core input yields
``insufficient_data`` with a ``None`` score — never ``0`` (ADR-003). Output language
is constrained to *fundamental divergence / watch / thesis weakening / risk* — no
blind BUY language (§10).
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

CLASS_DIVERGENCE = "fundamental_divergence"
CLASS_WATCH = "watch"
CLASS_WEAKENING = "thesis_weakening"
CLASS_INSUFFICIENT = "insufficient_data"


@dataclass(frozen=True)
class DivergenceOutcome:
    classification: str
    divergence_score: float | None
    fundamentals_trend: float | None
    price_trend: float | None
    valuation_trend: float | None
    window: str | None
    method: str | None
    data_quality: float | None
    evidence: dict


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def evaluate(series: AssetSeries, config: DivergenceConfig) -> DivergenceOutcome:
    ft = fundamentals_trend(series, config)
    pt = price_trend(series, config)
    vt = valuation_trend(series, config)
    vmult = valuation_multiple(series)

    # The gap between fundamentals improvement and price recognition is the core.
    if not ft.available or not pt.available:
        return DivergenceOutcome(
            classification=CLASS_INSUFFICIENT,
            divergence_score=None,
            fundamentals_trend=ft.value,
            price_trend=pt.value,
            valuation_trend=vt.value,
            window=None,
            method=None,
            data_quality=0.0,
            evidence={
                "what_changed": "insufficient data to assess divergence",
                "why_now": "not enough fundamentals or price signal",
                "what_supports": [],
                "what_contradicts": [],
                "what_invalidates": "n/a",
                "major_risk": "no reliable trend — do not infer a signal",
                "fundamentals_note": ft.note,
                "price_note": pt.note,
            },
        )

    gap = _clamp(ft.value - pt.value)  # type: ignore[operator]

    components: list[tuple[float, float]] = [(config.weight_gap, gap)]
    val_signal: float | None = None
    if vt.available:
        # Falling multiple while fundamentals rise = positive divergence.
        val_signal = _clamp(-vt.value)  # type: ignore[operator]
        components.append((config.weight_valuation, val_signal))

    total_w = sum(w for w, _ in components)
    score = sum(w * v for w, v in components) / total_w

    uses_growth_window = METHOD_GROWTH_WINDOW in (ft.method, pt.method)
    method = (
        METHOD_CROSS_TIME
        if ft.method == METHOD_CROSS_TIME and pt.method == METHOD_CROSS_TIME
        else METHOD_GROWTH_WINDOW
    )
    window = "history" if method == METHOD_CROSS_TIME else "7d/30d"
    completeness = len(components) / 2.0
    data_quality = completeness * (0.6 if uses_growth_window else 1.0)

    fundamentals_improving = ft.value >= config.min_fundamentals_improvement  # type: ignore[operator]
    fundamentals_declining = ft.value <= -config.min_fundamentals_improvement  # type: ignore[operator]

    if fundamentals_declining or score <= config.weakening_threshold:
        classification = CLASS_WEAKENING
    elif score >= config.threshold and fundamentals_improving:
        classification = CLASS_DIVERGENCE
    else:
        classification = CLASS_WATCH

    evidence = _build_evidence(
        ft=ft,
        pt=pt,
        vt=vt,
        vmult=vmult,
        val_signal=val_signal,
        classification=classification,
        method=method,
        data_quality=data_quality,
    )

    return DivergenceOutcome(
        classification=classification,
        divergence_score=score,
        fundamentals_trend=ft.value,
        price_trend=pt.value,
        valuation_trend=vt.value,
        window=window,
        method=method,
        data_quality=data_quality,
        evidence=evidence,
    )


def _build_evidence(
    *,
    ft: TrendResult,
    pt: TrendResult,
    vt: TrendResult,
    vmult: float | None,
    val_signal: float | None,
    classification: str,
    method: str,
    data_quality: float,
) -> dict:
    supports: list[str] = []
    contradicts: list[str] = []

    if ft.value is not None and ft.value > 0:
        supports.append(f"fundamentals improving ({_pct(ft.value)}, {ft.note})")
    if pt.value is not None and pt.value <= 0:
        supports.append(f"price lagging ({_pct(pt.value)})")
    if val_signal is not None and val_signal > 0:
        supports.append("valuation multiple compressing over time")

    if pt.value is not None and pt.value > 0:
        contradicts.append(f"price already moved ({_pct(pt.value)})")
    if ft.value is not None and ft.value < 0:
        contradicts.append(f"fundamentals declining ({_pct(ft.value)})")
    if val_signal is not None and val_signal < 0:
        contradicts.append("valuation multiple expanding")

    what_changed = (
        f"Fundamentals {_pct(ft.value)} ({ft.note}); "
        f"price {_pct(pt.value)} ({pt.note})."
    )
    why_now = (
        "based on cross-time history"
        if method == METHOD_CROSS_TIME
        else "based on provider 7d/30d growth windows (single snapshot)"
    )
    risks: list[str] = []
    if method == METHOD_GROWTH_WINDOW:
        risks.append("single-snapshot proxy — confirm as history accumulates")
    if data_quality < 0.6:
        risks.append("low data quality")
    risks.append("fee growth may be incentive-driven, not organic")

    return {
        "what_changed": what_changed,
        "why_now": why_now,
        "what_supports": supports,
        "what_contradicts": contradicts,
        "what_invalidates": (
            "fundamentals reversing, or price catching up to fundamentals"
        ),
        "major_risk": "; ".join(risks),
        "valuation_multiple": vmult,
        "classification_note": classification.replace("_", " "),
    }
