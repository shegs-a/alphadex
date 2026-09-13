"""Risk Score + band — a separate output (§10), never folded into the Alpha Score.

Blends the available risk factors (renormalizing weights over what is present so a
missing factor lowers data quality, never a false low risk) and maps the score to a
band. ``data_quality`` is kept separate from the score. Language is *risk elevated /
risk high* — never BUY/GUARANTEED.
"""

from __future__ import annotations

from dataclasses import dataclass

from alphadex.risk.config import RiskConfig
from alphadex.risk.factors import (
    Values,
    concentration_risk,
    dilution_risk,
    liquidity_risk,
    size_risk,
    volatility_risk,
)

BAND_LOW = "low"
BAND_MODERATE = "moderate"
BAND_ELEVATED = "elevated"
BAND_HIGH = "high"
BAND_UNKNOWN = "unknown"


@dataclass(frozen=True)
class RiskOutcome:
    risk_score: float | None
    risk_band: str
    liquidity_risk: float | None
    volatility_risk: float | None
    dilution_risk: float | None
    size_risk: float | None
    concentration_risk: float | None
    data_quality: float
    evidence: dict


def evaluate(values: Values, config: RiskConfig) -> RiskOutcome:
    lr = liquidity_risk(values, config)
    vr = volatility_risk(values, config)
    dr = dilution_risk(values)
    sr = size_risk(values, config)
    cr = concentration_risk(values)  # always None (data gap)

    weighted = [
        (config.weight_liquidity, lr),
        (config.weight_volatility, vr),
        (config.weight_dilution, dr),
        (config.weight_size, sr),
    ]
    present = [(w, v) for w, v in weighted if v is not None]
    if present:
        total_w = sum(w for w, _ in present)
        score: float | None = sum(w * v for w, v in present) / total_w
    else:
        score = None

    # Data quality over all five factors (concentration is a known, surfaced gap).
    available = sum(1 for v in (lr, vr, dr, sr, cr) if v is not None)
    data_quality = available / 5.0

    band = _band(score, config)
    evidence = _build_evidence(lr=lr, vr=vr, dr=dr, sr=sr, cr=cr, band=band)
    return RiskOutcome(
        risk_score=score,
        risk_band=band,
        liquidity_risk=lr,
        volatility_risk=vr,
        dilution_risk=dr,
        size_risk=sr,
        concentration_risk=cr,
        data_quality=data_quality,
        evidence=evidence,
    )


def _band(score: float | None, config: RiskConfig) -> str:
    if score is None:
        return BAND_UNKNOWN
    if score < config.band_moderate:
        return BAND_LOW
    if score < config.band_elevated:
        return BAND_MODERATE
    if score < config.band_high:
        return BAND_ELEVATED
    return BAND_HIGH


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}"


def _build_evidence(
    *,
    lr: float | None,
    vr: float | None,
    dr: float | None,
    sr: float | None,
    cr: float | None,
    band: str,
) -> dict:
    drivers: list[str] = []
    for name, value in (
        ("liquidity", lr),
        ("volatility", vr),
        ("dilution", dr),
        ("size", sr),
    ):
        if value is not None and value >= 0.5:
            drivers.append(f"{name} risk elevated ({_pct(value)}/100)")

    gaps: list[str] = []
    if cr is None:
        gaps.append("holder concentration unavailable (no on-chain data)")
    for name, value in (
        ("liquidity", lr),
        ("volatility", vr),
        ("dilution", dr),
        ("size", sr),
    ):
        if value is None:
            gaps.append(f"{name} factor unavailable")

    return {
        "summary": f"risk {band}",
        "primary_drivers": drivers,
        "data_gaps": gaps,
        "note": (
            "risk is a separate output from the Alpha Score; a strong signal with "
            "high risk is not a top candidate"
        ),
    }
