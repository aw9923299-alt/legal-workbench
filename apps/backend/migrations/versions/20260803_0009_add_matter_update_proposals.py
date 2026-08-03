"""Add human-reviewed Matter update proposals.

Revision ID: 20260803_0009
Revises: 20260803_0008
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260803_0009"
down_revision: str | None = "20260803_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "legal_matters",
        sa.Column("priority", sa.String(length=16), server_default="medium", nullable=False),
    )
    op.add_column(
        "legal_matters",
        sa.Column("priority_source", sa.String(length=24), server_default="system", nullable=False),
    )
    op.add_column("legal_matters", sa.Column("target_deadline_at", sa.DateTime(timezone=True)))
    op.add_column("legal_matters", sa.Column("next_action", sa.Text()))
    op.create_check_constraint(
        "ck_legal_matters_priority",
        "legal_matters",
        "priority IN ('urgent','high','medium','low')",
    )
    op.create_check_constraint(
        "ck_legal_matters_priority_source",
        "legal_matters",
        "priority_source IN ('system','agent_suggested','legal_confirmed')",
    )

    op.create_table(
        "matter_update_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("base_matter_version", sa.Integer(), nullable=False),
        sa.Column(
            "proposed_changes",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "final_changes",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "field_decisions",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("reviewed_by", sa.String(length=160)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("base_matter_version > 0", name="ck_proposal_base_matter_version"),
        sa.CheckConstraint(
            "status IN ('pending','approved','partially_approved','rejected','superseded')",
            name="ck_matter_update_proposal_status",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["message_candidates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["matter_id"], ["legal_matters.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_matter_update_proposals_candidate_id",
        "matter_update_proposals",
        ["candidate_id"],
    )
    op.create_index(
        "ix_matter_update_proposals_matter_id", "matter_update_proposals", ["matter_id"]
    )
    op.create_index(
        "ix_matter_update_proposals_status_created",
        "matter_update_proposals",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_matter_update_proposals_matter_status",
        "matter_update_proposals",
        ["matter_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_matter_update_proposals_matter_status", table_name="matter_update_proposals")
    op.drop_index("ix_matter_update_proposals_status_created", table_name="matter_update_proposals")
    op.drop_index("ix_matter_update_proposals_matter_id", table_name="matter_update_proposals")
    op.drop_index("ix_matter_update_proposals_candidate_id", table_name="matter_update_proposals")
    op.drop_table("matter_update_proposals")
    op.drop_constraint("ck_legal_matters_priority_source", "legal_matters", type_="check")
    op.drop_constraint("ck_legal_matters_priority", "legal_matters", type_="check")
    op.drop_column("legal_matters", "next_action")
    op.drop_column("legal_matters", "target_deadline_at")
    op.drop_column("legal_matters", "priority_source")
    op.drop_column("legal_matters", "priority")
