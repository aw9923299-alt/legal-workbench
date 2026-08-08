"""Add fenced Agent Run Attempts.

Revision ID: 20260803_0007
Revises: 20260801_0006
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0007"
down_revision: str | None = "20260801_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_run_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(length=80)),
        sa.Column("failure_message", sa.Text()),
        sa.CheckConstraint(
            "attempt_number > 0", name="ck_agent_run_attempts_attempt_number"
        ),
        sa.CheckConstraint(
            "status IN ('running','completed','failed','timed_out','cancelled','expired')",
            name="ck_agent_run_attempts_agent_attempt_status",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_run_id", "attempt_number", name="uq_agent_run_attempts_number"
        ),
        sa.UniqueConstraint("lease_token", name="uq_agent_run_attempts_lease_token"),
    )
    op.create_index(
        "ix_agent_run_attempts_agent_run_id",
        "agent_run_attempts",
        ["agent_run_id"],
    )
    op.create_index(
        "ix_agent_run_attempts_status_expiry",
        "agent_run_attempts",
        ["status", "lease_expires_at"],
    )
    op.execute(
        "INSERT INTO agent_run_attempts "
        "(id, agent_run_id, attempt_number, lease_token, worker_id, status, "
        "lease_expires_at, started_at, heartbeat_at, finished_at, failure_code, "
        "failure_message) "
        "SELECT gen_random_uuid(), id, attempt_number, gen_random_uuid(), "
        "COALESCE(NULLIF(worker_id, ''), 'migration-backfill'), "
        "CASE "
        "WHEN status IN ('preparing','running','validating') THEN 'running' "
        "WHEN status IN ('completed','needs_more_information') THEN 'completed' "
        "WHEN status = 'timed_out' THEN 'timed_out' "
        "WHEN status = 'cancelled' THEN 'cancelled' "
        "ELSE 'failed' END, "
        "COALESCE(lease_expires_at, finished_at, updated_at), "
        "COALESCE(started_at, updated_at), COALESCE(heartbeat_at, started_at, updated_at), "
        "finished_at, failure_code, failure_message "
        "FROM agent_runs WHERE status <> 'queued'"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_run_attempts_status_expiry", table_name="agent_run_attempts"
    )
    op.drop_index(
        "ix_agent_run_attempts_agent_run_id", table_name="agent_run_attempts"
    )
    op.drop_table("agent_run_attempts")
