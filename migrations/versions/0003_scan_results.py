"""opportunity scanner: scan_runs and scan_results

Sprint 04. Additive: adds the Opportunity Scanner's persistence — one row per scan
(with the config snapshot used) and one result per asset (classification, a
preliminary screen score, rank, data completeness, and an explainability
breakdown). Scan results are derived data (regenerable by re-running a scan). The
Sprint 01–03 schema is untouched.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("universe_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
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
        "scan_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scan_run_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("screen_score", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("data_completeness", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["scan_run_id"], ["scan_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("scan_run_id", "asset_id", name="uq_scan_result_run_asset"),
    )
    op.create_index("ix_scan_results_run", "scan_results", ["scan_run_id"])
    op.create_index("ix_scan_results_asset", "scan_results", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_scan_results_asset", table_name="scan_results")
    op.drop_index("ix_scan_results_run", table_name="scan_results")
    op.drop_table("scan_results")
    op.drop_table("scan_runs")
