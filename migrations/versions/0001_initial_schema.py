"""initial schema: assets and metric_observations

Implements ADR-004 (append-only observations) and ADR-003 (explicit missing-data
with a value/status consistency check).

Revision ID: 0001
Revises:
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALUE_STATUSES = ("OK", "UNKNOWN", "NOT_AVAILABLE", "NOT_APPLICABLE")


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("symbol", "name", name="uq_asset_symbol_name"),
    )
    op.create_index("ix_assets_symbol", "assets", ["symbol"])

    op.create_table(
        "metric_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column(
            "value_status",
            sa.Enum(*_VALUE_STATUSES, name="value_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("period", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_provider", sa.String(length=64), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_status", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "(value_status = 'OK' AND value IS NOT NULL) "
            "OR (value_status != 'OK' AND value IS NULL)",
            name="ck_observation_value_status_consistency",
        ),
    )
    op.create_index(
        "ix_observation_asset_metric_period_observed",
        "metric_observations",
        ["asset_id", "metric", "period", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_observation_asset_metric_period_observed",
        table_name="metric_observations",
    )
    op.drop_table("metric_observations")
    op.drop_index("ix_assets_symbol", table_name="assets")
    op.drop_table("assets")
