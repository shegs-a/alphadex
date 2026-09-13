"""Application configuration.

Env-driven via pydantic-settings (AGENTS.md §12, ADR-002). No secrets are
hard-coded; see ``.env.example`` for the documented set. ``DATABASE_URL`` may be
provided directly, or assembled from the individual ``POSTGRES_*`` variables.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_env: str = Field(default="local", description="local | staging | production")
    app_log_level: str = Field(default="INFO")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)

    # ── Database ─────────────────────────────────────────────────────────────
    # Either set DATABASE_URL directly, or the POSTGRES_* parts below.
    database_url: str | None = Field(default=None)
    postgres_user: str = Field(default="alphadex")
    postgres_password: str = Field(default="alphadex")
    postgres_db: str = Field(default="alphadex")
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)

    # ── Market data provider (Sprint 02) ────────────────────────────────────
    market_data_provider: str = Field(default="coingecko")
    coingecko_api_key: str | None = Field(default=None)
    coingecko_base_url: str = Field(default="https://api.coingecko.com/api/v3")
    provider_timeout_seconds: float = Field(default=20.0)

    # Asset universe (configurable, never hard-coded — AGENTS.md §2). An explicit
    # comma-separated list of provider ids wins; otherwise the top-N by market cap.
    market_universe_ids: str | None = Field(default=None)
    market_universe_top_n: int = Field(default=50)

    # ── Fundamental data provider (Sprint 03) ───────────────────────────────
    fundamental_data_provider: str = Field(default="defillama")
    defillama_api_key: str | None = Field(default=None)
    defillama_base_url: str = Field(default="https://api.llama.fi")

    # ── Opportunity Scanner (Sprint 04) ─────────────────────────────────────
    # Inclusion gates (configurable — never hard-coded, §2/§10).
    scan_market_cap_min: float = Field(default=10_000_000.0)
    scan_market_cap_max: float | None = Field(default=None)
    scan_min_volume_24h: float = Field(default=100_000.0)
    scan_freshness_max_hours: float = Field(default=48.0)
    # When true, an asset with no fundamentals is insufficient_data (not a candidate).
    scan_require_fundamentals: bool = Field(default=False)
    # Normalization references for the (log-scaled) signals.
    scan_ref_fees_30d: float = Field(default=100_000_000.0)
    scan_ref_volume_24h: float = Field(default=1_000_000_000.0)
    # Preliminary Screen Score weights (must sum to 1.0; NOT the Alpha Score).
    scan_weight_activity: float = Field(default=0.4)
    scan_weight_liquidity: float = Field(default=0.3)
    scan_weight_momentum: float = Field(default=0.3)

    # ── Divergence Engine (Sprint 05) ───────────────────────────────────────
    # Which assets to analyze: "candidates" (latest scan candidates+watch) or "all".
    divergence_scope: str = Field(default="candidates")
    # Track B needs two observations at least this many days apart.
    divergence_min_history_days: float = Field(default=5.0)
    # Classification heuristics (configurable — documented, not universal truths).
    # Minimum economic-price gap for a divergence-family classification.
    divergence_threshold: float = Field(default=0.15)
    # Materiality floor for "fundamentals improving"/"deteriorating".
    divergence_min_fundamentals_improvement: float = Field(default=0.05)
    # Price at/below this (fractional 30d change) is "declining or stagnant".
    divergence_price_stagnant_ceiling: float = Field(default=0.05)
    # Price at/above this is "already repriced strongly" (momentum/repricing marker).
    divergence_price_strong_threshold: float = Field(default=0.50)
    # Divergence score component weights (must sum to 1.0; a component; NOT alpha).
    divergence_weight_gap: float = Field(default=0.7)
    divergence_weight_valuation: float = Field(default=0.3)

    # ── Tokenomics / Token Value Capture (Sprint 06) ────────────────────────
    tokenomics_scope: str = Field(default="candidates")
    # Annualized holders-revenue / market cap that scores full marks (10% = 1.0).
    tokenomics_ref_real_yield: float = Field(default=0.10)
    # Value Capture score weights (must sum to 1.0; a component, NOT the Alpha Score).
    tokenomics_weight_dilution: float = Field(default=0.5)
    tokenomics_weight_value_capture: float = Field(default=0.5)

    # ── Risk Engine (Sprint 06) — a separate output (§10) ───────────────────
    risk_scope: str = Field(default="candidates")
    # Normalization references for the risk factors (documented heuristics).
    risk_ref_turnover: float = Field(default=0.10)  # healthy 24h volume / market cap
    risk_ref_volatility: float = Field(default=0.50)  # 50% swing → full volatility risk
    risk_ref_market_cap: float = Field(default=10_000_000_000.0)  # size reference
    # Risk Score factor weights (must sum to 1.0).
    risk_weight_liquidity: float = Field(default=0.30)
    risk_weight_volatility: float = Field(default=0.30)
    risk_weight_dilution: float = Field(default=0.20)
    risk_weight_size: float = Field(default=0.20)
    # Risk band cut points on the 0..1 score (documented, tunable).
    risk_band_moderate: float = Field(default=0.25)
    risk_band_elevated: float = Field(default=0.50)
    risk_band_high: float = Field(default=0.75)

    # ── Alpha Scoring Engine (Sprint 07) — three separate outputs (§10) ──────
    alpha_scope: str = Field(default="candidates")
    # The full 7-component Alpha weight vector (AGENTS.md §10 defaults; sums to 1.0).
    # Valuation and Technical Setup are not implemented yet — their weight is
    # renormalized over the available components and their absence lowers Confidence
    # (never zero-filled — ADR-003/ADR-006). Weights are documented defaults, NOT
    # fitted to any known outcomes (§10, no hindsight bias).
    alpha_weight_economic_growth: float = Field(default=0.25)
    alpha_weight_divergence: float = Field(default=0.20)
    alpha_weight_valuation: float = Field(default=0.15)
    alpha_weight_token_value_capture: float = Field(default=0.15)
    alpha_weight_market_strength: float = Field(default=0.10)
    alpha_weight_tokenomics: float = Field(default=0.10)
    alpha_weight_technical_setup: float = Field(default=0.05)
    # Normalization references for the component adapters (documented heuristics).
    alpha_ref_fundamentals_growth: float = Field(default=0.50)  # +50% → full marks
    alpha_ref_market_momentum: float = Field(default=0.50)  # +50% 30d → full marks
    alpha_ref_market_turnover: float = Field(default=0.10)  # healthy vol / market cap
    # Confidence blend (model completeness vs upstream data quality; must sum to 1.0).
    alpha_conf_weight_completeness: float = Field(default=0.60)
    alpha_conf_weight_data_quality: float = Field(default=0.40)
    # Confidence band cut points on the 0..1 confidence (0 < moderate < high < 1).
    alpha_confidence_band_moderate: float = Field(default=0.40)
    alpha_confidence_band_high: float = Field(default=0.70)
    # Decision-status Alpha thresholds (0 < moderate < strong < 1).
    alpha_status_moderate: float = Field(default=0.45)
    alpha_status_strong: float = Field(default=0.65)

    # ── Valuation Engine (Sprint 08) — a component feeding Alpha (§10) ───────
    valuation_scope: str = Field(default="candidates")
    # Heuristic mid-range references per multiple (the point mapped to 0.5
    # attractiveness). Baselines — NOT universal fair values; not fitted to outcomes.
    valuation_ref_price_to_fees: float = Field(default=30.0)
    valuation_ref_price_to_revenue: float = Field(default=40.0)
    valuation_ref_price_to_holders_revenue: float = Field(default=20.0)
    valuation_ref_mcap_to_tvl: float = Field(default=1.0)
    # Blend weights over the four multiples (must sum to 1.0).
    valuation_weight_fees: float = Field(default=0.30)
    valuation_weight_revenue: float = Field(default=0.30)
    valuation_weight_holders_revenue: float = Field(default=0.25)
    valuation_weight_tvl: float = Field(default=0.15)
    # Label cut points on the 0..1 attractiveness (0 < expensive < cheap < 1).
    valuation_band_expensive: float = Field(default=0.40)
    valuation_band_cheap: float = Field(default=0.66)

    @property
    def universe_ids(self) -> list[str]:
        """Parsed explicit universe ids (empty when top-N mode is used)."""
        if not self.market_universe_ids:
            return []
        return [p.strip() for p in self.market_universe_ids.split(",") if p.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_url(self) -> str:
        """Resolved SQLAlchemy URL: explicit DATABASE_URL wins, else assembled."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (one read of the environment)."""
    return Settings()
