"""Complete Feishu local ingestion persistence.

Revision ID: 20260801_0005
Revises: 20260801_0004
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0005"
down_revision: str | None = "20260801_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_EMPTY_LIST = sa.text("'[]'::jsonb")
JSON_EMPTY_OBJECT = sa.text("'{}'::jsonb")
NOW = sa.func.now()


def upgrade() -> None:
    op.execute("UPDATE feishu_events SET tenant_key = '' WHERE tenant_key IS NULL")
    op.alter_column("feishu_events", "tenant_key", existing_type=sa.String(160), nullable=False)
    op.create_unique_constraint(
        "uq_feishu_events_tenant_event", "feishu_events", ["tenant_key", "event_id"]
    )
    op.execute("UPDATE feishu_messages SET tenant_key = '' WHERE tenant_key IS NULL")
    op.alter_column("feishu_messages", "tenant_key", existing_type=sa.String(160), nullable=False)

    op.add_column("feishu_messages", sa.Column("plain_text", sa.Text()))
    op.add_column(
        "feishu_messages",
        sa.Column(
            "structured_content",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_OBJECT,
            nullable=False,
        ),
    )
    op.add_column(
        "feishu_messages",
        sa.Column(
            "attachments", postgresql.JSONB(), server_default=JSON_EMPTY_LIST, nullable=False
        ),
    )
    op.add_column("feishu_messages", sa.Column("content_hash", sa.String(length=64)))
    op.add_column("feishu_messages", sa.Column("edited_at", sa.DateTime(timezone=True)))
    op.add_column("feishu_messages", sa.Column("recalled_at", sa.DateTime(timezone=True)))
    op.add_column("feishu_messages", sa.Column("unsupported_reason", sa.Text()))
    op.execute("UPDATE feishu_messages SET structured_content = content")
    op.execute("UPDATE feishu_messages SET plain_text = COALESCE(content ->> 'text', '')")
    # Existing audit rows predate canonical SHA-256 generation. Preserve them
    # with a deterministic 64-character legacy digest; all new writes use SHA-256.
    op.execute(
        "UPDATE feishu_messages SET content_hash = "
        "md5(raw_message::text) || md5(raw_message::text)"
    )
    op.alter_column("feishu_messages", "content_hash", nullable=False)
    op.drop_constraint("feishu_message_status", "feishu_messages", type_="check")
    op.create_check_constraint(
        "feishu_message_status",
        "feishu_messages",
        "status IN ('received','queued_for_analysis','context_prepared','agent_queued',"
        "'analysing','candidate_created','ignored','analysis_failed','dead_letter','unsupported')",
    )

    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration_type", sa.String(length=40), nullable=False),
        sa.Column("connection_mode", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("last_connected_at", sa.DateTime(timezone=True)),
        sa.Column("last_disconnected_at", sa.DateTime(timezone=True)),
        sa.Column("last_event_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=100)),
        sa.Column("last_error_message", sa.Text()),
        sa.Column("reconnect_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_reconcile_at", sa.DateTime(timezone=True)),
        sa.Column("last_reconcile_status", sa.String(length=40)),
        sa.Column("last_reconcile_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "connection_mode IN ('long_connection','webhook')",
            name="ck_integration_connections_mode",
        ),
        sa.CheckConstraint(
            "status IN ('disabled','starting','connected','degraded','disconnected','failed')",
            name="ck_integration_connections_status",
        ),
        sa.CheckConstraint("reconnect_count >= 0", name="ck_integration_connections_reconnect"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "integration_type",
            "connection_mode",
            name="uq_integration_connections_type_mode",
        ),
    )

    op.create_table(
        "feishu_message_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("feishu_message_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("plain_text", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "structured_content",
            postgresql.JSONB(),
            server_default=JSON_EMPTY_OBJECT,
            nullable=False,
        ),
        sa.Column(
            "attachments", postgresql.JSONB(), server_default=JSON_EMPTY_LIST, nullable=False
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True)),
        sa.Column("recalled_at", sa.DateTime(timezone=True)),
        sa.Column("is_recalled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_feishu_message_versions_revision"),
        sa.ForeignKeyConstraint(["feishu_message_id"], ["feishu_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["feishu_events.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feishu_message_id", "revision", name="uq_feishu_message_versions_revision"
        ),
    )
    op.create_index(
        "ix_feishu_message_versions_message_created",
        "feishu_message_versions",
        ["feishu_message_id", "created_at"],
    )
    op.execute(
        "INSERT INTO feishu_message_versions "
        "(id, feishu_message_id, event_id, revision, raw_payload, content_hash, "
        "plain_text, structured_content, attachments, is_recalled, created_at) "
        "SELECT gen_random_uuid(), id, event_id, 1, raw_message, content_hash, "
        "COALESCE(plain_text, ''), structured_content, attachments, false, created_at "
        "FROM feishu_messages"
    )

    op.create_table(
        "feishu_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("feishu_message_id", sa.Uuid(), nullable=False),
        sa.Column("message_version_id", sa.Uuid(), nullable=False),
        sa.Column("file_key", sa.String(length=240), nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=160)),
        sa.Column("size", sa.Integer()),
        sa.Column("sha256", sa.String(length=64)),
        sa.Column("local_path", sa.Text()),
        sa.Column("download_status", sa.String(length=24), nullable=False),
        sa.Column("download_error", sa.Text()),
        sa.Column(
            "authorized_for_analysis",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("size IS NULL OR size >= 0", name="ck_feishu_attachments_size"),
        sa.CheckConstraint(
            "download_status IN ('pending','downloading','downloaded','failed','not_requested')",
            name="ck_feishu_attachments_download_status",
        ),
        sa.ForeignKeyConstraint(["feishu_message_id"], ["feishu_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["message_version_id"], ["feishu_message_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_version_id", "file_key", name="uq_feishu_attachments_version_file"
        ),
    )
    op.create_index(
        "ix_feishu_attachments_status_created",
        "feishu_attachments",
        ["download_status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_feishu_attachments_status_created", table_name="feishu_attachments")
    op.drop_table("feishu_attachments")
    op.drop_index(
        "ix_feishu_message_versions_message_created", table_name="feishu_message_versions"
    )
    op.drop_table("feishu_message_versions")
    op.drop_table("integration_connections")

    op.drop_constraint("feishu_message_status", "feishu_messages", type_="check")
    op.execute("UPDATE feishu_messages SET status = 'ignored' WHERE status = 'unsupported'")
    op.create_check_constraint(
        "feishu_message_status",
        "feishu_messages",
        "status IN ('received','queued_for_analysis','context_prepared','agent_queued',"
        "'analysing','candidate_created','ignored','analysis_failed','dead_letter')",
    )
    op.drop_column("feishu_messages", "unsupported_reason")
    op.drop_column("feishu_messages", "recalled_at")
    op.drop_column("feishu_messages", "edited_at")
    op.drop_column("feishu_messages", "content_hash")
    op.drop_column("feishu_messages", "attachments")
    op.drop_column("feishu_messages", "structured_content")
    op.drop_column("feishu_messages", "plain_text")
    op.alter_column("feishu_messages", "tenant_key", existing_type=sa.String(160), nullable=True)
    op.drop_constraint("uq_feishu_events_tenant_event", "feishu_events", type_="unique")
    op.alter_column("feishu_events", "tenant_key", existing_type=sa.String(160), nullable=True)
