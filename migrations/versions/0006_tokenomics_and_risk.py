"""tokenomics and risk: tokenomics_runs/signals and risk_runs/assessments

Sprint 06. Additive: adds the Tokenomics (Token Value Capture) and Risk engines'
persistence. Risk is a separate output from Alpha (§10). Results are derived data
(regenerable by re-running). The Sprint 01–05 schema is untouched.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _run_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analyzed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table("tokenomics_runs", *_run_columns())
    op.create_table(
        "tokenomics_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tokenomics_run_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column(
            "value_capture_score", sa.Numeric(precision=9, scale=6), nullable=True
        ),
        sa.Column("value_capture_label", sa.String(length=16), nullable=True),
        sa.Column("float_ratio", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("revenue_to_fees", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column(
            "holders_to_revenue", sa.Numeric(precision=18, scale=8), nullable=True
        ),
        sa.Column("real_yield", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("data_completeness", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tokenomics_run_id"], ["tokenomics_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tokenomics_run_id", "asset_id", name="uq_tokenomics_signal_run_asset"
        ),
    )
    op.create_index(
        "ix_tokenomics_signals_run", "tokenomics_signals", ["tokenomics_run_id"]
    )
    op.create_index("ix_tokenomics_signals_asset", "tokenomics_signals", ["asset_id"])

    op.create_table("risk_runs", *_run_columns())
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("risk_run_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("risk_score", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("risk_band", sa.String(length=16), nullable=True),
        sa.Column("liquidity_risk", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("volatility_risk", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("dilution_risk", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("size_risk", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column(
            "concentration_risk", sa.Numeric(precision=9, scale=6), nullable=True
        ),
        sa.Column("data_quality", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["risk_run_id"], ["risk_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "risk_run_id", "asset_id", name="uq_risk_assessment_run_asset"
        ),
    )
    op.create_index("ix_risk_assessments_run", "risk_assessments", ["risk_run_id"])
    op.create_index("ix_risk_assessments_asset", "risk_assessments", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_risk_assessments_asset", table_name="risk_assessments")
    op.drop_index("ix_risk_assessments_run", table_name="risk_assessments")
    op.drop_table("risk_assessments")
    op.drop_table("risk_runs")
    op.drop_index("ix_tokenomics_signals_asset", table_name="tokenomics_signals")
    op.drop_index("ix_tokenomics_signals_run", table_name="tokenomics_signals")
    op.drop_table("tokenomics_signals")
    op.drop_table("tokenomics_runs")
