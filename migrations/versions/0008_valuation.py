"""valuation: valuation_runs and valuation_assessments

Sprint 08. Additive: adds the Valuation engine's persistence. Valuation is a
**component** feeding the Alpha Score (§10, ADR-006), not the Alpha Score itself.
``valuation_score`` is a relative attractiveness (never an intrinsic/fair-value claim)
and is NULL when unmeasurable, never 0 (ADR-003). Results are derived data (regenerable
by re-running). The Sprint 01–07 schema is untouched.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "valuation_runs",
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
    )
    op.create_table(
        "valuation_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("valuation_run_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("valuation_score", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("valuation_label", sa.String(length=16), nullable=True),
        sa.Column("price_to_fees", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("price_to_revenue", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column(
            "price_to_holders_revenue",
            sa.Numeric(precision=18, scale=8),
            nullable=True,
        ),
        sa.Column("mcap_to_tvl", sa.Numeric(precision=18, scale=8), nullable=True),
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
            ["valuation_run_id"], ["valuation_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "valuation_run_id", "asset_id", name="uq_valuation_assessment_run_asset"
        ),
    )
    op.create_index(
        "ix_valuation_assessments_run", "valuation_assessments", ["valuation_run_id"]
    )
    op.create_index(
        "ix_valuation_assessments_asset", "valuation_assessments", ["asset_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_valuation_assessments_asset", table_name="valuation_assessments"
    )
    op.drop_index("ix_valuation_assessments_run", table_name="valuation_assessments")
    op.drop_table("valuation_assessments")
    op.drop_table("valuation_runs")
