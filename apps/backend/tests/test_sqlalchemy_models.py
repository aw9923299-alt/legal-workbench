import legal_workbench.infrastructure.models  # noqa: F401
from legal_workbench.infrastructure.database import Base


def test_first_workflow_tables_are_registered() -> None:
    assert set(Base.metadata.tables) >= {
        "context_snapshots",
        "message_candidates",
        "legal_matters",
        "work_items",
        "candidate_matter_links",
        "audit_events",
        "outbox_events",
        "idempotency_records",
    }


def test_work_item_has_matter_foreign_key_and_version_column() -> None:
    table = Base.metadata.tables["work_items"]
    assert "matter_id" in table.c
    assert "version" in table.c
    assert any(fk.target_fullname == "legal_matters.id" for fk in table.c.matter_id.foreign_keys)


def test_outbox_tracks_correlation_and_has_partial_pending_index() -> None:
    table = Base.metadata.tables["outbox_events"]
    assert "correlation_id" in table.c
    pending_index = next(
        index for index in table.indexes if index.name == "ix_outbox_events_pending"
    )
    assert "published_at IS NULL" in str(pending_index.dialect_options["postgresql"]["where"])
