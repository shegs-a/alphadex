"""Alpha Score + Risk + Confidence — three separate outputs (§10, ADR-006).

- **Alpha Score**: a weighted blend of the available attractiveness components, with
  weights **renormalized** over what is present. It is a weighted *average* of the
  available contributions, so it is bounded by their min and max — a missing component
  can never inflate it above what the present evidence supports (the no-inflation
  invariant). Risk and Confidence are **never** folded into this number.
- **Risk Score**: taken as-is from the Risk engine (Sprint 06) and surfaced alongside.
- **Confidence**: how much to trust the Alpha Score — a blend of ``model_completeness``
  (how much of the full 7-component model was available) and upstream data quality.
  With Valuation and Technical Setup not yet implemented, completeness is capped below
  1.0, honestly constraining Confidence until they land (ADR-006).

Ranking is by Alpha Score, with ``model_completeness`` breaking ties **toward** the
more-complete asset — so renormalizing a shorter component set never buys a rank
advantage. A high Alpha with elevated Risk or low Confidence is **down-classified** in
``status`` (never surfaced as a top opportunity; no BUY language — §10).
"""

from __future__ import annotations

from dataclasses import dataclass

from alphadex.alpha.components import AlphaComponent
from alphadex.alpha.config import AlphaConfig
from alphadex.divergence.engine import CLASS_WEAKENING
from alphadex.risk.score import BAND_ELEVATED, BAND_HIGH

# Alpha bands (parallel to the status thresholds).
BAND_STRONG = "strong"
BAND_MODERATE = "moderate"
BAND_WEAK = "weak"
BAND_UNKNOWN = "unknown"

# Confidence bands.
CONF_HIGH = "high"
CONF_MODERATE = "moderate"
CONF_LOW = "low"

# Decision status vocabulary (§10 — never BUY/GUARANTEED).
STATUS_HIGH_INTEREST = "high_interest"
STATUS_POTENTIAL_OPPORTUNITY = "potential_opportunity"
STATUS_WATCH = "watch"
STATUS_RISK_ELEVATED = "risk_elevated"
STATUS_LOW_CONFIDENCE = "low_confidence"
STATUS_THESIS_WEAKENING = "thesis_weakening"
STATUS_INSUFFICIENT = "insufficient_data"

# Risk bands at or above which a candidate is down-classified.
_RISK_DOWNCLASS_BANDS = (BAND_ELEVATED, BAND_HIGH)


@dataclass(frozen=True)
class UpstreamContext:
    """Upstream signals fed into Confidence and decision status (not into Alpha)."""

    divergence_classification: str | None = None
    divergence_quality: float | None = None
    tokenomics_quality: float | None = None
    risk_score: float | None = None
    risk_band: str | None = None
    risk_quality: float | None = None


@dataclass(frozen=True)
class AlphaAssessment:
    alpha_score: float | None
    alpha_band: str
    risk_score: float | None
    risk_band: str | None
    confidence: float
    confidence_band: str
    model_completeness: float
    status: str
    components: list[dict]
    evidence: dict

    @property
    def rank_key(self) -> tuple[float, float]:
        """Sort key (descending): Alpha first, model completeness breaks ties.

        Completeness breaks ties **toward** the more-complete asset, so an asset that
        is missing components never outranks an equally-scored, more-complete one
        purely because its weights were renormalized (ADR-006).
        """
        assert self.alpha_score is not None
        return (-self.alpha_score, -self.model_completeness)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _alpha_band(score: float | None, config: AlphaConfig) -> str:
    if score is None:
        return BAND_UNKNOWN
    if score >= config.status_strong:
        return BAND_STRONG
    if score >= config.status_moderate:
        return BAND_MODERATE
    return BAND_WEAK


def _confidence_band(confidence: float, config: AlphaConfig) -> str:
    if confidence >= config.confidence_band_high:
        return CONF_HIGH
    if confidence >= config.confidence_band_moderate:
        return CONF_MODERATE
    return CONF_LOW


def _decision_status(
    *,
    alpha_score: float | None,
    alpha_band: str,
    confidence_band: str,
    risk_band: str | None,
    divergence_classification: str | None,
    config: AlphaConfig,
) -> str:
    """Combine the three outputs into a decision status (down-classify, never BUY)."""
    if alpha_score is None:
        return STATUS_INSUFFICIENT
    # Trust first: if we cannot trust the Alpha Score, that caveat leads.
    if confidence_band == CONF_LOW:
        return STATUS_LOW_CONFIDENCE
    # Risk is a separate output; an elevated/high band disqualifies a top rating.
    if risk_band in _RISK_DOWNCLASS_BANDS:
        return STATUS_RISK_ELEVATED
    # A deteriorating thesis is not an opportunity regardless of the blended score.
    if divergence_classification == CLASS_WEAKENING:
        return STATUS_THESIS_WEAKENING
    if alpha_band == BAND_STRONG and confidence_band == CONF_HIGH:
        return STATUS_HIGH_INTEREST
    if alpha_score >= config.status_moderate:
        return STATUS_POTENTIAL_OPPORTUNITY
    return STATUS_WATCH


def score(
    components: list[AlphaComponent],
    context: UpstreamContext,
    config: AlphaConfig,
) -> AlphaAssessment:
    available = [c for c in components if c.available and c.contribution is not None]

    # ── Alpha Score: weighted average over available components (renormalized). ──
    if available:
        total_w = sum(c.weight for c in available)
        alpha: float | None = (
            sum(
                c.weight * c.contribution
                for c in available
                if c.contribution is not None
            )
            / total_w
        )
    else:
        alpha = None

    # ── model_completeness: available weight / full target weight (§10, ADR-006). ─
    total_target = sum(c.weight for c in components)
    completeness = (
        sum(c.weight for c in available) / total_target if total_target > 0 else 0.0
    )

    # ── Confidence: completeness blended with available upstream data quality. ──
    qualities = [
        q
        for q in (
            context.divergence_quality,
            context.tokenomics_quality,
            context.risk_quality,
        )
        if q is not None
    ]
    data_quality = _mean(qualities) if qualities else 0.0
    confidence = (
        config.conf_weight_completeness * completeness
        + config.conf_weight_data_quality * data_quality
    )

    alpha_band = _alpha_band(alpha, config)
    confidence_band = _confidence_band(confidence, config)
    status = _decision_status(
        alpha_score=alpha,
        alpha_band=alpha_band,
        confidence_band=confidence_band,
        risk_band=context.risk_band,
        divergence_classification=context.divergence_classification,
        config=config,
    )

    evidence = _build_evidence(
        available=available,
        components=components,
        alpha=alpha,
        completeness=completeness,
        context=context,
        status=status,
    )
    return AlphaAssessment(
        alpha_score=alpha,
        alpha_band=alpha_band,
        risk_score=context.risk_score,
        risk_band=context.risk_band,
        confidence=confidence,
        confidence_band=confidence_band,
        model_completeness=completeness,
        status=status,
        components=[c.as_dict() for c in components],
        evidence=evidence,
    )


def _build_evidence(
    *,
    available: list[AlphaComponent],
    components: list[AlphaComponent],
    alpha: float | None,
    completeness: float,
    context: UpstreamContext,
    status: str,
) -> dict:
    def _contrib(c: AlphaComponent) -> float:
        return c.contribution if c.contribution is not None else 0.0

    strongest = sorted(available, key=_contrib, reverse=True)
    why_interesting = [f"{c.name}: {c.detail}" for c in strongest[:3]]
    supports = [c.detail for c in available if _contrib(c) >= 0.5]
    contradicts = [c.detail for c in available if _contrib(c) < 0.5]
    missing = [c.name for c in components if not c.available]

    major_risk_parts: list[str] = []
    if context.risk_band in _RISK_DOWNCLASS_BANDS:
        major_risk_parts.append(f"risk band is {context.risk_band}")
    if missing:
        major_risk_parts.append(
            "model incomplete — " + ", ".join(missing) + " not scored"
        )
    if not major_risk_parts:
        major_risk_parts.append("no dominant single risk in the scored components")

    return {
        "summary": f"alpha status: {status.replace('_', ' ')}",
        "why_interesting": why_interesting,
        "what_supports": supports,
        "what_contradicts": contradicts,
        "what_invalidates": (
            "fundamentals reversing, price catching up, or risk deteriorating"
        ),
        "model_completeness": completeness,
        "missing_components": missing,
        "major_risk": "; ".join(major_risk_parts),
        "note": (
            "Alpha, Risk, and Confidence are separate outputs; a high Alpha with "
            "elevated Risk or low Confidence is not a top candidate"
        ),
    }
