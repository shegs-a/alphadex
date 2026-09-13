"""economic divergence engine: divergence_runs and divergence_signals

Sprint 05. Additive: adds the Divergence Engine's persistence — one row per run
(with the config snapshot) and one signal per analyzed asset (classification, a
divergence score, the trends, method, data quality, and an evidence breakdown).
Signals are derived data (regenerable by re-running the engine). The Sprint 01–04
schema is untouched.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "divergence_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analyzed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("divergence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "divergence_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("divergence_run_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("divergence_score", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column(
            "fundamentals_trend", sa.Numeric(precision=18, scale=8), nullable=True
        ),
        sa.Column("price_trend", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("valuation_trend", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("window", sa.String(length=32), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=True),
        sa.Column("data_quality", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["divergence_run_id"], ["divergence_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "divergence_run_id", "asset_id", name="uq_divergence_signal_run_asset"
        ),
    )
    op.create_index(
        "ix_divergence_signals_run", "divergence_signals", ["divergence_run_id"]
    )
    op.create_index("ix_divergence_signals_asset", "divergence_signals", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_divergence_signals_asset", table_name="divergence_signals")
    op.drop_index("ix_divergence_signals_run", table_name="divergence_signals")
    op.drop_table("divergence_signals")
    op.drop_table("divergence_runs")
