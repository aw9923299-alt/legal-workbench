from sqlalchemy import Index, UniqueConstraint

from legal_workbench.infrastructure.database import Base
from legal_workbench.infrastructure.models import core as _core_models  # noqa: F401


def test_agent_runtime_tables_are_registered() -> None:
    expected = {
        "agent_definitions",
        "agent_runs",
        "agent_run_sources",
        "draft_artifacts",
    }

    assert expected <= set(Base.metadata.tables)


def test_agent_definition_key_and_version_are_unique() -> None:
    table = Base.metadata.tables["agent_definitions"]

    assert any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns} == {"key", "version"}
        for constraint in table.constraints
    )


def test_agent_run_has_auditable_foreign_keys_and_version() -> None:
    table = Base.metadata.tables["agent_runs"]
    foreign_keys = {foreign_key.target_fullname for foreign_key in table.foreign_keys}

    assert "agent_definitions.id" in foreign_keys
    assert "context_snapshots.id" in foreign_keys
    assert "feishu_messages.id" in foreign_keys
    assert "version" in table.c
    assert "correlation_id" in table.c


def test_message_candidate_is_directly_linked_to_source_message_and_run() -> None:
    table = Base.metadata.tables["message_candidates"]
    foreign_keys = {foreign_key.target_fullname for foreign_key in table.foreign_keys}

    assert "feishu_messages.id" in foreign_keys
    assert "agent_runs.id" in foreign_keys
    assert "requires_manual_review" in table.c
    assert "analysis_payload" in table.c


def test_context_snapshot_contains_immutable_bounded_content() -> None:
    table = Base.metadata.tables["context_snapshots"]

    assert {
        "source_id",
        "snapshot_version",
        "attachment_ids",
        "thread_metadata",
        "content",
        "content_hash",
    } <= set(table.c.keys())
    assert any(
        isinstance(index, Index)
        and {column.name for column in index.columns}
        == {"source_type", "source_id", "content_hash"}
        for index in table.indexes
    )
