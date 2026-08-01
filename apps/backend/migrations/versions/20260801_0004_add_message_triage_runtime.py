"""Add persisted message-triage Agent runtime.

Revision ID: 20260801_0004
Revises: 20260801_0003
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0004"
down_revision: str | None = "20260801_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_EMPTY_LIST = sa.text("'[]'::jsonb")
JSON_EMPTY_OBJECT = sa.text("'{}'::jsonb")
NOW = sa.func.now()


def upgrade() -> None:
    op.add_column("context_snapshots", sa.Column("source_id", sa.String(length=160)))
    op.execute(
        "UPDATE context_snapshots "
        # Legacy hashes and source_ids were client-supplied and were not a
        # trustworthy deduplication identity. Preserve every historical audit
        # row by assigning its immutable primary key as the migration source.
        "SET source_id = id::text "
        "WHERE source_id IS NULL"
    )
    op.alter_column("context_snapshots", "source_id", nullable=False)
    op.add_column(
        "context_snapshots",
        sa.Column("snapshot_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "context_snapshots",
        sa.Column(
            "attachment_ids", postgresql.JSONB(), server_default=JSON_EMPTY_LIST, nullable=False
        ),
    )
    op.execute("UPDATE context_snapshots SET attachment_ids = file_ids")
    op.add_column(
        "context_snapshots",
        sa.Column(
            "thread_metadata", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False
        ),
    )
    op.add_column(
        "context_snapshots",
        sa.Column("content", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False),
    )
    op.create_index(
        "ix_context_snapshots_source_hash",
        "context_snapshots",
        ["source_type", "source_id", "content_hash"],
        unique=True,
    )

    op.create_table(
        "agent_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column(
            "input_schema", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False
        ),
        sa.Column(
            "output_schema", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False
        ),
        sa.Column(
            "allowed_tools", postgresql.JSONB(), server_default=JSON_EMPTY_LIST, nullable=False
        ),
        sa.Column(
            "allowed_knowledge_scopes",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','trial','active','paused','retired')",
            name="ck_agent_definitions_status",
        ),
        sa.CheckConstraint("timeout_seconds > 0", name="ck_agent_definitions_timeout_positive"),
        sa.CheckConstraint("max_retries >= 0", name="ck_agent_definitions_retries_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", "version", name="uq_agent_definitions_key_version"),
    )
    op.create_index("ix_agent_definitions_key_status", "agent_definitions", ["key", "status"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_definition_id", sa.Uuid(), nullable=False),
        sa.Column("matter_id", sa.Uuid()),
        sa.Column("work_item_id", sa.Uuid()),
        sa.Column("feishu_message_id", sa.Uuid()),
        sa.Column("context_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column(
            "input_payload", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False
        ),
        sa.Column(
            "output_payload", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False
        ),
        sa.Column("raw_stdout", sa.Text()),
        sa.Column("raw_stderr", sa.Text()),
        sa.Column("prompt_snapshot", sa.Text(), nullable=False),
        sa.Column("working_directory", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("timeout_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=80)),
        sa.Column("failure_message", sa.Text()),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','preparing','running','validating','completed',"
            "'needs_more_information','failed','timed_out','cancelled','dead_letter')",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint(
            "attempt_number >= 1 AND max_attempts >= attempt_number",
            name="ck_agent_runs_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["agent_definition_id"], ["agent_definitions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["matter_id"], ["legal_matters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["feishu_message_id"], ["feishu_messages.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["context_snapshot_id"], ["context_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_agent_definition_id", "agent_runs", ["agent_definition_id"])
    op.create_index("ix_agent_runs_context_snapshot_id", "agent_runs", ["context_snapshot_id"])
    op.create_index("ix_agent_runs_status_created", "agent_runs", ["status", "created_at"])
    op.create_index(
        "ix_agent_runs_message_created", "agent_runs", ["feishu_message_id", "created_at"]
    )
    op.create_index("ix_agent_runs_correlation", "agent_runs", ["correlation_id"])
    op.create_index("ix_agent_runs_failure_code", "agent_runs", ["failure_code"])

    op.create_table(
        "agent_run_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=200), nullable=False),
        sa.Column("source_version", sa.String(length=80)),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column(
            "citation_metadata",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_OBJECT,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "source_type IN ('feishu_message','context_snapshot','attachment',"
            "'knowledge_document','historical_matter','approved_example')",
            name="ck_agent_run_sources_type",
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_run_id",
            "source_type",
            "source_id",
            "source_hash",
            name="uq_agent_run_sources_exact_source",
        ),
    )
    op.create_index("ix_agent_run_sources_run", "agent_run_sources", ["agent_run_id", "created_at"])

    op.create_table(
        "draft_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "structured_payload",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_OBJECT,
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','superseded','approved')", name="ck_draft_artifacts_status"
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_draft_artifacts_run_status", "draft_artifacts", ["agent_run_id", "status"])

    op.add_column("message_candidates", sa.Column("feishu_message_id", sa.Uuid()))
    op.add_column(
        "message_candidates",
        sa.Column("requires_manual_review", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "message_candidates",
        sa.Column(
            "analysis_payload", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False
        ),
    )
    op.create_foreign_key(
        "fk_message_candidates_feishu_message_id",
        "message_candidates",
        "feishu_messages",
        ["feishu_message_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # Revision 0003 exposed this nullable placeholder without an AgentRun
    # registry. Preserve any external/legacy identifier in the audit payload
    # before clearing the column so the new foreign key can be established.
    op.execute(
        "UPDATE message_candidates "
        "SET analysis_payload = analysis_payload || "
        "jsonb_build_object('legacyAgentRunId', agent_run_id::text) "
        "WHERE agent_run_id IS NOT NULL"
    )
    op.execute("UPDATE message_candidates SET agent_run_id = NULL WHERE agent_run_id IS NOT NULL")
    op.create_foreign_key(
        "fk_message_candidates_agent_run_id",
        "message_candidates",
        "agent_runs",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_message_candidates_feishu_message_id", "message_candidates", ["feishu_message_id"]
    )
    op.create_index("ix_message_candidates_agent_run_id", "message_candidates", ["agent_run_id"])
    op.create_index(
        "uq_message_candidates_active_message",
        "message_candidates",
        ["feishu_message_id"],
        unique=True,
        postgresql_where=sa.text(
            "feishu_message_id IS NOT NULL AND status IN "
            "('pending_analysis','pending_confirmation','confirmed','linked')"
        ),
    )

    op.drop_constraint("feishu_message_status", "feishu_messages", type_="check")
    op.execute(
        "UPDATE feishu_messages SET status = 'candidate_created' WHERE status = 'analyzed'"
    )
    op.execute(
        "UPDATE feishu_messages SET status = 'analysis_failed' WHERE status = 'failed'"
    )
    op.create_check_constraint(
        "feishu_message_status",
        "feishu_messages",
        "status IN ('received','queued_for_analysis','context_prepared','agent_queued',"
        "'analysing','candidate_created','ignored','analysis_failed','dead_letter')",
    )
    op.add_column("feishu_messages", sa.Column("context_snapshot_id", sa.Uuid()))
    op.add_column("feishu_messages", sa.Column("last_agent_run_id", sa.Uuid()))
    op.add_column(
        "feishu_messages",
        sa.Column("analysis_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("feishu_messages", sa.Column("failure_code", sa.String(length=80)))
    op.add_column("feishu_messages", sa.Column("failure_message", sa.Text()))
    op.add_column(
        "feishu_messages", sa.Column("version", sa.Integer(), server_default="1", nullable=False)
    )
    op.create_foreign_key(
        "fk_feishu_messages_context_snapshot_id",
        "feishu_messages",
        "context_snapshots",
        ["context_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_feishu_messages_last_agent_run_id",
        "feishu_messages",
        "agent_runs",
        ["last_agent_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_feishu_messages_context_snapshot_id", "feishu_messages", ["context_snapshot_id"]
    )
    op.create_index(
        "ix_feishu_messages_last_agent_run_id", "feishu_messages", ["last_agent_run_id"]
    )

    op.add_column(
        "audit_events",
        sa.Column("actor_source", sa.String(length=40), server_default="system", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("audit_events", "actor_source")

    op.drop_index("ix_feishu_messages_last_agent_run_id", table_name="feishu_messages")
    op.drop_index("ix_feishu_messages_context_snapshot_id", table_name="feishu_messages")
    op.drop_constraint(
        "fk_feishu_messages_last_agent_run_id", "feishu_messages", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_feishu_messages_context_snapshot_id", "feishu_messages", type_="foreignkey"
    )
    op.drop_column("feishu_messages", "version")
    op.drop_column("feishu_messages", "failure_message")
    op.drop_column("feishu_messages", "failure_code")
    op.drop_column("feishu_messages", "analysis_attempts")
    op.drop_column("feishu_messages", "last_agent_run_id")
    op.drop_column("feishu_messages", "context_snapshot_id")
    op.drop_constraint("feishu_message_status", "feishu_messages", type_="check")
    # Preserve messages while folding the richer analysis state machine back
    # into the status vocabulary available in revision 0003.
    op.execute(
        "UPDATE feishu_messages SET status = 'queued_for_analysis' "
        "WHERE status IN ('context_prepared', 'agent_queued', 'analysing')"
    )
    op.execute(
        "UPDATE feishu_messages SET status = 'analyzed' WHERE status = 'candidate_created'"
    )
    op.execute(
        "UPDATE feishu_messages SET status = 'failed' "
        "WHERE status IN ('analysis_failed', 'dead_letter')"
    )
    op.create_check_constraint(
        "feishu_message_status",
        "feishu_messages",
        "status IN ('received','queued_for_analysis','analyzed','ignored','failed')",
    )

    op.drop_index("uq_message_candidates_active_message", table_name="message_candidates")
    op.drop_index("ix_message_candidates_agent_run_id", table_name="message_candidates")
    op.drop_index("ix_message_candidates_feishu_message_id", table_name="message_candidates")
    op.drop_constraint(
        "fk_message_candidates_agent_run_id", "message_candidates", type_="foreignkey"
    )
    # Restore any legacy external run identifier preserved during upgrade so
    # downgrade does not silently erase revision-0003 audit data.
    op.execute(
        "UPDATE message_candidates "
        "SET agent_run_id = (analysis_payload ->> 'legacyAgentRunId')::uuid "
        "WHERE analysis_payload ? 'legacyAgentRunId'"
    )
    op.drop_constraint(
        "fk_message_candidates_feishu_message_id", "message_candidates", type_="foreignkey"
    )
    op.drop_column("message_candidates", "analysis_payload")
    op.drop_column("message_candidates", "requires_manual_review")
    op.drop_column("message_candidates", "feishu_message_id")

    op.drop_index("ix_draft_artifacts_run_status", table_name="draft_artifacts")
    op.drop_table("draft_artifacts")
    op.drop_index("ix_agent_run_sources_run", table_name="agent_run_sources")
    op.drop_table("agent_run_sources")
    op.drop_index("ix_agent_runs_failure_code", table_name="agent_runs")
    op.drop_index("ix_agent_runs_correlation", table_name="agent_runs")
    op.drop_index("ix_agent_runs_message_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_context_snapshot_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_agent_definition_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_agent_definitions_key_status", table_name="agent_definitions")
    op.drop_table("agent_definitions")

    op.drop_index("ix_context_snapshots_source_hash", table_name="context_snapshots")
    op.drop_column("context_snapshots", "content")
    op.drop_column("context_snapshots", "thread_metadata")
    op.drop_column("context_snapshots", "attachment_ids")
    op.drop_column("context_snapshots", "snapshot_version")
    op.drop_column("context_snapshots", "source_id")
