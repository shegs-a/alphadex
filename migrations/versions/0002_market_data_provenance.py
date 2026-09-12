"""market data provenance: asset_source_ids and ingestion_runs

Sprint 02. Additive: adds provider-id mapping (symbol-collision-safe asset
identity, AGENTS.md §13) and an ingestion-run log (run-level observability, §8).
The Sprint 01 schema (assets, metric_observations) is untouched.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_source_ids",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "provider", "external_id", name="uq_asset_source_provider_external"
        ),
    )
    op.create_index("ix_asset_source_asset", "asset_source_ids", ["asset_id"])

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assets_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assets_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "observations_written",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_index("ix_asset_source_asset", table_name="asset_source_ids")
    op.drop_table("asset_source_ids")
