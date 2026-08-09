"""Add persisted legal Agent plans, run lineage and knowledge retrieval.

Revision ID: 20260809_0018
Revises: 20260808_0017
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260809_0018"
down_revision: str | None = "20260808_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identity_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _versioned_columns() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        *_identity_columns(),
        *_versioned_columns(),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=200), nullable=False),
        sa.Column("document_version_id", sa.Uuid()),
        sa.Column("matter_id", sa.Uuid()),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column(
            "agent_types", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            "matter_types",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("jurisdiction", sa.String(length=80), nullable=False),
        sa.Column("effective_from", sa.Date()),
        sa.Column("effective_to", sa.Date()),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("source_priority", sa.Integer(), server_default="50", nullable=False),
        sa.Column(
            "internal_precedent",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("confidentiality", sa.String(length=24), nullable=False),
        sa.Column("approved_by", sa.String(length=160)),
        sa.CheckConstraint(
            "source_priority BETWEEN 0 AND 100",
            name="knowledge_source_priority_range",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="knowledge_effective_date_order",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["matter_id"], ["legal_matters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "source_id", name="uq_knowledge_documents_source"),
    )
    op.create_index(
        "ix_knowledge_documents_filters",
        "knowledge_documents",
        ["status", "jurisdiction", "document_type", "source_priority"],
    )
    op.create_index(
        "ix_knowledge_documents_document_version_id",
        "knowledge_documents",
        ["document_version_id"],
    )
    op.create_index("ix_knowledge_documents_matter_id", "knowledge_documents", ["matter_id"])

    op.create_table(
        "knowledge_chunks",
        *_identity_columns(),
        sa.Column("knowledge_document_id", sa.Uuid(), nullable=False),
        sa.Column("document_segment_id", sa.Uuid()),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(length=500), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', coalesce(normalized_text, ''))", persisted=True),
        ),
        sa.CheckConstraint("sequence > 0", name="knowledge_chunk_sequence_positive"),
        sa.ForeignKeyConstraint(
            ["knowledge_document_id"], ["knowledge_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_segment_id"], ["document_segments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "knowledge_document_id", "sequence", name="uq_knowledge_chunks_sequence"
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_document",
        "knowledge_chunks",
        ["knowledge_document_id", "sequence"],
    )
    op.create_index(
        "ix_knowledge_chunks_document_segment_id",
        "knowledge_chunks",
        ["document_segment_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_fts",
        "knowledge_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_knowledge_chunks_trgm",
        "knowledge_chunks",
        ["normalized_text"],
        postgresql_using="gin",
        postgresql_ops={"normalized_text": "gin_trgm_ops"},
    )

    op.create_table(
        "knowledge_retrieval_logs",
        *_identity_columns(),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False),
        sa.Column("selected_chunk_ids", postgresql.JSONB(), nullable=False),
        sa.Column("component_scores", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("agent_run_id", sa.Uuid()),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_retrieval_logs_run_created",
        "knowledge_retrieval_logs",
        ["agent_run_id", "created_at"],
    )
    op.create_index(
        "ix_knowledge_retrieval_logs_correlation",
        "knowledge_retrieval_logs",
        ["correlation_id", "created_at"],
    )

    op.create_table(
        "agent_execution_plans",
        *_identity_columns(),
        *_versioned_columns(),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid()),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "task_types", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("synthesis_strategy", sa.Text(), nullable=False),
        sa.Column(
            "missing_information",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "requires_user_input",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("planning_run_id", sa.Uuid()),
        sa.Column("synthesis_run_id", sa.Uuid()),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','planning','planned','running','partial','completed',"
            "'failed','needs_information','cancelled')",
            name="agent_execution_plan_status",
        ),
        sa.ForeignKeyConstraint(["matter_id"], ["legal_matters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["planning_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["synthesis_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_agent_execution_plans_idempotency"),
    )
    op.create_index(
        "ix_agent_execution_plans_matter_created",
        "agent_execution_plans",
        ["matter_id", "created_at"],
    )
    op.create_index(
        "ix_agent_execution_plans_status_created",
        "agent_execution_plans",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_agent_execution_plans_correlation", "agent_execution_plans", ["correlation_id"]
    )
    op.create_index(
        "ix_agent_execution_plans_work_item_id", "agent_execution_plans", ["work_item_id"]
    )

    op.create_table(
        "agent_plan_steps",
        *_identity_columns(),
        *_versioned_columns(),
        sa.Column("execution_plan_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.String(length=120), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("agent_key", sa.String(length=120), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column(
            "depends_on",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "context_requirements",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("latest_run_id", sa.Uuid()),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_code", sa.String(length=80)),
        sa.Column("failure_message", sa.Text()),
        sa.CheckConstraint("sequence >= 0", name="agent_plan_step_sequence_nonnegative"),
        sa.CheckConstraint("attempt_count >= 0", name="agent_plan_step_attempt_nonnegative"),
        sa.CheckConstraint(
            "status IN ('pending','ready','running','completed','failed','skipped',"
            "'needs_information')",
            name="agent_plan_step_status",
        ),
        sa.ForeignKeyConstraint(
            ["execution_plan_id"], ["agent_execution_plans.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["latest_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_plan_id", "step_id", name="uq_agent_plan_steps_step_id"),
        sa.UniqueConstraint("execution_plan_id", "sequence", name="uq_agent_plan_steps_sequence"),
    )
    op.create_index(
        "ix_agent_plan_steps_plan_status",
        "agent_plan_steps",
        ["execution_plan_id", "status"],
    )

    op.add_column("agent_runs", sa.Column("execution_plan_id", sa.Uuid()))
    op.add_column("agent_runs", sa.Column("plan_step_id", sa.Uuid()))
    op.add_column("agent_runs", sa.Column("parent_run_id", sa.Uuid()))
    op.add_column("agent_runs", sa.Column("retry_of_run_id", sa.Uuid()))
    op.add_column(
        "agent_runs",
        sa.Column("run_role", sa.String(length=24), server_default="standalone", nullable=False),
    )
    op.create_foreign_key(
        "fk_agent_runs_execution_plan_id",
        "agent_runs",
        "agent_execution_plans",
        ["execution_plan_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_runs_plan_step_id",
        "agent_runs",
        "agent_plan_steps",
        ["plan_step_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for column in ("parent_run_id", "retry_of_run_id"):
        op.create_foreign_key(
            f"fk_agent_runs_{column}",
            "agent_runs",
            "agent_runs",
            [column],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_check_constraint(
        "agent_run_role",
        "agent_runs",
        "run_role IN ('standalone','butler_planning','specialist','butler_synthesis')",
    )
    for column in (
        "execution_plan_id",
        "plan_step_id",
        "parent_run_id",
        "retry_of_run_id",
    ):
        op.create_index(f"ix_agent_runs_{column}", "agent_runs", [column])


def downgrade() -> None:
    for column in (
        "retry_of_run_id",
        "parent_run_id",
        "plan_step_id",
        "execution_plan_id",
    ):
        op.drop_index(f"ix_agent_runs_{column}", table_name="agent_runs")
    op.drop_constraint("agent_run_role", "agent_runs", type_="check")
    op.drop_constraint("fk_agent_runs_retry_of_run_id", "agent_runs", type_="foreignkey")
    op.drop_constraint("fk_agent_runs_parent_run_id", "agent_runs", type_="foreignkey")
    op.drop_constraint("fk_agent_runs_plan_step_id", "agent_runs", type_="foreignkey")
    op.drop_constraint("fk_agent_runs_execution_plan_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "run_role")
    op.drop_column("agent_runs", "retry_of_run_id")
    op.drop_column("agent_runs", "parent_run_id")
    op.drop_column("agent_runs", "plan_step_id")
    op.drop_column("agent_runs", "execution_plan_id")
    op.drop_table("agent_plan_steps")
    op.drop_table("agent_execution_plans")
    op.drop_table("knowledge_retrieval_logs")
    op.drop_index("ix_knowledge_chunks_trgm", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_fts", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
