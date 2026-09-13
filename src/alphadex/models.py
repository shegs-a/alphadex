"""Core persistence models.

Implements the binding data contracts from Sprint 00:

- ADR-003 — missing data is explicit (``ValueStatus``), never ``0``. A check
  constraint enforces that a numeric value is present iff the status is ``OK``.
- ADR-004 — metric data is stored as append-only historical observations
  (asset, metric, value, period, observed_at, source), not mutable current values.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class ValueStatus(enum.StrEnum):
    """State of an observed metric value (ADR-003).

    ``OK`` carries a real value; the others explicitly represent absence and must
    never be substituted with ``0``.
    """

    OK = "OK"
    UNKNOWN = "UNKNOWN"  # value exists but could not be obtained
    NOT_AVAILABLE = "NOT_AVAILABLE"  # provider does not supply / not reported
    NOT_APPLICABLE = "NOT_APPLICABLE"  # metric does not apply to this asset


# Portable enum column (VARCHAR + CHECK) — works on both PostgreSQL and SQLite.
_value_status_type = Enum(
    ValueStatus,
    name="value_status",
    native_enum=False,
    values_callable=lambda e: [m.value for m in e],
)


class Asset(Base):
    """A crypto asset in the scannable universe."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Category may be unknown at ingest time; nullable rather than a fake default.
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
    )

    observations: Mapped[list[MetricObservation]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("symbol", "name", name="uq_asset_symbol_name"),
        Index("ix_assets_symbol", "symbol"),
    )

    source_ids: Mapped[list[AssetSourceId]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Asset id={self.id} symbol={self.symbol!r}>"


class AssetSourceId(Base):
    """Maps a provider's own asset id to an internal ``Asset`` (AGENTS.md §13).

    Asset identity is resolved by ``(provider, external_id)``, never by the
    ambiguous symbol — so symbol collisions and duplicate listings across
    providers cannot merge two distinct assets.
    """

    __tablename__ = "asset_source_ids"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    asset: Mapped[Asset] = relationship(back_populates="source_ids")

    __table_args__ = (
        UniqueConstraint(
            "provider", "external_id", name="uq_asset_source_provider_external"
        ),
        Index("ix_asset_source_asset", "asset_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<AssetSourceId asset_id={self.asset_id} provider={self.provider!r} "
            f"external_id={self.external_id!r}>"
        )


class MetricObservation(Base):
    """An append-only observation of one metric for one asset (ADR-004).

    Rows are never overwritten; corrections are new rows. "Current value" is a
    query over these observations, not a stored field.
    """

    __tablename__ = "metric_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )

    metric: Mapped[str] = mapped_column(String(128), nullable=False)
    # Numeric value; NULL exactly when value_status != OK (enforced below).
    value: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)
    value_status: Mapped[ValueStatus] = mapped_column(
        _value_status_type, nullable=False, default=ValueStatus.OK
    )
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Period the value covers, e.g. "point", "7d", "30d", "2026-08".
    period: Mapped[str] = mapped_column(String(32), nullable=False, default="point")

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # ── Provenance (ADR-004 / AGENTS.md §9) ──────────────────────────────────
    source_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    asset: Mapped[Asset] = relationship(back_populates="observations")

    __table_args__ = (
        # ADR-003: a real value is present iff the status is OK.
        CheckConstraint(
            "(value_status = 'OK' AND value IS NOT NULL) "
            "OR (value_status != 'OK' AND value IS NULL)",
            name="ck_observation_value_status_consistency",
        ),
        Index(
            "ix_observation_asset_metric_period_observed",
            "asset_id",
            "metric",
            "period",
            "observed_at",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<MetricObservation asset_id={self.asset_id} metric={self.metric!r} "
            f"status={self.value_status.value}>"
        )


class IngestionRun(Base):
    """Run-level record of one ingestion cycle (AGENTS.md §8 observability).

    Makes provider failures and partial runs observable rather than silent: how
    many assets succeeded, how many failed, how many observations were written.
    """

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    # running | success | partial | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    assets_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assets_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observations_written: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<IngestionRun id={self.id} provider={self.provider!r} "
            f"status={self.status!r}>"
        )


class ScanRun(Base):
    """One run of the Opportunity Scanner (Sprint 04).

    A scan is the cheap, broad screen at the top of the tiered pipeline (§9). The
    config (thresholds/weights) used is snapshotted here so a scan's results are
    reproducible and auditable (explainability §10; ADR-004 spirit).
    """

    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # running | success | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    universe_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Snapshot of the screen configuration used (thresholds + weights).
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    results: Mapped[list[ScanResult]] = relationship(
        back_populates="scan_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ScanRun id={self.id} status={self.status!r}>"


class ScanResult(Base):
    """One asset's outcome in a scan.

    ``status`` is the classification; ``screen_score`` is a **preliminary** ordering
    score (never the Alpha Score). ``data_completeness`` records how much of the
    scored signal was actually available — poor data never masquerades as a strong
    signal (§10). ``reasons`` holds the human-readable per-criterion breakdown
    (explanatory metadata only; decision fields are typed columns — §9). A missing
    score is ``NULL`` with a status explaining why, never ``0`` (ADR-003).
    """

    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )

    # candidate | watch | insufficient_data | excluded
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    screen_score: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_completeness: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    reasons: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    scan_run: Mapped[ScanRun] = relationship(back_populates="results")
    asset: Mapped[Asset] = relationship()

    __table_args__ = (
        Index("ix_scan_results_run", "scan_run_id"),
        Index("ix_scan_results_asset", "asset_id"),
        UniqueConstraint("scan_run_id", "asset_id", name="uq_scan_result_run_asset"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<ScanResult run={self.scan_run_id} asset={self.asset_id} "
            f"status={self.status!r} rank={self.rank}>"
        )


class DivergenceRun(Base):
    """One run of the Economic Divergence Engine (Sprint 05).

    The config used is snapshotted for reproducibility (§10). Divergence signals are
    derived data, regenerable by re-running the engine.
    """

    __tablename__ = "divergence_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # running | success | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    analyzed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    divergence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    signals: Mapped[list[DivergenceSignal]] = relationship(
        back_populates="divergence_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<DivergenceRun id={self.id} status={self.status!r}>"


class DivergenceSignal(Base):
    """One asset's divergence signal in a run.

    Quantifies the gap between improving fundamentals and lagging price/valuation.
    ``divergence_score`` is a **component** (not the Alpha Score) and is ``NULL``
    with a classification when it cannot be computed — never ``0`` (ADR-003). The
    ``evidence`` JSON answers the §10 questions (what changed / why now / supports /
    contradicts / invalidates / major risk). ``method`` records how the trend was
    derived (``growth_window`` or ``cross_time``).
    """

    __tablename__ = "divergence_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    divergence_run_id: Mapped[int] = mapped_column(
        ForeignKey("divergence_runs.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )

    # potential_mispricing | fundamental_divergence | fundamental_repricing |
    # momentum | thesis_weakening | watch | insufficient_data  (see ADR-005)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    # Measurement fields, kept distinct from confidence (ADR-005):
    divergence_score: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    divergence_gap: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    signal_strength: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    fundamentals_trend: Mapped[float | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    price_trend: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    valuation_trend: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    valuation_level: Mapped[float | None] = mapped_column(
        Numeric(38, 18), nullable=True
    )
    window: Mapped[str | None] = mapped_column(String(32), nullable=True)
    method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    data_quality: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    divergence_run: Mapped[DivergenceRun] = relationship(back_populates="signals")
    asset: Mapped[Asset] = relationship()

    __table_args__ = (
        Index("ix_divergence_signals_run", "divergence_run_id"),
        Index("ix_divergence_signals_asset", "asset_id"),
        UniqueConstraint(
            "divergence_run_id", "asset_id", name="uq_divergence_signal_run_asset"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<DivergenceSignal run={self.divergence_run_id} asset={self.asset_id} "
            f"class={self.classification!r} rank={self.rank}>"
        )


class TokenomicsRun(Base):
    """One run of the Tokenomics (Token Value Capture) engine (Sprint 06)."""

    __tablename__ = "tokenomics_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analyzed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    signals: Mapped[list[TokenomicsSignal]] = relationship(
        back_populates="tokenomics_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<TokenomicsRun id={self.id} status={self.status!r}>"


class TokenomicsSignal(Base):
    """One asset's Token Value Capture assessment.

    Measures whether protocol economics accrue to the token: dilution/float and
    value capture (Fees ≠ Revenue ≠ Holders Revenue kept distinct — §9). The
    ``value_capture_score`` is a **component**, not the Alpha Score, and is ``NULL``
    with a label when it cannot be computed — never ``0`` (ADR-003). Component
    values are kept distinct from the score, and ``data_completeness`` is separate
    (ADR-005 discipline).
    """

    __tablename__ = "tokenomics_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    tokenomics_run_id: Mapped[int] = mapped_column(
        ForeignKey("tokenomics_runs.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )

    value_capture_score: Mapped[float | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )
    # strong | moderate | weak | unknown
    value_capture_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    float_ratio: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    revenue_to_fees: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    holders_to_revenue: Mapped[float | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    real_yield: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    data_completeness: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    tokenomics_run: Mapped[TokenomicsRun] = relationship(back_populates="signals")
    asset: Mapped[Asset] = relationship()

    __table_args__ = (
        Index("ix_tokenomics_signals_run", "tokenomics_run_id"),
        Index("ix_tokenomics_signals_asset", "asset_id"),
        UniqueConstraint(
            "tokenomics_run_id", "asset_id", name="uq_tokenomics_signal_run_asset"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<TokenomicsSignal run={self.tokenomics_run_id} asset={self.asset_id} "
            f"label={self.value_capture_label!r}>"
        )


class RiskRun(Base):
    """One run of the Risk engine (Sprint 06). Risk is a separate output (§10)."""

    __tablename__ = "risk_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analyzed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    assessments: Mapped[list[RiskAssessment]] = relationship(
        back_populates="risk_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<RiskRun id={self.id} status={self.status!r}>"


class RiskAssessment(Base):
    """One asset's Risk assessment — a **separate** output from Alpha (§10).

    Per-factor risks (0..1, higher = riskier) plus a blended ``risk_score`` and a
    ``risk_band``. ``concentration_risk`` is ``NULL`` (no on-chain provider yet) —
    a data gap surfaced, never guessed. A missing score is ``NULL`` with a band,
    never ``0`` (ADR-003); ``data_quality`` is separate from the score.
    """

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_run_id: Mapped[int] = mapped_column(
        ForeignKey("risk_runs.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )

    risk_score: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    # low | moderate | elevated | high | unknown
    risk_band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    liquidity_risk: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    volatility_risk: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    dilution_risk: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    size_risk: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    concentration_risk: Mapped[float | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )
    data_quality: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    risk_run: Mapped[RiskRun] = relationship(back_populates="assessments")
    asset: Mapped[Asset] = relationship()

    __table_args__ = (
        Index("ix_risk_assessments_run", "risk_run_id"),
        Index("ix_risk_assessments_asset", "asset_id"),
        UniqueConstraint(
            "risk_run_id", "asset_id", name="uq_risk_assessment_run_asset"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<RiskAssessment run={self.risk_run_id} asset={self.asset_id} "
            f"band={self.risk_band!r}>"
        )


class AlphaRun(Base):
    """One run of the Alpha Scoring Engine (Sprint 07).

    Assembles the upstream component signals into the headline decision-support
    output. The config (weight vector, references, thresholds) is snapshotted for
    reproducibility (§10). Alpha scores are derived data, regenerable by re-running.
    """

    __tablename__ = "alpha_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # running | success | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analyzed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scored_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    scores: Mapped[list[AlphaScore]] = relationship(
        back_populates="alpha_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<AlphaRun id={self.id} status={self.status!r}>"


class AlphaScore(Base):
    """One asset's Alpha assessment — **three separate outputs** (§10, ADR-006).

    ``alpha_score`` (attractiveness), ``risk_score`` (+ band, taken from the Risk
    engine — not folded into Alpha), and ``confidence`` (+ band) are distinct columns.
    ``model_completeness`` records how much of the full 7-component model was available
    (Valuation and Technical Setup are not implemented yet). A missing score is
    ``NULL`` with a ``status`` explaining why, never ``0`` (ADR-003). ``components``
    holds the per-component breakdown (contribution/weight/available) and ``evidence``
    answers the §10 questions. ``status`` uses the allowed decision vocabulary — never
    BUY. Ranking is by Alpha Score, ties broken toward higher completeness.
    """

    __tablename__ = "alpha_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    alpha_run_id: Mapped[int] = mapped_column(
        ForeignKey("alpha_runs.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )

    alpha_score: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    # strong | moderate | weak | unknown
    alpha_band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    # low | moderate | elevated | high | unknown
    risk_band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    # high | moderate | low
    confidence_band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    model_completeness: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    # high_interest | potential_opportunity | watch | risk_elevated |
    # low_confidence | thesis_weakening | insufficient_data  (never BUY — §10)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    components: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    alpha_run: Mapped[AlphaRun] = relationship(back_populates="scores")
    asset: Mapped[Asset] = relationship()

    __table_args__ = (
        Index("ix_alpha_scores_run", "alpha_run_id"),
        Index("ix_alpha_scores_asset", "asset_id"),
        UniqueConstraint("alpha_run_id", "asset_id", name="uq_alpha_score_run_asset"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<AlphaScore run={self.alpha_run_id} asset={self.asset_id} "
            f"status={self.status!r} rank={self.rank}>"
        )


class ValuationRun(Base):
    """One run of the Valuation engine (Sprint 08). A **component** feeding Alpha."""

    __tablename__ = "valuation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analyzed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    assessments: Mapped[list[ValuationAssessment]] = relationship(
        back_populates="valuation_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ValuationRun id={self.id} status={self.status!r}>"


class ValuationAssessment(Base):
    """One asset's relative valuation — a **component**, not the Alpha Score.

    ``valuation_score`` is a **relative attractiveness** in [0,1] (higher = cheaper
    vs the economics generated) against heuristic reference multiples — **not** an
    intrinsic/fair-value claim. It is ``NULL`` with a label when no multiple was
    measurable, never ``0`` (ADR-003). The four multiples measure distinct economic
    relationships and are stored as distinct columns (§9); ``data_completeness`` is
    kept **separate** from the score. Derived data, regenerable by re-running.
    """

    __tablename__ = "valuation_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    valuation_run_id: Mapped[int] = mapped_column(
        ForeignKey("valuation_runs.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )

    valuation_score: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    # cheap | fair | expensive | unknown  (a relative reading, not a fair-value verdict)
    valuation_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    price_to_fees: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    price_to_revenue: Mapped[float | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    price_to_holders_revenue: Mapped[float | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    mcap_to_tvl: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    data_completeness: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    valuation_run: Mapped[ValuationRun] = relationship(back_populates="assessments")
    asset: Mapped[Asset] = relationship()

    __table_args__ = (
        Index("ix_valuation_assessments_run", "valuation_run_id"),
        Index("ix_valuation_assessments_asset", "asset_id"),
        UniqueConstraint(
            "valuation_run_id", "asset_id", name="uq_valuation_assessment_run_asset"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<ValuationAssessment run={self.valuation_run_id} asset={self.asset_id} "
            f"label={self.valuation_label!r}>"
        )
