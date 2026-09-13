"""alpha scoring: alpha_runs and alpha_scores

Sprint 07. Additive: adds the Alpha Scoring Engine's persistence. Alpha, Risk, and
Confidence are three separate outputs (§10, ADR-006) kept as distinct columns; a
missing score is NULL with a status, never 0 (ADR-003). Results are derived data
(regenerable by re-running). The Sprint 01–06 schema is untouched.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alpha_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analyzed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scored_count", sa.Integer(), nullable=False, server_default="0"),
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
        "alpha_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alpha_run_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("alpha_score", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("alpha_band", sa.String(length=16), nullable=True),
        sa.Column("risk_score", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("risk_band", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("confidence_band", sa.String(length=16), nullable=True),
        sa.Column(
            "model_completeness", sa.Numeric(precision=5, scale=4), nullable=True
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["alpha_run_id"], ["alpha_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "alpha_run_id", "asset_id", name="uq_alpha_score_run_asset"
        ),
    )
    op.create_index("ix_alpha_scores_run", "alpha_scores", ["alpha_run_id"])
    op.create_index("ix_alpha_scores_asset", "alpha_scores", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_alpha_scores_asset", table_name="alpha_scores")
    op.drop_index("ix_alpha_scores_run", table_name="alpha_scores")
    op.drop_table("alpha_scores")
    op.drop_table("alpha_runs")
