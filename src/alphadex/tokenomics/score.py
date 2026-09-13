"""Token Value Capture score — a component, not the Alpha Score.

Blends a **dilution** component (float ratio) and a **value-capture** component
(does revenue reach holders) over available inputs, renormalizing weights over what
is present so a missing input lowers completeness and never inflates the score
(ADR-003/ADR-005 discipline). ``data_completeness`` is kept separate from the score.
"""

from __future__ import annotations

from dataclasses import dataclass

from alphadex.tokenomics.config import TokenomicsConfig
from alphadex.tokenomics.signals import (
    Values,
    float_ratio,
    holders_to_revenue,
    real_yield,
    revenue_to_fees,
)

LABEL_STRONG = "strong"
LABEL_MODERATE = "moderate"
LABEL_WEAK = "weak"
LABEL_UNKNOWN = "unknown"


@dataclass(frozen=True)
class TokenomicsOutcome:
    value_capture_score: float | None
    value_capture_label: str
    float_ratio: float | None
    revenue_to_fees: float | None
    holders_to_revenue: float | None
    real_yield: float | None
    data_completeness: float
    evidence: dict


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def evaluate(values: Values, config: TokenomicsConfig) -> TokenomicsOutcome:
    fr = float_ratio(values)
    rtf = revenue_to_fees(values)
    htr = holders_to_revenue(values)
    ry = real_yield(values)

    # Value-capture component: mean of available sub-signals (normalized).
    vc_parts: list[float] = []
    if rtf is not None:
        vc_parts.append(rtf)
    if htr is not None:
        vc_parts.append(htr)
    if ry is not None:
        vc_parts.append(min(1.0, ry / config.ref_real_yield))
    value_capture = _mean(vc_parts) if vc_parts else None

    # Blend dilution (float ratio) and value capture over present components.
    components: list[tuple[float, float]] = []
    if fr is not None:
        components.append((config.weight_dilution, fr))
    if value_capture is not None:
        components.append((config.weight_value_capture, value_capture))

    if components:
        total_w = sum(w for w, _ in components)
        score: float | None = sum(w * v for w, v in components) / total_w
    else:
        score = None

    # Completeness over the four raw sub-signals (separate from the score).
    present = sum(1 for x in (fr, rtf, htr, ry) if x is not None)
    completeness = present / 4.0

    # The label is about *value capture*: if no value-capture input is available, we
    # cannot claim it is strong/weak just from low dilution — say "unknown" (the
    # score still records the dilution measurement). Poor data never masquerades as a
    # strong signal (ADR-005 discipline).
    label = _label(score) if value_capture is not None else LABEL_UNKNOWN
    evidence = _build_evidence(fr=fr, rtf=rtf, htr=htr, ry=ry, score=score, label=label)
    return TokenomicsOutcome(
        value_capture_score=score,
        value_capture_label=label,
        float_ratio=fr,
        revenue_to_fees=rtf,
        holders_to_revenue=htr,
        real_yield=ry,
        data_completeness=completeness,
        evidence=evidence,
    )


def _label(score: float | None) -> str:
    if score is None:
        return LABEL_UNKNOWN
    if score >= 0.66:
        return LABEL_STRONG
    if score >= 0.33:
        return LABEL_MODERATE
    return LABEL_WEAK


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _build_evidence(
    *,
    fr: float | None,
    rtf: float | None,
    htr: float | None,
    ry: float | None,
    score: float | None,
    label: str,
) -> dict:
    supports: list[str] = []
    contradicts: list[str] = []
    gaps: list[str] = []

    if fr is not None:
        (supports if fr >= 0.5 else contradicts).append(
            f"circulating value is {_pct(fr)} of fully diluted (dilution overhang "
            f"{'low' if fr >= 0.5 else 'high'})"
        )
    else:
        gaps.append("supply/FDV unavailable — dilution unknown")

    if rtf is not None:
        supports.append(f"protocol keeps {_pct(rtf)} of fees as revenue")
    else:
        gaps.append("revenue or fees unavailable — value capture partly unknown")
    if htr is not None:
        (supports if htr > 0 else contradicts).append(
            f"{_pct(htr)} of revenue routed to holders"
        )
    else:
        gaps.append("holders-revenue unavailable — accrual to holders unknown")
    if ry is not None:
        supports.append(f"real yield to holders ~{_pct(ry)} of market cap (annualized)")

    return {
        "summary": f"token value capture: {label}",
        "what_supports": supports,
        "what_contradicts": contradicts,
        "data_gaps": gaps,
        "major_risk": (
            "supply ratios are a dilution proxy; precise unlock schedules and "
            "on-chain distribution are not yet available"
        ),
    }
