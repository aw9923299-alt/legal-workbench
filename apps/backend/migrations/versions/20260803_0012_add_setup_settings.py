"""Add durable local setup metadata and integration check runs.

Revision ID: 20260803_0012
Revises: 20260803_0011
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260803_0012"
down_revision: str | None = "20260803_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
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
    )


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("value_type", sa.String(length=24), nullable=False),
        sa.Column("updated_by", sa.String(length=160), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_system_settings_key"),
    )
    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("credential_kind", sa.String(length=80), nullable=False),
        sa.Column("secret_ref", sa.String(length=120)),
        sa.Column("configured", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("masked_hint", sa.String(length=40)),
        sa.Column("last_validated_at", sa.DateTime(timezone=True)),
        sa.Column("last_validation_status", sa.String(length=40)),
        sa.Column("last_error_code", sa.String(length=100)),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "NOT configured OR secret_ref IS NOT NULL",
            name="integration_credential_configured_has_reference",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "credential_kind", name="uq_integration_credential"),
    )
    op.create_table(
        "integration_scopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("external_scope_id", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=240)),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("sync_mode", sa.String(length=24), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=100)),
        sa.Column("last_error_message", sa.Text()),
        sa.Column("last_compensated_at", sa.DateTime(timezone=True)),
        sa.Column("last_compensation_status", sa.String(length=40)),
        sa.Column("approved_by", sa.String(length=160)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('unapproved','allowed','excluded','paused')",
            name="integration_scope_status",
        ),
        sa.CheckConstraint(
            "sync_mode IN ('mentions_only','all_messages','disabled')",
            name="integration_sync_mode",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_scope_id", name="uq_integration_scope"),
    )
    op.create_index(
        "ix_integration_scopes_provider_status",
        "integration_scopes",
        ["provider", "status"],
    )
    op.create_table(
        "integration_check_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("check_kind", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.String(length=160), nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=40), server_default="pending", nullable=False),
        sa.Column("error_code", sa.String(length=100)),
        sa.Column("detail", sa.Text()),
        sa.Column("runtime_version", sa.String(length=80)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','not_executed')",
            name="integration_check_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_integration_check_runs_correlation_id",
        "integration_check_runs",
        ["correlation_id"],
    )
    op.create_index(
        "ix_integration_check_runs_provider_kind_created",
        "integration_check_runs",
        ["provider", "check_kind", "created_at"],
    )
    op.create_index(
        "ix_integration_check_runs_status",
        "integration_check_runs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_check_runs_status", table_name="integration_check_runs")
    op.drop_index(
        "ix_integration_check_runs_provider_kind_created",
        table_name="integration_check_runs",
    )
    op.drop_index(
        "ix_integration_check_runs_correlation_id",
        table_name="integration_check_runs",
    )
    op.drop_table("integration_check_runs")
    op.drop_index("ix_integration_scopes_provider_status", table_name="integration_scopes")
    op.drop_table("integration_scopes")
    op.drop_table("integration_credentials")
    op.drop_table("system_settings")
