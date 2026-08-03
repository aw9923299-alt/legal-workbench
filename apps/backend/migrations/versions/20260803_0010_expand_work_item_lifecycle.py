"""Expand the audited WorkItem lifecycle.

Revision ID: 20260803_0010
Revises: 20260803_0009
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0010"
down_revision: str | None = "20260803_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status_constraint = op.f("ck_work_items_work_item_status")
    op.drop_constraint(status_constraint, "work_items", type_="check")
    op.create_check_constraint(
        status_constraint,
        "work_items",
        "status IN ('todo','in_progress','paused','waiting','blocked',"
        "'pending_review','done','cancelled')",
    )
    op.add_column("work_items", sa.Column("paused_reason", sa.Text()))
    op.add_column("work_items", sa.Column("cancelled_at", sa.DateTime(timezone=True)))
    op.add_column("work_items", sa.Column("cancel_reason", sa.Text()))
    op.add_column("work_item_dependencies", sa.Column("satisfied_by", sa.String(length=160)))


def downgrade() -> None:
    op.execute("UPDATE work_items SET status = 'in_progress' WHERE status = 'paused'")
    status_constraint = op.f("ck_work_items_work_item_status")
    op.drop_constraint(status_constraint, "work_items", type_="check")
    op.create_check_constraint(
        status_constraint,
        "work_items",
        "status IN ('todo','in_progress','waiting','blocked','pending_review','done','cancelled')",
    )
    op.drop_column("work_item_dependencies", "satisfied_by")
    op.drop_column("work_items", "cancel_reason")
    op.drop_column("work_items", "cancelled_at")
    op.drop_column("work_items", "paused_reason")
