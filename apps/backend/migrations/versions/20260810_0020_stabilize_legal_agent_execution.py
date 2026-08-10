"""Persist a stable analysis date for each Legal Agent execution plan.

Revision ID: 20260810_0020
Revises: 20260809_0019
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0020"
down_revision: str | None = "20260809_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_execution_plans",
        sa.Column("analysis_effective_date", sa.Date(), nullable=True),
    )
    op.execute(
        "UPDATE agent_execution_plans "
        "SET analysis_effective_date = "
        "(created_at AT TIME ZONE 'UTC')::date "
        "WHERE analysis_effective_date IS NULL"
    )
    op.alter_column(
        "agent_execution_plans",
        "analysis_effective_date",
        existing_type=sa.Date(),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("agent_execution_plans", "analysis_effective_date")
