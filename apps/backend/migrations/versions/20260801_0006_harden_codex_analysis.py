"""Harden Codex analysis state, snapshots, and candidate history.

Revision ID: 20260801_0006
Revises: 20260801_0005
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0006"
down_revision: str | None = "20260801_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_EMPTY_LIST = sa.text("'[]'::jsonb")


def upgrade() -> None:
    for column in (
        sa.Column(
            "builder_version", sa.String(length=40), server_default="1.0.0", nullable=False
        ),
        sa.Column(
            "selection_policy_version",
            sa.String(length=40),
            server_default="thread-v1",
            nullable=False,
        ),
        sa.Column("current_message_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "attachment_version_hash", sa.String(length=64), server_default="", nullable=False
        ),
        sa.Column("truncated", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("truncation_reason", sa.Text()),
        sa.Column("original_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("included_size", sa.Integer(), server_default="0", nullable=False),
    ):
        op.add_column("context_snapshots", column)
    op.execute(
        "UPDATE context_snapshots SET truncated = "
        "CASE WHEN lower(COALESCE(content ->> 'truncated', 'false')) = 'true' "
        "THEN true ELSE false END"
    )
    op.create_check_constraint(
        "context_snapshot_sizes",
        "context_snapshots",
        "original_size >= 0 AND included_size >= 0 AND included_size <= original_size",
    )

    for column in (
        sa.Column("runtime_version", sa.String(length=80)),
        sa.Column(
            "agent_definition_version", sa.String(length=40), server_default="", nullable=False
        ),
        sa.Column("prompt_version", sa.String(length=40), server_default="", nullable=False),
        sa.Column(
            "validation_errors",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column("repair_attempted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("token_usage", postgresql.JSONB()),
        sa.Column("worker_id", sa.String(length=160)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("agent_runs", column)
    op.execute(
        "UPDATE agent_runs AS run SET agent_definition_version = definition.version, "
        "prompt_version = definition.version FROM agent_definitions AS definition "
        "WHERE definition.id = run.agent_definition_id"
    )
    op.create_index("ix_agent_runs_worker_id", "agent_runs", ["worker_id"])
    op.create_index("ix_agent_runs_lease_expires_at", "agent_runs", ["lease_expires_at"])

    op.create_table(
        "agent_run_status_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=32)),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=80)),
        sa.Column("failure_message", sa.Text()),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN "
            "('queued','preparing','running','validating','completed',"
            "'needs_more_information','failed','timed_out','cancelled','dead_letter')",
            name="ck_agent_run_status_events_from_status",
        ),
        sa.CheckConstraint(
            "to_status IN ('queued','preparing','running','validating','completed',"
            "'needs_more_information','failed','timed_out','cancelled','dead_letter')",
            name="ck_agent_run_status_events_to_status",
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_run_status_events_run_changed",
        "agent_run_status_events",
        ["agent_run_id", "changed_at"],
    )
    op.create_index(
        "ix_agent_run_status_events_agent_run_id",
        "agent_run_status_events",
        ["agent_run_id"],
    )
    op.create_index(
        "ix_agent_run_status_events_correlation_id",
        "agent_run_status_events",
        ["correlation_id"],
    )
    op.execute(
        "INSERT INTO agent_run_status_events "
        "(id, agent_run_id, from_status, to_status, changed_at, correlation_id, "
        "attempt_number, failure_code, failure_message) "
        "SELECT gen_random_uuid(), id, NULL, status, created_at, correlation_id, "
        "attempt_number, failure_code, failure_message FROM agent_runs"
    )

    op.create_table(
        "candidate_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_by", sa.Uuid()),
        sa.CheckConstraint("revision > 0", name="ck_candidate_revisions_revision"),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["message_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"], ["candidate_revisions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id", "revision", name="uq_candidate_revisions_revision"
        ),
    )
    op.create_index(
        "ix_candidate_revisions_candidate_created",
        "candidate_revisions",
        ["candidate_id", "created_at"],
    )
    op.create_index(
        "ix_candidate_revisions_candidate_id", "candidate_revisions", ["candidate_id"]
    )
    op.create_index(
        "ix_candidate_revisions_agent_run_id", "candidate_revisions", ["agent_run_id"]
    )
    op.execute(
        "INSERT INTO candidate_revisions "
        "(id, candidate_id, revision, agent_run_id, analysis_payload, created_at) "
        "SELECT gen_random_uuid(), id, 1, agent_run_id, analysis_payload, created_at "
        "FROM message_candidates WHERE agent_run_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_revisions_agent_run_id", table_name="candidate_revisions")
    op.drop_index("ix_candidate_revisions_candidate_id", table_name="candidate_revisions")
    op.drop_index(
        "ix_candidate_revisions_candidate_created", table_name="candidate_revisions"
    )
    op.drop_table("candidate_revisions")
    op.drop_index(
        "ix_agent_run_status_events_correlation_id",
        table_name="agent_run_status_events",
    )
    op.drop_index(
        "ix_agent_run_status_events_agent_run_id", table_name="agent_run_status_events"
    )
    op.drop_index(
        "ix_agent_run_status_events_run_changed", table_name="agent_run_status_events"
    )
    op.drop_table("agent_run_status_events")
    op.drop_index("ix_agent_runs_lease_expires_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_worker_id", table_name="agent_runs")
    for column in (
        "lease_expires_at",
        "worker_id",
        "token_usage",
        "repair_attempted",
        "validation_errors",
        "prompt_version",
        "agent_definition_version",
        "runtime_version",
    ):
        op.drop_column("agent_runs", column)
    op.drop_constraint("context_snapshot_sizes", "context_snapshots", type_="check")
    for column in (
        "included_size",
        "original_size",
        "truncation_reason",
        "truncated",
        "attachment_version_hash",
        "current_message_version",
        "selection_policy_version",
        "builder_version",
    ):
        op.drop_column("context_snapshots", column)
