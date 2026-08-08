"""Add Feishu native documents to the existing document pipeline.

Revision ID: 20260808_0015
Revises: 20260808_0014
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260808_0015"
down_revision: str | None = "20260808_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "feishu_messages",
        sa.Column(
            "detected_document_links",
            postgresql.JSONB(),
            server_default="[]",
            nullable=False,
        ),
    )
    op.create_table(
        "feishu_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("document_token", sa.String(length=200), nullable=False),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500)),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("last_content_hash", sa.String(length=64)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "document_type IN ('docx','wiki')",
            name="feishu_document_type",
        ),
        sa.ForeignKeyConstraint(
            ["authorization_id"],
            ["feishu_user_authorizations.id"],
            name="fk_feishu_documents_authorization_id_feishu_user_authorizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "authorization_id",
            "document_token",
            name="uq_feishu_documents_authorization_token",
        ),
    )
    op.create_index(
        "ix_feishu_documents_authorization_id",
        "feishu_documents",
        ["authorization_id"],
    )

    op.drop_constraint(
        "uq_document_versions_attachment_version",
        "document_versions",
        type_="unique",
    )
    op.drop_constraint(
        "uq_document_versions_attachment_sha256",
        "document_versions",
        type_="unique",
    )
    op.add_column("document_versions", sa.Column("feishu_document_id", sa.Uuid()))
    op.alter_column("document_versions", "attachment_id", nullable=True)
    op.create_foreign_key(
        "fk_document_versions_feishu_document_id_feishu_documents",
        "document_versions",
        "feishu_documents",
        ["feishu_document_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "document_version_exactly_one_source",
        "document_versions",
        "(attachment_id IS NULL) <> (feishu_document_id IS NULL)",
    )
    op.create_index(
        "ix_document_versions_feishu_document_id",
        "document_versions",
        ["feishu_document_id"],
    )
    op.create_index(
        "uq_document_versions_attachment_version",
        "document_versions",
        ["attachment_id", "version"],
        unique=True,
        postgresql_where=sa.text("attachment_id IS NOT NULL"),
    )
    op.create_index(
        "uq_document_versions_attachment_sha256",
        "document_versions",
        ["attachment_id", "content_sha256"],
        unique=True,
        postgresql_where=sa.text("attachment_id IS NOT NULL"),
    )
    op.create_index(
        "uq_document_versions_feishu_version",
        "document_versions",
        ["feishu_document_id", "version"],
        unique=True,
        postgresql_where=sa.text("feishu_document_id IS NOT NULL"),
    )
    op.create_index(
        "uq_document_versions_feishu_sha256",
        "document_versions",
        ["feishu_document_id", "content_sha256"],
        unique=True,
        postgresql_where=sa.text("feishu_document_id IS NOT NULL"),
    )

    op.add_column("document_segments", sa.Column("feishu_document_id", sa.Uuid()))
    op.alter_column("document_segments", "attachment_id", nullable=True)
    op.create_foreign_key(
        "fk_document_segments_feishu_document_id_feishu_documents",
        "document_segments",
        "feishu_documents",
        ["feishu_document_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "document_segment_exactly_one_source",
        "document_segments",
        "(attachment_id IS NULL) <> (feishu_document_id IS NULL)",
    )
    op.create_index(
        "ix_document_segments_feishu_document_id",
        "document_segments",
        ["feishu_document_id"],
    )
    op.create_index(
        "ix_document_segments_feishu_order",
        "document_segments",
        ["feishu_document_id", "paragraph_number"],
    )

    op.create_table(
        "feishu_message_document_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("feishu_message_id", sa.Uuid(), nullable=False),
        sa.Column("feishu_document_id", sa.Uuid(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["feishu_message_id"],
            ["feishu_messages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["feishu_document_id"],
            ["feishu_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feishu_message_id",
            "feishu_document_id",
            name="uq_feishu_message_document_link",
        ),
    )
    op.create_table(
        "feishu_document_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("folder_token", sa.String(length=200), nullable=False),
        sa.Column("recursive", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["authorization_id"],
            ["feishu_user_authorizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "authorization_id",
            "folder_token",
            name="uq_feishu_document_subscription",
        ),
    )


def downgrade() -> None:
    op.drop_table("feishu_document_subscriptions")
    op.drop_table("feishu_message_document_links")
    op.drop_index("ix_document_segments_feishu_order", table_name="document_segments")
    op.drop_index("ix_document_segments_feishu_document_id", table_name="document_segments")
    op.drop_constraint(
        "document_segment_exactly_one_source", "document_segments", type_="check"
    )
    op.drop_constraint(
        "fk_document_segments_feishu_document_id_feishu_documents",
        "document_segments",
        type_="foreignkey",
    )
    op.drop_column("document_segments", "feishu_document_id")
    op.alter_column("document_segments", "attachment_id", nullable=False)

    op.drop_index("uq_document_versions_feishu_sha256", table_name="document_versions")
    op.drop_index("uq_document_versions_feishu_version", table_name="document_versions")
    op.drop_index("uq_document_versions_attachment_sha256", table_name="document_versions")
    op.drop_index("uq_document_versions_attachment_version", table_name="document_versions")
    op.drop_index("ix_document_versions_feishu_document_id", table_name="document_versions")
    op.drop_constraint(
        "document_version_exactly_one_source", "document_versions", type_="check"
    )
    op.drop_constraint(
        "fk_document_versions_feishu_document_id_feishu_documents",
        "document_versions",
        type_="foreignkey",
    )
    op.drop_column("document_versions", "feishu_document_id")
    op.alter_column("document_versions", "attachment_id", nullable=False)
    op.create_unique_constraint(
        "uq_document_versions_attachment_version",
        "document_versions",
        ["attachment_id", "version"],
    )
    op.create_unique_constraint(
        "uq_document_versions_attachment_sha256",
        "document_versions",
        ["attachment_id", "content_sha256"],
    )
    op.drop_index("ix_feishu_documents_authorization_id", table_name="feishu_documents")
    op.drop_table("feishu_documents")
    op.drop_column("feishu_messages", "detected_document_links")
