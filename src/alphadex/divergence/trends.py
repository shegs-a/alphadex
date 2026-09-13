"""Trend computations for divergence (Track A and Track B).

Each function returns a ``TrendResult`` carrying the value, how it was derived
(``method``), and a short human note — or an explicit "unavailable" result when the
inputs are missing/insufficient (never ``0``, ADR-003). Track B (cross-time from the
append-only history) is preferred when available; Track A (provider growth windows)
is the single-snapshot fallback.
"""

from __future__ import annotations

from dataclasses import dataclass

from alphadex.divergence.config import DivergenceConfig
from alphadex.divergence.inputs import AssetSeries
from alphadex.fundamentals.normalize import (
    METRIC_FEES_7D_USD,
    METRIC_FEES_30D_USD,
    METRIC_TVL_USD,
)
from alphadex.marketdata.normalize import (
    METRIC_MARKET_CAP_USD,
    METRIC_PRICE_CHANGE_PCT_30D,
    METRIC_PRICE_USD,
)

METHOD_CROSS_TIME = "cross_time"
METHOD_GROWTH_WINDOW = "growth_window"
METHOD_NONE = "none"

_DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class TrendResult:
    """A computed trend (fractional change) with provenance."""

    value: float | None
    method: str
    note: str

    @property
    def available(self) -> bool:
        return self.value is not None


def _pct_change(new: float, old: float) -> float | None:
    if old == 0:
        return None
    return (new - old) / abs(old)


def fundamentals_trend(series: AssetSeries, config: DivergenceConfig) -> TrendResult:
    """Improvement in protocol economics (fees), preferring cross-time history."""
    # Track B: fees_30d now vs a prior observation far enough back.
    latest = series.latest(METRIC_FEES_30D_USD)
    prior = series.prior(METRIC_FEES_30D_USD, min_gap_days=config.min_history_days)
    if latest is not None and prior is not None:
        change = _pct_change(latest.value, prior.value)
        if change is not None:
            return TrendResult(
                change,
                METHOD_CROSS_TIME,
                "30d fees changed vs an earlier observation",
            )

    # Track B fallback: TVL trend (also economic activity).
    tvl_latest = series.latest(METRIC_TVL_USD)
    tvl_prior = series.prior(METRIC_TVL_USD, min_gap_days=config.min_history_days)
    if tvl_latest is not None and tvl_prior is not None:
        change = _pct_change(tvl_latest.value, tvl_prior.value)
        if change is not None:
            return TrendResult(change, METHOD_CROSS_TIME, "TVL changed vs earlier")

    # Track A: fees acceleration — 7d run-rate vs 30d run-rate (single snapshot).
    fees_7d = series.latest_value(METRIC_FEES_7D_USD)
    fees_30d = series.latest_value(METRIC_FEES_30D_USD)
    if fees_7d is not None and fees_30d is not None:
        rate_7d = fees_7d * (_DAYS_PER_YEAR / 7.0)
        rate_30d = fees_30d * (_DAYS_PER_YEAR / 30.0)
        accel = _pct_change(rate_7d, rate_30d)
        if accel is not None:
            return TrendResult(
                accel,
                METHOD_GROWTH_WINDOW,
                "fees run-rate: 7d vs 30d (acceleration)",
            )

    return TrendResult(None, METHOD_NONE, "no fundamentals trend available")


def price_trend(series: AssetSeries, config: DivergenceConfig) -> TrendResult:
    """Price movement, preferring cross-time history over the 30d growth window."""
    latest = series.latest(METRIC_PRICE_USD)
    prior = series.prior(METRIC_PRICE_USD, min_gap_days=config.min_history_days)
    if latest is not None and prior is not None:
        change = _pct_change(latest.value, prior.value)
        if change is not None:
            return TrendResult(
                change, METHOD_CROSS_TIME, "price changed vs an earlier observation"
            )

    pct_30d = series.latest_value(METRIC_PRICE_CHANGE_PCT_30D)
    if pct_30d is not None:
        return TrendResult(
            pct_30d / 100.0, METHOD_GROWTH_WINDOW, "30d price change (provider)"
        )

    return TrendResult(None, METHOD_NONE, "no price trend available")


def valuation_multiple(series: AssetSeries) -> float | None:
    """Coarse market-cap-to-annualized-fees multiple (a divergence input, not a
    valuation verdict). Lower means cheaper relative to fee generation."""
    mc = series.latest_value(METRIC_MARKET_CAP_USD)
    fees_30d = series.latest_value(METRIC_FEES_30D_USD)
    if mc is None or fees_30d is None:
        return None
    annualized = fees_30d * (_DAYS_PER_YEAR / 30.0)
    if annualized <= 0:
        return None
    return mc / annualized


def valuation_trend(series: AssetSeries, config: DivergenceConfig) -> TrendResult:
    """Change in the valuation multiple over time (Track B only).

    A falling multiple while fundamentals rise is positive divergence (the market is
    not yet repricing). Requires cross-time market-cap and fees.
    """
    mc_latest = series.latest(METRIC_MARKET_CAP_USD)
    mc_prior = series.prior(METRIC_MARKET_CAP_USD, min_gap_days=config.min_history_days)
    fees_latest = series.latest(METRIC_FEES_30D_USD)
    fees_prior = series.prior(METRIC_FEES_30D_USD, min_gap_days=config.min_history_days)
    if not (mc_latest and mc_prior and fees_latest and fees_prior):
        return TrendResult(None, METHOD_NONE, "no cross-time valuation trend")
    if fees_latest.value <= 0 or fees_prior.value <= 0:
        return TrendResult(None, METHOD_NONE, "fees non-positive")
    mult_now = mc_latest.value / (fees_latest.value * (_DAYS_PER_YEAR / 30.0))
    mult_then = mc_prior.value / (fees_prior.value * (_DAYS_PER_YEAR / 30.0))
    change = _pct_change(mult_now, mult_then)
    if change is None:
        return TrendResult(None, METHOD_NONE, "valuation multiple undefined")
    return TrendResult(change, METHOD_CROSS_TIME, "valuation multiple change")
