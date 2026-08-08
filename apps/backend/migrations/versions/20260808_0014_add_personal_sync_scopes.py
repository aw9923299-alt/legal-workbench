"""Add personal Feishu scopes and durable sync checkpoints.

Revision ID: 20260808_0014
Revises: 20260808_0013
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260808_0014"
down_revision: str | None = "20260808_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_integration_scope", "integration_scopes", type_="unique")
    op.add_column(
        "integration_scopes",
        sa.Column("identity_type", sa.String(length=12), server_default="app", nullable=False),
    )
    op.add_column(
        "integration_scopes",
        sa.Column("scope_type", sa.String(length=12), server_default="group", nullable=False),
    )
    op.add_column(
        "integration_scopes",
        sa.Column("authorization_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "integration_scopes",
        sa.Column("backfill_days", sa.Integer(), server_default="7", nullable=False),
    )
    op.add_column(
        "integration_scopes",
        sa.Column("high_value_legal", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_check_constraint(
        "integration_scope_identity_type",
        "integration_scopes",
        "identity_type IN ('app','user')",
    )
    op.create_check_constraint(
        "integration_scope_type",
        "integration_scopes",
        "scope_type IN ('group','p2p')",
    )
    op.create_check_constraint(
        "integration_scope_backfill_days",
        "integration_scopes",
        "backfill_days IN (7,30,90)",
    )
    op.create_foreign_key(
        "fk_integration_scopes_user_authorization",
        "integration_scopes",
        "feishu_user_authorizations",
        ["authorization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_integration_scopes_authorization_id",
        "integration_scopes",
        ["authorization_id"],
    )
    op.create_unique_constraint(
        "uq_integration_scope",
        "integration_scopes",
        [
            "provider",
            "identity_type",
            "authorization_id",
            "scope_type",
            "external_scope_id",
        ],
        postgresql_nulls_not_distinct=True,
    )
    op.create_table(
        "feishu_sync_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("watermark", sa.DateTime(timezone=True)),
        sa.Column("page_token", sa.String(length=400)),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(length=100)),
        sa.Column("last_started_at", sa.DateTime(timezone=True)),
        sa.Column("last_succeeded_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["authorization_id"],
            ["feishu_user_authorizations.id"],
            name="fk_sync_checkpoints_user_authorization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scope_id"],
            ["integration_scopes.id"],
            name="fk_feishu_sync_checkpoints_scope_id_integration_scopes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "authorization_id",
            "scope_id",
            name="uq_feishu_sync_checkpoint_authorization_scope",
        ),
    )
    op.create_index(
        "ix_feishu_sync_checkpoints_authorization_id",
        "feishu_sync_checkpoints",
        ["authorization_id"],
    )
    op.create_index(
        "ix_feishu_sync_checkpoints_scope_id",
        "feishu_sync_checkpoints",
        ["scope_id"],
    )
    op.add_column(
        "feishu_messages",
        sa.Column("analysis_disposition", sa.String(length=20), server_default="analyze", nullable=False),
    )
    op.add_column(
        "feishu_messages",
        sa.Column(
            "analysis_policy_version",
            sa.String(length=80),
            server_default="legacy-app-event-v1",
            nullable=False,
        ),
    )
    op.add_column(
        "feishu_messages",
        sa.Column("analysis_reasons", postgresql.JSONB(), server_default="[]", nullable=False),
    )
    op.create_check_constraint(
        "feishu_message_analysis_disposition",
        "feishu_messages",
        "analysis_disposition IN ('analyze','store_only')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "feishu_message_analysis_disposition", "feishu_messages", type_="check"
    )
    op.drop_column("feishu_messages", "analysis_reasons")
    op.drop_column("feishu_messages", "analysis_policy_version")
    op.drop_column("feishu_messages", "analysis_disposition")
    op.drop_index("ix_feishu_sync_checkpoints_scope_id", table_name="feishu_sync_checkpoints")
    op.drop_index(
        "ix_feishu_sync_checkpoints_authorization_id",
        table_name="feishu_sync_checkpoints",
    )
    op.drop_table("feishu_sync_checkpoints")
    op.drop_constraint("uq_integration_scope", "integration_scopes", type_="unique")
    op.drop_index("ix_integration_scopes_authorization_id", table_name="integration_scopes")
    op.drop_constraint(
        "fk_integration_scopes_user_authorization",
        "integration_scopes",
        type_="foreignkey",
    )
    op.drop_constraint("integration_scope_backfill_days", "integration_scopes", type_="check")
    op.drop_constraint("integration_scope_type", "integration_scopes", type_="check")
    op.drop_constraint("integration_scope_identity_type", "integration_scopes", type_="check")
    op.drop_column("integration_scopes", "backfill_days")
    op.drop_column("integration_scopes", "high_value_legal")
    op.drop_column("integration_scopes", "authorization_id")
    op.drop_column("integration_scopes", "scope_type")
    op.drop_column("integration_scopes", "identity_type")
    op.create_unique_constraint(
        "uq_integration_scope",
        "integration_scopes",
        ["provider", "external_scope_id"],
    )
