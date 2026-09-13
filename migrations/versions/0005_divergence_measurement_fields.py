"""divergence measurement fields: divergence_gap, signal_strength, valuation_level

Sprint 05.1. Additive: separates the divergence *measurement* into distinct fields
(ADR-005) — the raw economic-price gap, the signal-strength magnitude, and the
informational valuation multiple level. Divergence signals are derived data
(regenerable by re-running the engine). The Sprint 01–05 schema is otherwise
untouched.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "divergence_signals",
        sa.Column("divergence_gap", sa.Numeric(precision=18, scale=8), nullable=True),
    )
    op.add_column(
        "divergence_signals",
        sa.Column("signal_strength", sa.Numeric(precision=9, scale=6), nullable=True),
    )
    op.add_column(
        "divergence_signals",
        sa.Column("valuation_level", sa.Numeric(precision=38, scale=18), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("divergence_signals", "valuation_level")
    op.drop_column("divergence_signals", "signal_strength")
    op.drop_column("divergence_signals", "divergence_gap")
