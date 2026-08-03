"""Add durable message judgement evaluation models.

Revision ID: 20260803_0011
Revises: 20260803_0010
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260803_0011"
down_revision: str | None = "20260803_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("suite_key", sa.String(length=120), nullable=False),
        sa.Column("case_key", sa.String(length=120), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("agent_key", sa.String(length=80), nullable=False),
        sa.Column("input_payload", postgresql.JSONB(), nullable=False),
        sa.Column("expected_output", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("data_classification", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("case_version > 0", name="evaluation_case_version_positive"),
        sa.CheckConstraint(
            "data_classification = 'synthetic_non_sensitive'",
            name="evaluation_case_synthetic_only",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "suite_key", "case_key", "case_version", name="uq_evaluation_cases_identity"
        ),
    )
    op.create_index(
        "ix_evaluation_cases_suite", "evaluation_cases", ["suite_key", "case_key"]
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("suite_key", sa.String(length=120), nullable=False),
        sa.Column("suite_version", sa.Integer(), nullable=False),
        sa.Column("runtime_type", sa.String(length=16), nullable=False),
        sa.Column("agent_key", sa.String(length=80), nullable=False),
        sa.Column("agent_definition_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.String(length=160), nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("allow_real_runtime", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "metrics",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("failure_code", sa.String(length=80)),
        sa.Column("failure_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("suite_version > 0", name="evaluation_suite_version_positive"),
        sa.CheckConstraint("runtime_type IN ('fake','real')", name="evaluation_runtime_type"),
        sa.CheckConstraint(
            "status IN ('running','completed','failed')", name="evaluation_run_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_runs_correlation_id", "evaluation_runs", ["correlation_id"]
    )
    op.create_index(
        "ix_evaluation_runs_suite_created", "evaluation_runs", ["suite_key", "created_at"]
    )
    op.create_index(
        "ix_evaluation_runs_status_created", "evaluation_runs", ["status", "created_at"]
    )

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_case_id", sa.Uuid(), nullable=False),
        sa.Column(
            "result_payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "scores",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("expected_relevant", sa.Boolean(), nullable=False),
        sa.Column("candidate_created", sa.Boolean(), nullable=False),
        sa.Column("schema_first_pass", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=80)),
        sa.Column("runtime_version", sa.String(length=80)),
        sa.Column("runtime_execution_id", sa.Uuid()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("duration_ms >= 0", name="evaluation_result_duration_nonnegative"),
        sa.CheckConstraint("retry_count >= 0", name="evaluation_result_retry_nonnegative"),
        sa.ForeignKeyConstraint(
            ["evaluation_case_id"], ["evaluation_cases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "evaluation_case_id",
            name="uq_evaluation_results_run_case",
        ),
    )
    op.create_index(
        "ix_evaluation_results_run",
        "evaluation_results",
        ["evaluation_run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_results_run", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index("ix_evaluation_runs_status_created", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_suite_created", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_correlation_id", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_evaluation_cases_suite", table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
