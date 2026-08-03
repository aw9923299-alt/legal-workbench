from __future__ import annotations

import os
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest

from legal_workbench.application.context_snapshots import ContextSnapshotBuilder
from legal_workbench.application.document_extraction import DocumentExtractionService
from legal_workbench.domain.entities import (
    FeishuMessage,
    FeishuMessageVersion,
    FeishuRawEvent,
    MessageAttachment,
)
from legal_workbench.domain.enums import (
    AttachmentDownloadStatus,
    DocumentExtractionStatus,
    FeishuEventStatus,
    FeishuMessageStatus,
)
from legal_workbench.integrations.document_extractors import extract_document


class _DirectExtractor:
    def extract(self, path, mime_type):  # type: ignore[no-untyped-def]
        return extract_document(path, mime_type)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_extraction_and_context_citations_persist_in_postgres(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    uow_factory = SqlAlchemyUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    content = "合同第一条。\n合同期限一年。"
    document = tmp_path / "合同.txt"
    document.write_text(content, encoding="utf-8")
    event = FeishuRawEvent(
        id=uuid4(),
        event_id=f"evt-document-{uuid4().hex}",
        event_type="integration.document",
        tenant_key="tenant-document-test",
        app_id="integration-test",
        schema_version="2.0-test",
        raw_payload={"test": True},
        payload_hash=sha256(b"document-event").hexdigest(),
        status=FeishuEventStatus.PROCESSED,
    )
    message = FeishuMessage(
        id=uuid4(),
        event_id=event.id,
        tenant_key=event.tenant_key,
        message_id=f"om-document-{uuid4().hex}",
        chat_id=f"oc-document-{uuid4().hex}",
        thread_id=None,
        root_id=None,
        parent_id=None,
        sender_id="ou-document-test",
        sender_type="user",
        message_type="file",
        content={"file_key": "file-document-test", "file_name": "合同.txt"},
        mentions=[],
        create_time=datetime.now(UTC),
        update_time=None,
        raw_message={"test": True},
        plain_text="合同.txt",
        attachments=[
            {"fileKey": "file-document-test", "fileName": "合同.txt"}
        ],
        status=FeishuMessageStatus.RECEIVED,
    )
    version = FeishuMessageVersion(
        id=uuid4(),
        feishu_message_id=message.id,
        event_id=event.id,
        revision=1,
        raw_payload={"test": True},
        content_hash=sha256(b"document-message-version").hexdigest(),
        plain_text=message.plain_text or "",
        structured_content=message.content,
        attachments=message.attachments,
    )
    attachment = MessageAttachment(
        id=uuid4(),
        feishu_message_id=message.id,
        message_version_id=version.id,
        file_key="file-document-test",
        file_name="合同.txt",
        mime_type="text/plain",
        size=document.stat().st_size,
        sha256=sha256(document.read_bytes()).hexdigest(),
        local_path=str(document),
        download_status=AttachmentDownloadStatus.DOWNLOADED,
        authorized_for_analysis=True,
        extraction_status=DocumentExtractionStatus.PENDING,
    )

    try:
        async with uow_factory() as uow:
            await uow.feishu.add_event(event)
            await uow.feishu.add_message(message)
            await uow.flush()
            await uow.feishu.add_message_version(version)
            await uow.flush()
            await uow.feishu.add_attachments([attachment])
            await uow.commit()

        service = DocumentExtractionService(
            uow_factory,
            _DirectExtractor(),
        )
        result = await service.execute(attachment.id)
        replay = await service.execute(attachment.id)
        snapshot = await ContextSnapshotBuilder(
            uow_factory,
            max_messages=5,
            max_text_characters=2000,
        ).build_for_feishu_message(message.id)

        async with engine.connect() as connection:
            extraction_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM document_extractions "
                    "WHERE document_version_id IN "
                    "(SELECT id FROM document_versions WHERE attachment_id = :id)"
                ),
                {"id": attachment.id},
            )
            segment_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM document_segments WHERE attachment_id = :id"
                ),
                {"id": attachment.id},
            )

        assert result.status == DocumentExtractionStatus.SUCCEEDED
        assert replay.extraction_id == result.extraction_id
        assert extraction_count == 1
        assert segment_count == 2
        assert len(snapshot.included_segments) == 2
        assert snapshot.included_segments[0]["attachmentId"] == str(attachment.id)
        assert snapshot.content["attachmentSegments"][1]["content"] == "合同期限一年。"  # type: ignore[index]
    finally:
        await engine.dispose()
