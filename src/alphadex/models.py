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
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
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

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Asset id={self.id} symbol={self.symbol!r}>"


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
