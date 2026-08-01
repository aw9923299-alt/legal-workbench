"""Create the first legal workflow tables.

Revision ID: 20260801_0002
Revises: 20260801_0001
Create Date: 2026-08-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0002"
down_revision: str | None = "20260801_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_EMPTY_LIST = sa.text("'[]'::jsonb")
JSON_EMPTY_OBJECT = sa.text("'{}'::jsonb")
NOW = sa.func.now()

candidate_status = sa.Enum(
    "pending_analysis",
    "pending_confirmation",
    "confirmed",
    "linked",
    "information_only",
    "ignored",
    "rejected",
    name="candidate_status",
    native_enum=False,
    create_constraint=True,
)
legal_relevance = sa.Enum(
    "relevant",
    "possibly_relevant",
    "not_relevant",
    "unknown",
    name="legal_relevance",
    native_enum=False,
    create_constraint=True,
)
message_role = sa.Enum(
    "new_request",
    "progress_update",
    "material_update",
    "decision",
    "deadline_change",
    "closure_signal",
    "information",
    name="message_role",
    native_enum=False,
    create_constraint=True,
)
recommended_action = sa.Enum(
    "create_matter",
    "link_matter",
    "update_matter",
    "add_material",
    "reopen_matter",
    "information_only",
    "ignore",
    "needs_confirmation",
    name="recommended_action",
    native_enum=False,
    create_constraint=True,
)
matter_category = sa.Enum(
    "contract",
    "copy_review",
    "employment",
    "dispute",
    "intellectual_property",
    "platform_rules",
    "general_consultation",
    name="matter_category",
    native_enum=False,
    create_constraint=True,
)
matter_lifecycle_status = sa.Enum(
    "open",
    "resolved",
    "closed",
    "reopened",
    "cancelled",
    name="matter_lifecycle_status",
    native_enum=False,
    create_constraint=True,
)
matter_work_status = sa.Enum(
    "ready",
    "in_progress",
    "waiting",
    "blocked",
    "done",
    name="matter_work_status",
    native_enum=False,
    create_constraint=True,
)
legal_risk = sa.Enum(
    "critical",
    "high",
    "medium",
    "low",
    "pending",
    name="legal_risk",
    native_enum=False,
    create_constraint=True,
)
business_impact = sa.Enum(
    "company",
    "department",
    "project",
    "general",
    name="business_impact",
    native_enum=False,
    create_constraint=True,
)
confidentiality = sa.Enum(
    "internal",
    "confidential",
    "restricted",
    name="confidentiality",
    native_enum=False,
    create_constraint=True,
)
work_item_status = sa.Enum(
    "todo",
    "in_progress",
    "waiting",
    "blocked",
    "pending_review",
    "done",
    "cancelled",
    name="work_item_status",
    native_enum=False,
    create_constraint=True,
)
work_item_priority = sa.Enum(
    "urgent",
    "high",
    "medium",
    "low",
    name="work_item_priority",
    native_enum=False,
    create_constraint=True,
)
priority_source = sa.Enum(
    "system",
    "agent_suggested",
    "legal_confirmed",
    name="priority_source",
    native_enum=False,
    create_constraint=True,
)
ai_suggested_priority = sa.Enum(
    "urgent",
    "high",
    "medium",
    "low",
    name="ai_suggested_priority",
    native_enum=False,
    create_constraint=True,
)
candidate_matter_relation = sa.Enum(
    "created",
    "linked",
    "updated",
    name="candidate_matter_relation",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "context_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_ids", postgresql.JSONB(), server_default=JSON_EMPTY_LIST, nullable=False),
        sa.Column(
            "message_ids",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column("file_ids", postgresql.JSONB(), server_default=JSON_EMPTY_LIST, nullable=False),
        sa.Column(
            "relevant_matter_ids",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column(
            "participant_ids",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column(
            "permission_snapshot",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_OBJECT,
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_context_snapshots"),
    )

    op.create_table(
        "message_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("context_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("status", candidate_status, nullable=False),
        sa.Column("legal_relevance", legal_relevance, nullable=False),
        sa.Column("message_role", message_role, nullable=False),
        sa.Column("recommended_action", recommended_action, nullable=False),
        sa.Column("title_proposal", sa.String(length=500), nullable=True),
        sa.Column(
            "category_proposals",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column(
            "deadline_proposals",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column(
            "related_matter_proposals",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_by", sa.String(length=160), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.ForeignKeyConstraint(
            ["context_snapshot_id"], ["context_snapshots.id"],
            name="fk_message_candidates_context_snapshot_id_context_snapshots", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message_candidates"),
    )
    op.create_index(
        "ix_message_candidates_context_snapshot_id",
        "message_candidates",
        ["context_snapshot_id"],
    )
    op.create_index(
        "ix_message_candidates_status_created_at",
        "message_candidates",
        ["status", "created_at"],
    )

    op.create_table(
        "legal_matters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("matter_number", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("primary_category", matter_category, nullable=False),
        sa.Column(
            "secondary_categories",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column("lifecycle_status", matter_lifecycle_status, nullable=False),
        sa.Column("work_status", matter_work_status, nullable=False),
        sa.Column("owner_id", sa.String(length=160), nullable=False),
        sa.Column(
            "collaborator_ids",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column(
            "requester_ids",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column("entity_ids", postgresql.JSONB(), server_default=JSON_EMPTY_LIST, nullable=False),
        sa.Column("legal_risk", legal_risk, nullable=False),
        sa.Column("business_impact", business_impact, nullable=False),
        sa.Column("confidentiality", confidentiality, nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("current_stage", sa.String(length=160), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_legal_matters"),
        sa.UniqueConstraint("matter_number", name="uq_legal_matters_matter_number"),
    )
    op.create_index("ix_legal_matters_owner_id", "legal_matters", ["owner_id"])
    op.create_index(
        "ix_legal_matters_owner_status",
        "legal_matters",
        ["owner_id", "lifecycle_status"],
    )

    op.create_table(
        "work_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("status", work_item_status, nullable=False),
        sa.Column("owner_id", sa.String(length=160), nullable=False),
        sa.Column(
            "collaborator_ids",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column("priority", work_item_priority, nullable=False),
        sa.Column("priority_source", priority_source, nullable=False),
        sa.Column("ai_suggested_priority", ai_suggested_priority, nullable=True),
        sa.Column(
            "priority_reasons",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=False),
        sa.Column("waiting_party_id", sa.String(length=160), nullable=True),
        sa.Column("waiting_reason", sa.Text(), nullable=True),
        sa.Column("waiting_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("blocker_reason", sa.Text(), nullable=True),
        sa.Column("blocker_owner_id", sa.String(length=160), nullable=True),
        sa.Column("planned_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_complete_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sequence_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0",
            name="estimated_minutes_positive",
        ),
        sa.ForeignKeyConstraint(
            ["matter_id"], ["legal_matters.id"],
            name="fk_work_items_matter_id_legal_matters", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_work_items"),
    )
    op.create_index("ix_work_items_matter_id", "work_items", ["matter_id"])
    op.create_index("ix_work_items_owner_id", "work_items", ["owner_id"])
    op.create_index("ix_work_items_matter_status", "work_items", ["matter_id", "status"])
    op.create_index("ix_work_items_owner_priority", "work_items", ["owner_id", "priority"])

    op.create_table(
        "candidate_matter_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", candidate_matter_relation, nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("confirmed_by", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["message_candidates.id"],
            name="fk_candidate_matter_links_candidate_id_message_candidates", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["matter_id"], ["legal_matters.id"],
            name="fk_candidate_matter_links_matter_id_legal_matters", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_candidate_matter_links"),
        sa.UniqueConstraint(
            "candidate_id", "matter_id", "relation_type",
            name="uq_candidate_matter_links_candidate_id",
        ),
    )
    op.create_index(
        "ix_candidate_matter_links_candidate_id",
        "candidate_matter_links",
        ["candidate_id"],
    )
    op.create_index("ix_candidate_matter_links_matter_id", "candidate_matter_links", ["matter_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])
    op.create_index("ix_audit_events_aggregate", "audit_events", ["aggregate_type", "aggregate_id"])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
    )
    op.create_index("ix_outbox_events_correlation_id", "outbox_events", ["correlation_id"])
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["occurred_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "response_payload",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_OBJECT,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_records"),
        sa.UniqueConstraint(
            "operation", "idempotency_key",
            name="uq_idempotency_records_operation",
        ),
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_index("ix_outbox_events_pending", table_name="outbox_events")
    op.drop_index("ix_outbox_events_correlation_id", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_audit_events_aggregate", table_name="audit_events")
    op.drop_index("ix_audit_events_correlation_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_candidate_matter_links_matter_id", table_name="candidate_matter_links")
    op.drop_index("ix_candidate_matter_links_candidate_id", table_name="candidate_matter_links")
    op.drop_table("candidate_matter_links")
    op.drop_index("ix_work_items_owner_priority", table_name="work_items")
    op.drop_index("ix_work_items_matter_status", table_name="work_items")
    op.drop_index("ix_work_items_owner_id", table_name="work_items")
    op.drop_index("ix_work_items_matter_id", table_name="work_items")
    op.drop_table("work_items")
    op.drop_index("ix_legal_matters_owner_status", table_name="legal_matters")
    op.drop_index("ix_legal_matters_owner_id", table_name="legal_matters")
    op.drop_table("legal_matters")
    op.drop_index("ix_message_candidates_status_created_at", table_name="message_candidates")
    op.drop_index("ix_message_candidates_context_snapshot_id", table_name="message_candidates")
    op.drop_table("message_candidates")
    op.drop_table("context_snapshots")
