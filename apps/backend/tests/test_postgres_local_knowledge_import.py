from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_local_import_is_incremental_versioned_and_read_only(
    tmp_path: Path,
) -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.application.local_knowledge_import import (
        LocalKnowledgeImportService,
    )
    from legal_workbench.infrastructure.models import (
        DocumentVersionModel,
        KnowledgeChunkModel,
        KnowledgeDocumentModel,
        LocalDocumentSourceModel,
    )
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
    from legal_workbench.integrations.document_extractors import (
        IsolatedExtractionProcessRunner,
    )

    source = tmp_path / "materials"
    source.mkdir()
    material = source / "法律" / "中华人民共和国示例法.txt"
    material.parent.mkdir()
    fixture_id = uuid4().hex
    original_text = f"第一条 这是不含真实信息的法律资料 fixture {fixture_id}。"
    changed_text = original_text + "\n第二条 变更内容。"
    material.write_text(original_text, encoding="utf-8")
    original_mode = material.stat().st_mode
    source_root_key = f"postgres-import-{uuid4().hex}"

    engine = create_async_engine(os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    uow_factory = SqlAlchemyUnitOfWorkFactory(session_factory)
    extractor = IsolatedExtractionProcessRunner(
        attachment_root=source,
        work_root=tmp_path / "extraction-work",
        max_file_bytes=1024 * 1024,
        timeout_seconds=10,
        max_output_bytes=1024 * 1024,
    )
    service = LocalKnowledgeImportService(uow_factory, extractor)
    try:
        initial = await service.execute(
            source=source,
            source_root_key=source_root_key,
            correlation_id=f"initial-{uuid4().hex}",
        )
        repeated = await service.execute(
            source=source,
            source_root_key=source_root_key,
            correlation_id=f"repeat-{uuid4().hex}",
        )
        material.write_text(changed_text, encoding="utf-8")
        changed = await service.execute(
            source=source,
            source_root_key=source_root_key,
            correlation_id=f"changed-{uuid4().hex}",
        )

        assert initial.imported_count == 1
        assert repeated.unchanged_count == 1
        assert changed.imported_count == 1
        assert material.read_text(encoding="utf-8") == changed_text
        assert material.stat().st_mode == original_mode

        async with session_factory() as session:
            source_id = await session.scalar(
                select(LocalDocumentSourceModel.id).where(
                    LocalDocumentSourceModel.source_root_key == source_root_key
                )
            )
            assert source_id is not None
            version_count = await session.scalar(
                select(func.count(DocumentVersionModel.id)).where(
                    DocumentVersionModel.local_source_id == source_id
                )
            )
            knowledge_count = await session.scalar(
                select(func.count(KnowledgeDocumentModel.id)).where(
                    KnowledgeDocumentModel.document_version_id.in_(
                        select(DocumentVersionModel.id).where(
                            DocumentVersionModel.local_source_id == source_id
                        )
                    )
                )
            )
            chunk_texts = list(
                (
                    await session.scalars(
                        select(KnowledgeChunkModel.text)
                        .join(
                            KnowledgeDocumentModel,
                            KnowledgeDocumentModel.id
                            == KnowledgeChunkModel.knowledge_document_id,
                        )
                        .where(
                            KnowledgeDocumentModel.document_version_id.in_(
                                select(DocumentVersionModel.id).where(
                                    DocumentVersionModel.local_source_id == source_id
                                )
                            )
                        )
                        .order_by(KnowledgeChunkModel.created_at)
                    )
                ).all()
            )

        assert version_count == 2
        assert knowledge_count == 2
        assert original_text in chunk_texts
        assert "第二条 变更内容。" in chunk_texts
    finally:
        await engine.dispose()
