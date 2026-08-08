"""Harden Feishu token rotation crash recovery.

Revision ID: 20260808_0017
Revises: 20260808_0016
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0017"
down_revision: str | None = "20260808_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "feishu_user_authorizations",
        sa.Column(
            "rotation_phase",
            sa.String(length=24),
            server_default="idle",
            nullable=False,
        ),
    )
    op.add_column(
        "feishu_user_authorizations",
        sa.Column("rotation_request_started_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "feishu_user_authorizations",
        sa.Column("rotation_fence", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "feishu_user_authorizations",
        sa.Column("rotation_result_written_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "feishu_user_authorizations",
        sa.Column("rotation_reauth_reason", sa.String(length=100)),
    )
    op.create_check_constraint(
        "feishu_user_authorization_rotation_phase",
        "feishu_user_authorizations",
        "rotation_phase IN ('idle','claimed','request_started','result_durable','activated')",
    )
    op.create_check_constraint(
        "feishu_user_authorization_rotation_fence_nonnegative",
        "feishu_user_authorizations",
        "rotation_fence >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "feishu_user_authorization_rotation_fence_nonnegative",
        "feishu_user_authorizations",
        type_="check",
    )
    op.drop_constraint(
        "feishu_user_authorization_rotation_phase",
        "feishu_user_authorizations",
        type_="check",
    )
    op.drop_column("feishu_user_authorizations", "rotation_reauth_reason")
    op.drop_column("feishu_user_authorizations", "rotation_result_written_at")
    op.drop_column("feishu_user_authorizations", "rotation_fence")
    op.drop_column("feishu_user_authorizations", "rotation_request_started_at")
    op.drop_column("feishu_user_authorizations", "rotation_phase")
