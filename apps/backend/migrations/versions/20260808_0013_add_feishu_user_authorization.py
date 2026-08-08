"""Add Feishu user OAuth authorization metadata.

Revision ID: 20260808_0013
Revises: 20260803_0012
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260808_0013"
down_revision: str | None = "20260803_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feishu_oauth_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("code_verifier_ref", sa.String(length=120), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("requested_by", sa.String(length=160), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash", name="uq_feishu_oauth_attempts_state_hash"),
    )
    op.create_table(
        "feishu_user_authorizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("open_id", sa.String(length=160), nullable=False),
        sa.Column("union_id", sa.String(length=160)),
        sa.Column("tenant_key", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=240)),
        sa.Column("scopes", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("access_token_ref", sa.String(length=120), nullable=False),
        sa.Column("refresh_token_ref", sa.String(length=120), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('connected','refreshing','reauth_required','expired','permission_missing','revoked','degraded')",
            name="feishu_user_authorization_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_key",
            "open_id",
            name="uq_feishu_user_authorization_identity",
        ),
    )


def downgrade() -> None:
    op.drop_table("feishu_user_authorizations")
    op.drop_table("feishu_oauth_attempts")
