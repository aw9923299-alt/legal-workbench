from __future__ import annotations

import os
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest

from legal_workbench.application.context_snapshots import ContextSnapshotBuilder
from legal_workbench.application.document_extraction import DocumentExtractionService
from legal_workbench.application.feishu_documents import FeishuDocumentSyncService
from legal_workbench.domain.entities import (
    FeishuMessage,
    FeishuMessageVersion,
    FeishuRawEvent,
    FeishuUserAuthorization,
    MessageAttachment,
)
from legal_workbench.domain.enums import (
    AttachmentDownloadStatus,
    DocumentExtractionStatus,
    FeishuEventStatus,
    FeishuMessageStatus,
    FeishuUserAuthorizationStatus,
)
from legal_workbench.integrations.document_extractors import extract_document


class _DirectExtractor:
    def extract(self, path, mime_type):  # type: ignore[no-untyped-def]
        return extract_document(path, mime_type)


class _MarkdownClient:
    async def get_document_markdown(
        self, *, authorization_id, document_id  # type: ignore[no-untyped-def]
    ) -> str:
        del authorization_id
        assert document_id == "doccnContextTest"
        return "# 测试合同\n付款期限为七日。"


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_message_linked_native_docx_body_enters_context_snapshot() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    uow_factory = SqlAlchemyUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    now = datetime.now(UTC)
    authorization = FeishuUserAuthorization(
        id=uuid4(),
        open_id=f"ou-doc-{uuid4().hex}",
        union_id=None,
        tenant_key=f"tenant-doc-{uuid4().hex}",
        display_name="Native doc integration test",
        scopes=("offline_access", "docs:document.content:read"),
        access_token_ref=f"feishu_uat_{uuid4().hex}_v1",
        refresh_token_ref=f"feishu_urt_{uuid4().hex}_v1",
        access_expires_at=now.replace(year=now.year + 1),
        refresh_expires_at=now.replace(year=now.year + 1),
        token_version=1,
        status=FeishuUserAuthorizationStatus.CONNECTED,
    )
    event = FeishuRawEvent(
        id=uuid4(),
        event_id=f"evt-native-doc-{uuid4().hex}",
        event_type="integration.native-doc",
        tenant_key=authorization.tenant_key,
        app_id=None,
        schema_version="2.0-test",
        raw_payload={"test": True},
        payload_hash=sha256(b"native-doc-event").hexdigest(),
        status=FeishuEventStatus.PROCESSED,
    )
    message = FeishuMessage(
        id=uuid4(),
        event_id=event.id,
        tenant_key=authorization.tenant_key,
        message_id=f"om-native-doc-{uuid4().hex}",
        chat_id=f"oc-native-doc-{uuid4().hex}",
        thread_id=None,
        root_id=None,
        parent_id=None,
        sender_id=authorization.open_id,
        sender_type="user",
        message_type="text",
        content={"text": "请审核测试文档"},
        mentions=[],
        create_time=now,
        update_time=None,
        raw_message={"test": True},
        plain_text="请审核测试文档",
        status=FeishuMessageStatus.RECEIVED,
    )

    try:
        async with uow_factory() as uow:
            await uow.feishu_user_authorizations.add_authorization(authorization)
            await uow.feishu.add_event(event)
            await uow.feishu.add_message(message)
            await uow.commit()

        await FeishuDocumentSyncService(
            uow_factory,
            client=_MarkdownClient(),
        ).sync_document(
            authorization_id=authorization.id,
            document_token="doccnContextTest",
            document_type="docx",
            title="测试合同",
            source_url="https://acme.feishu.cn/docx/doccnContextTest",
            source_message_id=message.id,
        )
        snapshot = await ContextSnapshotBuilder(
            uow_factory,
            max_messages=5,
            max_text_characters=2000,
        ).build_for_feishu_message(message.id)

        assert snapshot.content["documentSegments"][1]["content"] == "付款期限为七日。"  # type: ignore[index]
        assert snapshot.content["documentSegments"][1]["untrustedInput"] is True  # type: ignore[index]
        assert snapshot.permission_snapshot["allowedFeishuDocumentTokens"] == [
            "doccnContextTest"
        ]
    finally:
        await engine.dispose()
