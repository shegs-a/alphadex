"""Valuation score — a **relative attractiveness**, not a fair-value claim.

Each measurable multiple is normalized to an attractiveness in [0,1] against a
documented heuristic reference: ``ref / (ref + multiple)`` — a smooth, bounded,
monotonic map where **lower multiple = cheaper = more attractive**, hitting exactly
0.5 at the reference. The available attractiveness values are blended with
**renormalized** weights into a ``valuation_score`` that is **``None`` unless at least
one multiple was actually measurable** (a strong reading is never fabricated from
missing data — ADR-003/ADR-005 discipline). The raw multiples are always exposed and
retain their distinct economic meanings (§9); ``data_completeness`` is kept **separate**
from the score. The label (``cheap``/``fair``/``expensive``) is a *relative* reading
against the heuristic baselines, never a verdict of intrinsic/fair value. No BUY (§10).
"""

from __future__ import annotations

from dataclasses import dataclass

from alphadex.valuation.config import ValuationConfig
from alphadex.valuation.multiples import (
    Values,
    mcap_to_tvl,
    price_to_fees,
    price_to_holders_revenue,
    price_to_revenue,
)

LABEL_CHEAP = "cheap"
LABEL_FAIR = "fair"
LABEL_EXPENSIVE = "expensive"
LABEL_UNKNOWN = "unknown"

# Number of distinct multiples the engine can compute (for data completeness).
_MULTIPLE_COUNT = 4


@dataclass(frozen=True)
class ValuationOutcome:
    valuation_score: float | None  # relative attractiveness [0,1], higher = cheaper
    valuation_label: str
    price_to_fees: float | None
    price_to_revenue: float | None
    price_to_holders_revenue: float | None
    mcap_to_tvl: float | None
    data_completeness: float
    evidence: dict


def _attractiveness(multiple: float | None, ref: float) -> float | None:
    """Map a multiple to relative cheapness in [0,1]: ``ref / (ref + multiple)``.

    Monotonic decreasing in the multiple; 0.5 at ``ref``; → 1 as the multiple → 0;
    → 0 as it grows. This is *relative* cheapness vs a heuristic baseline, not a
    fair-value estimate.
    """
    if multiple is None:
        return None
    if multiple <= 0:
        return 1.0  # a non-positive priced-in multiple reads as maximally cheap
    return ref / (ref + multiple)


def evaluate(values: Values, config: ValuationConfig) -> ValuationOutcome:
    pf = price_to_fees(values)
    ps = price_to_revenue(values)
    phr = price_to_holders_revenue(values)
    mtv = mcap_to_tvl(values)

    # Each multiple's relative attractiveness, paired with its blend weight. Only the
    # measurable ones contribute; weights are renormalized over what is present.
    parts: list[tuple[float, float]] = []
    a_pf = _attractiveness(pf, config.ref_price_to_fees)
    a_ps = _attractiveness(ps, config.ref_price_to_revenue)
    a_phr = _attractiveness(phr, config.ref_price_to_holders_revenue)
    a_mtv = _attractiveness(mtv, config.ref_mcap_to_tvl)
    for weight, attractiveness in (
        (config.weight_fees, a_pf),
        (config.weight_revenue, a_ps),
        (config.weight_holders_revenue, a_phr),
        (config.weight_tvl, a_mtv),
    ):
        if attractiveness is not None:
            parts.append((weight, attractiveness))

    # valuation_score is None unless at least one multiple was measurable — a strong
    # reading is never fabricated from missing data.
    if parts:
        total_w = sum(w for w, _ in parts)
        score: float | None = sum(w * a for w, a in parts) / total_w
    else:
        score = None

    # Completeness over the four multiples — kept SEPARATE from the score (never
    # blended into it): thin data raises uncertainty, not a fake reading.
    present = sum(1 for m in (pf, ps, phr, mtv) if m is not None)
    completeness = present / _MULTIPLE_COUNT

    label = _label(score, config)
    evidence = _build_evidence(
        pf=pf,
        ps=ps,
        phr=phr,
        mtv=mtv,
        a_pf=a_pf,
        a_ps=a_ps,
        a_phr=a_phr,
        a_mtv=a_mtv,
        score=score,
        label=label,
    )
    return ValuationOutcome(
        valuation_score=score,
        valuation_label=label,
        price_to_fees=pf,
        price_to_revenue=ps,
        price_to_holders_revenue=phr,
        mcap_to_tvl=mtv,
        data_completeness=completeness,
        evidence=evidence,
    )


def _label(score: float | None, config: ValuationConfig) -> str:
    if score is None:
        return LABEL_UNKNOWN
    if score >= config.band_cheap:
        return LABEL_CHEAP
    if score >= config.band_expensive:
        return LABEL_FAIR
    return LABEL_EXPENSIVE


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}x"


def _build_evidence(
    *,
    pf: float | None,
    ps: float | None,
    phr: float | None,
    mtv: float | None,
    a_pf: float | None,
    a_ps: float | None,
    a_phr: float | None,
    a_mtv: float | None,
    score: float | None,
    label: str,
) -> dict:
    # Distinct economic meaning per multiple, surfaced on distinct lines (§9).
    lines = [
        ("market cap / annualized fees (gross throughput)", pf, a_pf),
        ("market cap / annualized revenue (protocol take)", ps, a_ps),
        ("market cap / annualized holders revenue (accrual to holders)", phr, a_phr),
        ("market cap / TVL (capital efficiency)", mtv, a_mtv),
    ]
    cheaper: list[str] = []
    richer: list[str] = []
    gaps: list[str] = []
    for name, mult, attr in lines:
        if mult is None or attr is None:
            gaps.append(f"{name} unavailable")
        elif attr >= 0.5:
            cheaper.append(f"{name}: {_fmt(mult)} (relatively cheap)")
        else:
            richer.append(f"{name}: {_fmt(mult)} (relatively rich)")

    return {
        "summary": f"relative valuation: {label}",
        "basis": (
            "relative cheapness vs the economics generated, against heuristic "
            "reference multiples — NOT an intrinsic/fair-value estimate"
        ),
        "cheaper_on": cheaper,
        "richer_on": richer,
        "data_gaps": gaps,
        "major_risk": (
            "multiples are coarse and absolute (no DCF, peer/sector, or historical "
            "percentile context); references are heuristic baselines, not fair values"
        ),
    }
