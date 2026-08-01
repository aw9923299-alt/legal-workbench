"""Expand workflow with priority, deadlines, reviews, outbox and Feishu intake.

Revision ID: 20260801_0003
Revises: 20260801_0002
Create Date: 2026-08-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0003"
down_revision: str | None = "20260801_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_EMPTY_LIST = sa.text("'[]'::jsonb")
JSON_EMPTY_OBJECT = sa.text("'{}'::jsonb")
NOW = sa.func.now()

priority_confirmation_status = sa.Enum(
    "pending", "confirmed", "superseded",
    name="priority_confirmation_status", native_enum=False, create_constraint=True,
)
proposed_priority = sa.Enum(
    "urgent", "high", "medium", "low",
    name="proposed_priority", native_enum=False, create_constraint=True,
)
confirmed_priority = sa.Enum(
    "urgent", "high", "medium", "low",
    name="confirmed_priority", native_enum=False, create_constraint=True,
)
deadline_type = sa.Enum(
    "legal", "platform", "contractual", "business", "internal", "reminder",
    name="deadline_type", native_enum=False, create_constraint=True,
)
deadline_source = sa.Enum(
    "message_extracted", "document_extracted", "system_rule", "agent_suggested", "legal_confirmed",
    name="deadline_source", native_enum=False, create_constraint=True,
)
deadline_status = sa.Enum(
    "active", "satisfied", "missed", "cancelled", "superseded",
    name="deadline_status", native_enum=False, create_constraint=True,
)
dependency_type = sa.Enum(
    "finish_to_start", "start_to_start", "external_input", "approval", "material",
    name="dependency_type", native_enum=False, create_constraint=True,
)
dependency_status = sa.Enum(
    "active", "satisfied", "waived", "cancelled",
    name="dependency_status", native_enum=False, create_constraint=True,
)
review_package_type = sa.Enum(
    "external_message", "internal_message", "legal_analysis", "contract_review", "copy_review",
    name="review_package_type", native_enum=False, create_constraint=True,
)
review_package_status = sa.Enum(
    "draft", "pending_review", "approved", "rejected", "needs_information", "superseded",
    name="review_package_status", native_enum=False, create_constraint=True,
)
review_decision = sa.Enum(
    "approved", "approved_with_edits", "rejected", "needs_information",
    name="review_decision", native_enum=False, create_constraint=True,
)
communication_channel = sa.Enum(
    "feishu", name="communication_channel", native_enum=False, create_constraint=True,
)
communication_status = sa.Enum(
    "draft",
    "pending_review",
    "approved",
    "queued",
    "sending",
    "sent",
    "unknown",
    "failed",
    "dead_letter",
    name="communication_status", native_enum=False, create_constraint=True,
)
feishu_event_status = sa.Enum(
    "received", "duplicate", "processed", "ignored", "failed",
    name="feishu_event_status", native_enum=False, create_constraint=True,
)
feishu_message_status = sa.Enum(
    "received", "queued_for_analysis", "analyzed", "ignored", "failed",
    name="feishu_message_status", native_enum=False, create_constraint=True,
)


def upgrade() -> None:
    op.add_column("work_items", sa.Column("priority_confirmed_by", sa.String(length=160)))
    op.add_column("work_items", sa.Column("priority_confirmed_at", sa.DateTime(timezone=True)))

    op.add_column("outbox_events", sa.Column("locked_by", sa.String(length=120)))
    op.add_column("outbox_events", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("outbox_events", sa.Column("dead_lettered_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_outbox_events_dispatchable",
        "outbox_events",
        ["next_attempt_at", "occurred_at"],
        postgresql_where=sa.text("published_at IS NULL AND dead_lettered_at IS NULL"),
    )

    op.create_table(
        "priority_confirmations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_priority", proposed_priority, nullable=False),
        sa.Column("confirmed_priority", confirmed_priority, nullable=False),
        sa.Column("proposed_complete_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_complete_at", sa.DateTime(timezone=True)),
        sa.Column("reasons", postgresql.JSONB(), server_default=JSON_EMPTY_LIST, nullable=False),
        sa.Column("override_reason", sa.Text()),
        sa.Column("confirmed_by", sa.String(length=160), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("status", priority_confirmation_status, nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_priority_confirmations_work_item_created",
        "priority_confirmations", ["work_item_id", "created_at"],
    )

    op.create_table(
        "deadlines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("matter_id", sa.Uuid()),
        sa.Column("work_item_id", sa.Uuid()),
        sa.Column("deadline_type", deadline_type, nullable=False),
        sa.Column("source", deadline_source, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("is_hard", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", deadline_status, nullable=False),
        sa.Column("source_reference", sa.String(length=500)),
        sa.Column("confidence", sa.Float()),
        sa.Column(
            "reminder_policy",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_OBJECT,
            nullable=False,
        ),
        sa.Column("confirmed_by", sa.String(length=160)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "(matter_id IS NOT NULL AND work_item_id IS NULL) OR "
            "(matter_id IS NULL AND work_item_id IS NOT NULL)",
            name="deadline_exactly_one_owner",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="deadline_confidence_range",
        ),
        sa.ForeignKeyConstraint(["matter_id"], ["legal_matters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deadlines_matter_id", "deadlines", ["matter_id"])
    op.create_index("ix_deadlines_work_item_id", "deadlines", ["work_item_id"])
    op.create_index("ix_deadlines_active_due_at", "deadlines", ["status", "due_at"])

    op.create_table(
        "work_item_dependencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("depends_on_work_item_id", sa.Uuid()),
        sa.Column("dependency_type", dependency_type, nullable=False),
        sa.Column("status", dependency_status, nullable=False),
        sa.Column("external_party_id", sa.String(length=160)),
        sa.Column("description", sa.Text()),
        sa.Column("satisfied_at", sa.DateTime(timezone=True)),
        sa.Column("waived_by", sa.String(length=160)),
        sa.Column("waived_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "depends_on_work_item_id IS NULL OR depends_on_work_item_id <> work_item_id",
            name="dependency_not_self",
        ),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["depends_on_work_item_id"], ["work_items.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "work_item_id", "depends_on_work_item_id", "dependency_type",
            name="uq_work_item_dependency",
        ),
    )
    op.create_index(
        "ix_work_item_dependencies_work_item_id",
        "work_item_dependencies",
        ["work_item_id"],
    )
    op.create_index(
        "ix_work_item_dependencies_depends_on",
        "work_item_dependencies",
        ["depends_on_work_item_id"],
    )
    op.create_index(
        "ix_work_item_dependencies_active", "work_item_dependencies", ["work_item_id", "status"]
    )

    op.create_table(
        "review_packages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid()),
        sa.Column("package_type", review_package_type, nullable=False),
        sa.Column("status", review_package_status, nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("background", sa.Text(), nullable=False),
        sa.Column(
            "confirmed_facts",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column(
            "unconfirmed_facts",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("risks", postgresql.JSONB(), server_default=JSON_EMPTY_LIST, nullable=False),
        sa.Column(
            "alternatives",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column("citations", postgresql.JSONB(), server_default=JSON_EMPTY_LIST, nullable=False),
        sa.Column("proposed_content", sa.Text(), nullable=False),
        sa.Column("target", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_content_hash", sa.String(length=64)),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["matter_id"], ["legal_matters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_packages_matter_id", "review_packages", ["matter_id"])
    op.create_index("ix_review_packages_work_item_id", "review_packages", ["work_item_id"])
    op.create_index(
        "ix_review_packages_status_created",
        "review_packages",
        ["status", "created_at"],
    )

    op.create_table(
        "review_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_package_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.String(length=160), nullable=False),
        sa.Column("decision", review_decision, nullable=False),
        sa.Column("comments", sa.Text()),
        sa.Column("final_content", sa.Text()),
        sa.Column("final_content_hash", sa.String(length=64)),
        sa.Column(
            "change_summary",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_LIST,
            nullable=False,
        ),
        sa.Column(
            "reusable_as_example",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["review_package_id"],
            ["review_packages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_records_package_reviewed",
        "review_records",
        ["review_package_id", "reviewed_at"],
    )

    op.create_table(
        "communications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid()),
        sa.Column("review_package_id", sa.Uuid(), nullable=False),
        sa.Column("review_record_id", sa.Uuid(), nullable=False),
        sa.Column("channel", communication_channel, nullable=False),
        sa.Column("target", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", communication_status, nullable=False),
        sa.Column("requested_by", sa.String(length=160), nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("external_message_id", sa.String(length=160)),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("queued_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["matter_id"], ["legal_matters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_package_id"], ["review_packages.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["review_record_id"], ["review_records.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_record_id", name="uq_communications_review_record_id"),
    )
    op.create_index("ix_communications_matter_id", "communications", ["matter_id"])
    op.create_index("ix_communications_status_created", "communications", ["status", "created_at"])
    op.create_index("ix_communications_correlation_id", "communications", ["correlation_id"])

    op.create_table(
        "feishu_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("tenant_key", sa.String(length=160)),
        sa.Column("app_id", sa.String(length=160)),
        sa.Column("schema_version", sa.String(length=24)),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", feishu_event_status, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_feishu_events_event_id"),
    )
    op.create_index("ix_feishu_events_status_received", "feishu_events", ["status", "received_at"])

    op.create_table(
        "feishu_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_key", sa.String(length=160)),
        sa.Column("message_id", sa.String(length=160), nullable=False),
        sa.Column("chat_id", sa.String(length=160)),
        sa.Column("thread_id", sa.String(length=160)),
        sa.Column("root_id", sa.String(length=160)),
        sa.Column("parent_id", sa.String(length=160)),
        sa.Column("sender_id", sa.String(length=160)),
        sa.Column("sender_type", sa.String(length=40)),
        sa.Column("message_type", sa.String(length=40), nullable=False),
        sa.Column("content", postgresql.JSONB(), server_default=JSON_EMPTY_OBJECT, nullable=False),
        sa.Column("mentions", postgresql.JSONB(), server_default=JSON_EMPTY_LIST, nullable=False),
        sa.Column("create_time", sa.DateTime(timezone=True)),
        sa.Column("update_time", sa.DateTime(timezone=True)),
        sa.Column("raw_message", postgresql.JSONB(), nullable=False),
        sa.Column("status", feishu_message_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["feishu_events.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_key", "message_id", name="uq_feishu_messages_tenant_message"),
    )
    op.create_index("ix_feishu_messages_event_id", "feishu_messages", ["event_id"])
    op.create_index(
        "ix_feishu_messages_chat_created",
        "feishu_messages",
        ["chat_id", "create_time"],
    )
    op.create_index("ix_feishu_messages_sender_id", "feishu_messages", ["sender_id"])
    op.create_index(
        "ix_feishu_messages_status_created",
        "feishu_messages",
        ["status", "created_at"],
    )

    op.create_table(
        "outbox_dead_letters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("requeued_at", sa.DateTime(timezone=True)),
        sa.Column("requeued_event_id", sa.Uuid()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("original_event_id"),
    )
    op.create_index("ix_outbox_dead_letters_failed_at", "outbox_dead_letters", ["failed_at"])
    op.create_index(
        "ix_outbox_dead_letters_correlation_id",
        "outbox_dead_letters",
        ["correlation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_dead_letters_correlation_id", table_name="outbox_dead_letters")
    op.drop_index("ix_outbox_dead_letters_failed_at", table_name="outbox_dead_letters")
    op.drop_table("outbox_dead_letters")
    op.drop_index("ix_feishu_messages_status_created", table_name="feishu_messages")
    op.drop_index("ix_feishu_messages_sender_id", table_name="feishu_messages")
    op.drop_index("ix_feishu_messages_chat_created", table_name="feishu_messages")
    op.drop_index("ix_feishu_messages_event_id", table_name="feishu_messages")
    op.drop_table("feishu_messages")
    op.drop_index("ix_feishu_events_status_received", table_name="feishu_events")
    op.drop_table("feishu_events")
    op.drop_index("ix_communications_correlation_id", table_name="communications")
    op.drop_index("ix_communications_status_created", table_name="communications")
    op.drop_index("ix_communications_matter_id", table_name="communications")
    op.drop_table("communications")
    op.drop_index("ix_review_records_package_reviewed", table_name="review_records")
    op.drop_table("review_records")
    op.drop_index("ix_review_packages_status_created", table_name="review_packages")
    op.drop_index("ix_review_packages_work_item_id", table_name="review_packages")
    op.drop_index("ix_review_packages_matter_id", table_name="review_packages")
    op.drop_table("review_packages")
    op.drop_index("ix_work_item_dependencies_active", table_name="work_item_dependencies")
    op.drop_index("ix_work_item_dependencies_depends_on", table_name="work_item_dependencies")
    op.drop_index("ix_work_item_dependencies_work_item_id", table_name="work_item_dependencies")
    op.drop_table("work_item_dependencies")
    op.drop_index("ix_deadlines_active_due_at", table_name="deadlines")
    op.drop_index("ix_deadlines_work_item_id", table_name="deadlines")
    op.drop_index("ix_deadlines_matter_id", table_name="deadlines")
    op.drop_table("deadlines")
    op.drop_index(
        "ix_priority_confirmations_work_item_created",
        table_name="priority_confirmations",
    )
    op.drop_table("priority_confirmations")
    op.drop_index("ix_outbox_events_dispatchable", table_name="outbox_events")
    op.drop_column("outbox_events", "dead_lettered_at")
    op.drop_column("outbox_events", "next_attempt_at")
    op.drop_column("outbox_events", "locked_by")
    op.drop_column("work_items", "priority_confirmed_at")
    op.drop_column("work_items", "priority_confirmed_by")
