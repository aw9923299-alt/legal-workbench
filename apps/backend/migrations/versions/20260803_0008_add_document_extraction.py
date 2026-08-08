"""Add durable message attachment document extraction.

Revision ID: 20260803_0008
Revises: 20260803_0007
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260803_0008"
down_revision: str | None = "20260803_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.func.now()


def upgrade() -> None:
    op.add_column(
        "context_snapshots",
        sa.Column(
            "included_segments",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "context_snapshots",
        sa.Column(
            "excluded_segments",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.rename_table("feishu_attachments", "message_attachments")
    op.execute(
        "ALTER TABLE message_attachments RENAME CONSTRAINT "
        "uq_feishu_attachments_version_file "
        "TO uq_message_attachments_version_file"
    )
    op.execute(
        "ALTER INDEX ix_feishu_attachments_status_created "
        "RENAME TO ix_message_attachments_status_created"
    )
    op.add_column(
        "message_attachments",
        sa.Column(
            "extraction_status",
            sa.String(length=24),
            server_default="not_requested",
            nullable=False,
        ),
    )
    op.add_column("message_attachments", sa.Column("extractor_version", sa.String(length=80)))
    op.add_column("message_attachments", sa.Column("page_count", sa.Integer()))
    op.add_column("message_attachments", sa.Column("character_count", sa.Integer()))
    op.add_column("message_attachments", sa.Column("extraction_error_code", sa.String(length=100)))
    op.create_check_constraint(
        "ck_message_attachments_extraction_status",
        "message_attachments",
        "extraction_status IN "
        "('not_requested','pending','extracting','succeeded','body_unavailable','failed')",
    )
    op.create_check_constraint(
        "ck_message_attachments_extraction_counts",
        "message_attachments",
        "(page_count IS NULL OR page_count >= 0) AND "
        "(character_count IS NULL OR character_count >= 0)",
    )
    op.create_index(
        "ix_message_attachments_extraction_status",
        "message_attachments",
        ["extraction_status", "created_at"],
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attachment_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("local_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("version > 0", name="ck_document_versions_version"),
        sa.CheckConstraint("size >= 0", name="ck_document_versions_size"),
        sa.CheckConstraint("length(content_sha256) = 64", name="ck_document_versions_sha256"),
        sa.ForeignKeyConstraint(["attachment_id"], ["message_attachments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attachment_id", "version", name="uq_document_versions_attachment_version"
        ),
        sa.UniqueConstraint(
            "attachment_id",
            "content_sha256",
            name="uq_document_versions_attachment_sha256",
        ),
    )
    op.create_index(
        "ix_document_versions_attachment_created",
        "document_versions",
        ["attachment_id", "created_at"],
    )

    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("extractor_version", sa.String(length=80), nullable=False),
        sa.Column("page_count", sa.Integer()),
        sa.Column("character_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=100)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "status IN "
            "('not_requested','pending','extracting','succeeded','body_unavailable','failed')",
            name="ck_document_extractions_status",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_document_extractions_page_count",
        ),
        sa.CheckConstraint("character_count >= 0", name="ck_document_extractions_character_count"),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_extractions_version_created",
        "document_extractions",
        ["document_version_id", "created_at"],
    )
    op.create_index(
        "ix_document_extractions_status_started",
        "document_extractions",
        ["status", "started_at"],
    )

    op.create_table(
        "document_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column("attachment_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("paragraph_number", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number > 0",
            name="ck_document_segments_page_number",
        ),
        sa.CheckConstraint("paragraph_number > 0", name="ck_document_segments_paragraph_number"),
        sa.CheckConstraint(
            "start_offset >= 0 AND end_offset >= start_offset",
            name="ck_document_segments_offsets",
        ),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_document_segments_content_hash"),
        sa.ForeignKeyConstraint(["extraction_id"], ["document_extractions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attachment_id"], ["message_attachments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "extraction_id",
            "paragraph_number",
            name="uq_document_segments_extraction_paragraph",
        ),
    )
    op.create_index(
        "ix_document_segments_attachment_order",
        "document_segments",
        ["attachment_id", "page_number", "paragraph_number"],
    )

    op.create_table(
        "storage_quota_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attachment_id", sa.Uuid()),
        sa.Column("reservation_token", sa.Uuid(), nullable=False),
        sa.Column("requested_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("requested_bytes >= 0", name="ck_storage_quota_reservations_bytes"),
        sa.CheckConstraint(
            "status IN ('reserved','committed','released','expired')",
            name="ck_storage_quota_reservations_status",
        ),
        sa.ForeignKeyConstraint(["attachment_id"], ["message_attachments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reservation_token", name="uq_storage_quota_reservations_token"),
    )
    op.create_index(
        "ix_storage_quota_reservations_status_expiry",
        "storage_quota_reservations",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_storage_quota_reservations_status_expiry",
        table_name="storage_quota_reservations",
    )
    op.drop_table("storage_quota_reservations")
    op.drop_index("ix_document_segments_attachment_order", table_name="document_segments")
    op.drop_table("document_segments")
    op.drop_index("ix_document_extractions_status_started", table_name="document_extractions")
    op.drop_index("ix_document_extractions_version_created", table_name="document_extractions")
    op.drop_table("document_extractions")
    op.drop_index("ix_document_versions_attachment_created", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("ix_message_attachments_extraction_status", table_name="message_attachments")
    op.drop_constraint(
        "ck_message_attachments_extraction_counts",
        "message_attachments",
        type_="check",
    )
    op.drop_constraint(
        "ck_message_attachments_extraction_status",
        "message_attachments",
        type_="check",
    )
    op.drop_column("message_attachments", "extraction_error_code")
    op.drop_column("message_attachments", "character_count")
    op.drop_column("message_attachments", "page_count")
    op.drop_column("message_attachments", "extractor_version")
    op.drop_column("message_attachments", "extraction_status")
    op.execute(
        "ALTER INDEX ix_message_attachments_status_created "
        "RENAME TO ix_feishu_attachments_status_created"
    )
    op.execute(
        "ALTER TABLE message_attachments RENAME CONSTRAINT "
        "uq_message_attachments_version_file "
        "TO uq_feishu_attachments_version_file"
    )
    op.rename_table("message_attachments", "feishu_attachments")
    op.drop_column("context_snapshots", "excluded_segments")
    op.drop_column("context_snapshots", "included_segments")
