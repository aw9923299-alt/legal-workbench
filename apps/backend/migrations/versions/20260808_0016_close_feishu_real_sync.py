"""Close real Feishu personal sync reliability and provenance gaps.

Revision ID: 20260808_0016
Revises: 20260808_0015
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260808_0016"
down_revision: str | None = "20260808_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The table was renamed from ``feishu_attachments`` in revision 0008;
    # PostgreSQL retained the original convention-expanded constraint name.
    op.execute(
        "ALTER TABLE message_attachments DROP CONSTRAINT "
        "ck_feishu_attachments_ck_feishu_attachments_download_status"
    )
    op.create_check_constraint(
        "attachment_download_status",
        "message_attachments",
        "download_status IN "
        "('pending','downloading','downloaded','failed','not_requested','metadata_only')",
    )

    op.add_column(
        "feishu_events",
        sa.Column(
            "source_channel",
            sa.String(length=24),
            server_default="app_event",
            nullable=False,
        ),
    )
    op.add_column(
        "feishu_events",
        sa.Column(
            "provenance",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "feishu_event_source_channel",
        "feishu_events",
        "source_channel IN ('app_event','user_api','local_client')",
    )

    op.add_column(
        "feishu_messages",
        sa.Column(
            "source_channel",
            sa.String(length=24),
            server_default="app_event",
            nullable=False,
        ),
    )
    op.add_column(
        "feishu_messages",
        sa.Column(
            "source_channels",
            postgresql.JSONB(),
            server_default=sa.text("'[\"app_event\"]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "feishu_messages",
        sa.Column(
            "provenance",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "feishu_message_source_channel",
        "feishu_messages",
        "source_channel IN ('app_event','user_api','local_client')",
    )
    op.create_check_constraint(
        "feishu_message_source_channels_array",
        "feishu_messages",
        "jsonb_typeof(source_channels) = 'array'",
    )

    op.add_column(
        "feishu_sync_checkpoints",
        sa.Column("lease_owner", sa.String(length=80)),
    )
    op.add_column(
        "feishu_sync_checkpoints",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "feishu_sync_checkpoints",
        sa.Column("lease_fence", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "feishu_sync_checkpoint_lease_pair",
        "feishu_sync_checkpoints",
        "(lease_owner IS NULL) = (lease_expires_at IS NULL)",
    )
    op.create_check_constraint(
        "feishu_sync_checkpoint_fence_nonnegative",
        "feishu_sync_checkpoints",
        "lease_fence >= 0",
    )

    op.add_column(
        "feishu_user_authorizations",
        sa.Column("pending_token_version", sa.Integer()),
    )
    op.add_column(
        "feishu_user_authorizations",
        sa.Column("pending_token_bundle_ref", sa.String(length=120)),
    )
    op.add_column(
        "feishu_user_authorizations",
        sa.Column("rotation_owner", sa.String(length=80)),
    )
    op.add_column(
        "feishu_user_authorizations",
        sa.Column("rotation_expires_at", sa.DateTime(timezone=True)),
    )
    op.create_check_constraint(
        "feishu_user_authorization_pending_generation",
        "feishu_user_authorizations",
        "(pending_token_version IS NULL AND pending_token_bundle_ref IS NULL "
        "AND rotation_owner IS NULL AND rotation_expires_at IS NULL) OR "
        "(pending_token_version > token_version AND pending_token_bundle_ref IS NOT NULL "
        "AND rotation_owner IS NOT NULL AND rotation_expires_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "feishu_user_authorization_pending_generation",
        "feishu_user_authorizations",
        type_="check",
    )
    op.drop_column("feishu_user_authorizations", "rotation_expires_at")
    op.drop_column("feishu_user_authorizations", "rotation_owner")
    op.drop_column("feishu_user_authorizations", "pending_token_bundle_ref")
    op.drop_column("feishu_user_authorizations", "pending_token_version")

    op.drop_constraint(
        "feishu_sync_checkpoint_fence_nonnegative",
        "feishu_sync_checkpoints",
        type_="check",
    )
    op.drop_constraint(
        "feishu_sync_checkpoint_lease_pair",
        "feishu_sync_checkpoints",
        type_="check",
    )
    op.drop_column("feishu_sync_checkpoints", "lease_fence")
    op.drop_column("feishu_sync_checkpoints", "lease_expires_at")
    op.drop_column("feishu_sync_checkpoints", "lease_owner")

    op.drop_constraint(
        "feishu_message_source_channels_array",
        "feishu_messages",
        type_="check",
    )
    op.drop_constraint(
        "feishu_message_source_channel", "feishu_messages", type_="check"
    )
    op.drop_column("feishu_messages", "provenance")
    op.drop_column("feishu_messages", "source_channels")
    op.drop_column("feishu_messages", "source_channel")

    op.drop_constraint(
        "feishu_event_source_channel", "feishu_events", type_="check"
    )
    op.drop_column("feishu_events", "provenance")
    op.drop_column("feishu_events", "source_channel")

    op.execute(
        "UPDATE message_attachments SET download_status = 'failed' "
        "WHERE download_status = 'metadata_only'"
    )
    op.drop_constraint(
        "attachment_download_status",
        "message_attachments",
        type_="check",
    )
    op.execute(
        "ALTER TABLE message_attachments ADD CONSTRAINT "
        "ck_feishu_attachments_ck_feishu_attachments_download_status "
        "CHECK (download_status IN "
        "('pending','downloading','downloaded','failed','not_requested'))"
    )
