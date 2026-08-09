"""Add local knowledge provenance, authority taxonomy and token audit fields.

Revision ID: 20260809_0019
Revises: 20260809_0018
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260809_0019"
down_revision: str | None = "20260809_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_packages",
        sa.Column(
            "grounding_payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("agent_plan_steps", sa.Column("latest_valid_run_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_agent_plan_steps_latest_valid_run_id",
        "agent_plan_steps",
        "agent_runs",
        ["latest_valid_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_plan_steps_latest_valid_run_id",
        "agent_plan_steps",
        ["latest_valid_run_id"],
    )
    op.execute(
        "UPDATE agent_plan_steps SET latest_valid_run_id = latest_run_id "
        "WHERE status IN ('completed','needs_information')"
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "dependency_run_ids",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "local_knowledge_scans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_root_key", sa.String(length=120), nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("discovered_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unchanged_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("imported_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deduplicated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unsupported_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("missing_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running','completed','partial','failed')",
            name="local_knowledge_scan_status",
        ),
        sa.CheckConstraint(
            "discovered_count >= 0 AND unchanged_count >= 0 AND imported_count >= 0 "
            "AND deduplicated_count >= 0 "
            "AND failed_count >= 0 AND unsupported_count >= 0 AND missing_count >= 0",
            name="local_knowledge_scan_counts_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_local_knowledge_scans_root_started",
        "local_knowledge_scans",
        ["source_root_key", "started_at"],
    )
    op.create_index(
        "ix_local_knowledge_scans_status_started",
        "local_knowledge_scans",
        ["status", "started_at"],
    )

    op.create_table(
        "local_document_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_root_key", sa.String(length=120), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('active','missing','disabled')",
            name="local_document_source_status",
        ),
        sa.CheckConstraint("version > 0", name="local_document_source_version_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_root_key", "relative_path", name="uq_local_document_source_path"
        ),
    )
    op.create_index(
        "ix_local_document_sources_root_status",
        "local_document_sources",
        ["source_root_key", "status"],
    )

    op.drop_constraint(
        "document_version_exactly_one_source", "document_versions", type_="check"
    )
    op.add_column("document_versions", sa.Column("local_source_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_document_versions_local_source_id",
        "document_versions",
        "local_document_sources",
        ["local_source_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "document_version_exactly_one_source",
        "document_versions",
        "num_nonnulls(attachment_id, feishu_document_id, local_source_id) = 1",
    )
    op.create_index(
        "ix_document_versions_local_source_id",
        "document_versions",
        ["local_source_id"],
    )
    op.create_index(
        "uq_document_versions_local_version",
        "document_versions",
        ["local_source_id", "version"],
        unique=True,
        postgresql_where=sa.text("local_source_id IS NOT NULL"),
    )
    op.create_index(
        "uq_document_versions_local_sha256",
        "document_versions",
        ["local_source_id", "content_sha256"],
        unique=True,
        postgresql_where=sa.text("local_source_id IS NOT NULL"),
    )

    op.drop_constraint(
        "document_segment_exactly_one_source", "document_segments", type_="check"
    )
    op.add_column("document_segments", sa.Column("local_source_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_document_segments_local_source_id",
        "document_segments",
        "local_document_sources",
        ["local_source_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "document_segment_exactly_one_source",
        "document_segments",
        "num_nonnulls(attachment_id, feishu_document_id, local_source_id) = 1",
    )
    op.create_index(
        "ix_document_segments_local_source_id",
        "document_segments",
        ["local_source_id"],
    )
    op.create_index(
        "ix_document_segments_local_order",
        "document_segments",
        ["local_source_id", "paragraph_number"],
    )

    op.create_table(
        "local_document_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("local_source_id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid()),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("modified_at_ns", sa.BigInteger(), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("size >= 0", name="local_document_observation_size_nonnegative"),
        sa.CheckConstraint(
            "modified_at_ns >= 0", name="local_document_observation_mtime_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["local_source_id"], ["local_document_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["local_knowledge_scans.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "local_source_id", "scan_id", name="uq_local_document_observation_scan"
        ),
    )
    op.create_index(
        "ix_local_document_observations_local_source_id",
        "local_document_observations",
        ["local_source_id"],
    )
    op.create_index(
        "ix_local_document_observations_scan_id",
        "local_document_observations",
        ["scan_id"],
    )
    op.create_index(
        "ix_local_document_observations_document_version_id",
        "local_document_observations",
        ["document_version_id"],
    )
    op.create_index(
        "ix_local_document_observations_source_seen",
        "local_document_observations",
        ["local_source_id", "observed_at"],
    )
    op.create_index(
        "ix_local_document_observations_sha256",
        "local_document_observations",
        ["content_sha256"],
    )

    op.add_column(
        "knowledge_documents",
        sa.Column("authority_type", sa.String(length=40), server_default="unknown", nullable=False),
    )
    op.add_column(
        "knowledge_documents", sa.Column("authority_role", sa.String(length=32))
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "authority_status", sa.String(length=20), server_default="unknown", nullable=False
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "metadata_status",
            sa.String(length=24),
            server_default="pending_metadata",
            nullable=False,
        ),
    )
    op.add_column("knowledge_documents", sa.Column("issuer", sa.String(length=300)))
    op.add_column(
        "knowledge_documents", sa.Column("document_number", sa.String(length=160))
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_check_constraint(
        "knowledge_authority_type",
        "knowledge_documents",
        "authority_type IN ('unknown','law','administrative_regulation',"
        "'judicial_interpretation','department_rule','local_regulation',"
        "'local_government_rule','normative_document','guiding_case','court_case',"
        "'regulatory_guidance','contract','company_policy','business_rule',"
        "'legal_opinion','internal_precedent')",
    )
    op.create_check_constraint(
        "knowledge_authority_role",
        "knowledge_documents",
        "authority_role IS NULL OR authority_role IN ('formal_legal_basis',"
        "'persuasive_authority','contractual_basis','internal_basis','strategy_reference')",
    )
    op.create_check_constraint(
        "knowledge_authority_status",
        "knowledge_documents",
        "authority_status IN ('effective','superseded','repealed','unknown')",
    )
    op.create_check_constraint(
        "knowledge_metadata_status",
        "knowledge_documents",
        "metadata_status IN ('ready','pending_metadata')",
    )
    op.create_check_constraint(
        "knowledge_authority_role_mapping",
        "knowledge_documents",
        "(authority_type = 'unknown' AND authority_role IS NULL "
        "AND metadata_status = 'pending_metadata') OR "
        "(authority_type IN ('law','administrative_regulation','judicial_interpretation',"
        "'department_rule','local_regulation','local_government_rule','normative_document') "
        "AND authority_role = 'formal_legal_basis') OR "
        "(authority_type IN ('guiding_case','court_case','regulatory_guidance') "
        "AND authority_role = 'persuasive_authority') OR "
        "(authority_type = 'contract' AND authority_role = 'contractual_basis') OR "
        "(authority_type IN ('company_policy','business_rule') "
        "AND authority_role = 'internal_basis') OR "
        "(authority_type IN ('legal_opinion','internal_precedent') "
        "AND authority_role = 'strategy_reference')",
    )
    op.create_index(
        "ix_knowledge_documents_authority",
        "knowledge_documents",
        ["enabled", "authority_role", "authority_status", "jurisdiction"],
    )

    op.add_column(
        "knowledge_chunks",
        sa.Column("estimated_token_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "token_estimator",
            sa.String(length=80),
            server_default="utf8-bytes-ceil-div-4-v1",
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "token_count_estimated", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.create_check_constraint(
        "knowledge_chunk_token_count_nonnegative",
        "knowledge_chunks",
        "estimated_token_count >= 0",
    )

    for column in (
        "candidate_count",
        "selected_chunk_count",
        "selected_token_count",
        "excluded_by_token_budget_count",
        "excluded_duplicate_count",
    ):
        op.add_column(
            "knowledge_retrieval_logs",
            sa.Column(column, sa.Integer(), server_default="0", nullable=False),
        )
    op.add_column(
        "knowledge_retrieval_logs",
        sa.Column(
            "budget",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "knowledge_retrieval_log_counts_nonnegative",
        "knowledge_retrieval_logs",
        "candidate_count >= 0 AND selected_chunk_count >= 0 "
        "AND selected_token_count >= 0 AND excluded_by_token_budget_count >= 0 "
        "AND excluded_duplicate_count >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "knowledge_retrieval_log_counts_nonnegative",
        "knowledge_retrieval_logs",
        type_="check",
    )
    op.drop_column("knowledge_retrieval_logs", "budget")
    for column in (
        "excluded_by_token_budget_count",
        "excluded_duplicate_count",
        "selected_token_count",
        "selected_chunk_count",
        "candidate_count",
    ):
        op.drop_column("knowledge_retrieval_logs", column)

    op.drop_constraint(
        "knowledge_chunk_token_count_nonnegative", "knowledge_chunks", type_="check"
    )
    op.drop_column("knowledge_chunks", "token_count_estimated")
    op.drop_column("knowledge_chunks", "token_estimator")
    op.drop_column("knowledge_chunks", "estimated_token_count")

    op.drop_index("ix_knowledge_documents_authority", table_name="knowledge_documents")
    for constraint in (
        "knowledge_authority_role_mapping",
        "knowledge_metadata_status",
        "knowledge_authority_status",
        "knowledge_authority_role",
        "knowledge_authority_type",
    ):
        op.drop_constraint(constraint, "knowledge_documents", type_="check")
    for column in (
        "enabled",
        "document_number",
        "issuer",
        "metadata_status",
        "authority_status",
        "authority_role",
        "authority_type",
    ):
        op.drop_column("knowledge_documents", column)

    op.drop_index(
        "ix_local_document_observations_sha256", table_name="local_document_observations"
    )
    op.drop_index(
        "ix_local_document_observations_source_seen",
        table_name="local_document_observations",
    )
    op.drop_index(
        "ix_local_document_observations_document_version_id",
        table_name="local_document_observations",
    )
    op.drop_index(
        "ix_local_document_observations_scan_id", table_name="local_document_observations"
    )
    op.drop_index(
        "ix_local_document_observations_local_source_id",
        table_name="local_document_observations",
    )
    op.drop_table("local_document_observations")

    op.drop_index("ix_document_segments_local_order", table_name="document_segments")
    op.drop_index("ix_document_segments_local_source_id", table_name="document_segments")
    op.drop_constraint(
        "document_segment_exactly_one_source", "document_segments", type_="check"
    )
    op.drop_constraint(
        "fk_document_segments_local_source_id", "document_segments", type_="foreignkey"
    )
    op.drop_column("document_segments", "local_source_id")
    op.create_check_constraint(
        "document_segment_exactly_one_source",
        "document_segments",
        "(attachment_id IS NULL) <> (feishu_document_id IS NULL)",
    )

    op.drop_index("uq_document_versions_local_sha256", table_name="document_versions")
    op.drop_index("uq_document_versions_local_version", table_name="document_versions")
    op.drop_index("ix_document_versions_local_source_id", table_name="document_versions")
    op.drop_constraint(
        "document_version_exactly_one_source", "document_versions", type_="check"
    )
    op.drop_constraint(
        "fk_document_versions_local_source_id", "document_versions", type_="foreignkey"
    )
    op.drop_column("document_versions", "local_source_id")
    op.create_check_constraint(
        "document_version_exactly_one_source",
        "document_versions",
        "(attachment_id IS NULL) <> (feishu_document_id IS NULL)",
    )

    op.drop_index("ix_local_document_sources_root_status", table_name="local_document_sources")
    op.drop_table("local_document_sources")
    op.drop_index("ix_local_knowledge_scans_status_started", table_name="local_knowledge_scans")
    op.drop_index("ix_local_knowledge_scans_root_started", table_name="local_knowledge_scans")
    op.drop_table("local_knowledge_scans")
    op.drop_column("agent_runs", "dependency_run_ids")
    op.drop_index(
        "ix_agent_plan_steps_latest_valid_run_id", table_name="agent_plan_steps"
    )
    op.drop_constraint(
        "fk_agent_plan_steps_latest_valid_run_id",
        "agent_plan_steps",
        type_="foreignkey",
    )
    op.drop_column("agent_plan_steps", "latest_valid_run_id")
    op.drop_column("review_packages", "grounding_payload")
