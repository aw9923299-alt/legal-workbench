from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.context_snapshots import ContextSnapshotBuilder
from legal_workbench.domain.entities import (
    ContextSnapshot,
    DocumentSegment,
    FeishuMessage,
    MessageAttachment,
)
from legal_workbench.domain.enums import (
    AttachmentDownloadStatus,
    DocumentExtractionStatus,
)


def make_message(
    external_id: str,
    *,
    created_at: datetime,
    parent_id: str | None = None,
    text: str = "message",
) -> FeishuMessage:
    return FeishuMessage(
        id=uuid4(),
        event_id=uuid4(),
        tenant_key="tenant",
        message_id=external_id,
        chat_id="oc_chat",
        thread_id="omt_thread",
        root_id="om_root",
        parent_id=parent_id,
        sender_id=f"sender-{external_id}",
        sender_type="user",
        message_type="text",
        content={"text": text, "file_key": f"file-{external_id}"},
        mentions=[],
        create_time=created_at,
        update_time=None,
        raw_message={},
    )


class FakeFeishuRepository:
    def __init__(
        self,
        current: FeishuMessage,
        context: list[FeishuMessage],
        attachments: tuple[MessageAttachment, ...] = (),
    ) -> None:
        self.current = current
        self.context = context
        self.attachments = attachments

    async def get_message_by_id(self, message_id: UUID) -> FeishuMessage | None:
        return self.current if self.current.id == message_id else None

    async def list_context_messages(
        self, message: FeishuMessage, *, limit: int
    ) -> list[FeishuMessage]:
        assert message.id == self.current.id
        return self.context[:limit]

    async def list_attachments(self, message_id: UUID) -> tuple[MessageAttachment, ...]:
        return tuple(value for value in self.attachments if value.feishu_message_id == message_id)


class FakeDocumentRepository:
    def __init__(self, segments: tuple[DocumentSegment, ...] = ()) -> None:
        self.segments = segments

    async def list_latest_segments(self, attachment_ids: list[UUID]) -> tuple[DocumentSegment, ...]:
        allowed = set(attachment_ids)
        return tuple(value for value in self.segments if value.attachment_id in allowed)


class FakeSnapshotRepository:
    def __init__(self) -> None:
        self.values: list[ContextSnapshot] = []

    async def find_by_source_hash(
        self, *, source_type: str, source_id: str, content_hash: str
    ) -> ContextSnapshot | None:
        return next(
            (
                value
                for value in self.values
                if value.source_type == source_type
                and value.source_id == source_id
                and value.content_hash == content_hash
            ),
            None,
        )

    async def add(self, snapshot: ContextSnapshot) -> None:
        self.values.append(snapshot)


class FakeUnitOfWork:
    def __init__(
        self,
        feishu: FakeFeishuRepository,
        snapshots: FakeSnapshotRepository,
        documents: FakeDocumentRepository | None = None,
    ) -> None:
        self.feishu = feishu
        self.context_snapshots = snapshots
        self.documents = documents or FakeDocumentRepository()
        self.commits = 0

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        return None


@pytest.mark.asyncio
async def test_builder_is_bounded_deterministic_and_reuses_identical_snapshot() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    parent = make_message("om_parent", created_at=now - timedelta(minutes=2), text="P" * 90)
    sibling = make_message("om_sibling", created_at=now - timedelta(minutes=1), text="S" * 90)
    current = make_message("om_current", created_at=now, parent_id="om_parent", text="CURRENT" * 30)
    snapshots = FakeSnapshotRepository()
    uow = FakeUnitOfWork(FakeFeishuRepository(current, [current, sibling, parent]), snapshots)
    builder = ContextSnapshotBuilder(
        lambda: uow,
        max_messages=2,
        max_text_characters=120,
        now=lambda: now,
    )

    first = await builder.build_for_feishu_message(current.id)
    second = await builder.build_for_feishu_message(current.id)

    assert first.id == second.id
    assert len(snapshots.values) == 1
    assert first.message_ids == ["om_sibling", "om_current"]
    assert "om_current" in first.message_ids
    assert first.participant_ids == ["sender-om_current", "sender-om_sibling"]
    assert first.attachment_ids == ["file-om_current", "file-om_sibling"]
    assert len(first.content_hash) == 64
    assert first.content["truncated"] is True
    current_entry = next(
        value for value in first.content["messages"] if value["messageId"] == "om_current"
    )
    assert "CURRENT" in str(current_entry["content"])
    assert uow.commits == 1


@pytest.mark.asyncio
async def test_builder_hash_is_stable_for_different_repository_order() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    parent = make_message("om_parent", created_at=now - timedelta(minutes=1))
    current = make_message("om_current", created_at=now, parent_id="om_parent")
    first_store = FakeSnapshotRepository()
    second_store = FakeSnapshotRepository()

    first = await ContextSnapshotBuilder(
        lambda: FakeUnitOfWork(FakeFeishuRepository(current, [current, parent]), first_store),
        max_messages=10,
        max_text_characters=1000,
        now=lambda: now,
    ).build_for_feishu_message(current.id)
    second = await ContextSnapshotBuilder(
        lambda: FakeUnitOfWork(FakeFeishuRepository(current, [parent, current]), second_store),
        max_messages=10,
        max_text_characters=1000,
        now=lambda: now,
    ).build_for_feishu_message(current.id)

    assert first.content_hash == second.content_hash
    assert first.content == second.content


@pytest.mark.asyncio
async def test_builder_records_multidimensional_truncation_and_message_versions() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    current = make_message("om_current", created_at=now)
    current.version = 7
    current.content = {"text": "x" * 80}
    current.attachments = [
        {"fileKey": "file-1"},
        {"fileKey": "file-2"},
        {"fileKey": "file-3"},
    ]
    store = FakeSnapshotRepository()

    snapshot = await ContextSnapshotBuilder(
        lambda: FakeUnitOfWork(FakeFeishuRepository(current, [current]), store),
        max_messages=2,
        max_text_characters=40,
        max_single_message_characters=30,
        max_attachments=2,
        builder_version="2.0.0",
        selection_policy_version="thread-v2",
        now=lambda: now,
    ).build_for_feishu_message(current.id)

    assert snapshot.truncated is True
    assert "single_message_limit" in (snapshot.truncation_reason or "")
    assert "attachment_limit" in (snapshot.truncation_reason or "")
    assert snapshot.original_size > snapshot.included_size
    assert snapshot.builder_version == "2.0.0"
    assert snapshot.selection_policy_version == "thread-v2"
    assert snapshot.content["messages"][0]["messageVersion"] == 7  # type: ignore[index]
    assert len(snapshot.attachment_ids) == 2


@pytest.mark.asyncio
async def test_builder_includes_only_authorized_attachment_segments_with_citations() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    current = make_message("om_current", created_at=now, text="请审核附件合同")
    current.attachments = [{"fileKey": "file-om_current", "fileName": "合同.txt"}]
    attachment = MessageAttachment(
        id=uuid4(),
        feishu_message_id=current.id,
        message_version_id=uuid4(),
        file_key="file-om_current",
        file_name="合同.txt",
        mime_type="text/plain",
        size=8,
        download_status=AttachmentDownloadStatus.DOWNLOADED,
        authorized_for_analysis=True,
        extraction_status=DocumentExtractionStatus.SUCCEEDED,
    )
    segment = DocumentSegment(
        id=uuid4(),
        extraction_id=uuid4(),
        attachment_id=attachment.id,
        page_number=None,
        paragraph_number=1,
        start_offset=0,
        end_offset=8,
        content="合同期限一年。",
        content_hash="0" * 64,
    )
    uow = FakeUnitOfWork(
        FakeFeishuRepository(current, [current], (attachment,)),
        FakeSnapshotRepository(),
        FakeDocumentRepository((segment,)),
    )

    snapshot = await ContextSnapshotBuilder(
        lambda: uow,
        max_messages=2,
        max_text_characters=1000,
        now=lambda: now,
    ).build_for_feishu_message(current.id)

    assert snapshot.included_segments == [
        {
            "attachmentId": str(attachment.id),
            "fileName": "合同.txt",
            "pageNumber": None,
            "paragraphNumber": 1,
            "contentHash": "0" * 64,
        }
    ]
    assert snapshot.excluded_segments == []
    assert snapshot.content["attachmentSegments"][0]["content"] == "合同期限一年。"  # type: ignore[index]
    assert snapshot.permission_snapshot["allowedAttachmentIds"] == [str(attachment.id)]


@pytest.mark.asyncio
async def test_builder_bounds_attachment_segment_count_and_single_segment_size() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    current = make_message("om_current", created_at=now, text="附件")
    current.attachments = [{"fileKey": "file-om_current", "fileName": "合同.txt"}]
    attachment = MessageAttachment(
        id=uuid4(),
        feishu_message_id=current.id,
        message_version_id=uuid4(),
        file_key="file-om_current",
        file_name="合同.txt",
        mime_type="text/plain",
        size=20,
        download_status=AttachmentDownloadStatus.DOWNLOADED,
        authorized_for_analysis=True,
        extraction_status=DocumentExtractionStatus.SUCCEEDED,
    )
    segments = (
        DocumentSegment(
            id=uuid4(), extraction_id=uuid4(), attachment_id=attachment.id,
            page_number=None, paragraph_number=1, start_offset=0, end_offset=6,
            content="超过单段上限", content_hash="1" * 64,
        ),
        DocumentSegment(
            id=uuid4(), extraction_id=uuid4(), attachment_id=attachment.id,
            page_number=None, paragraph_number=2, start_offset=8, end_offset=10,
            content="可用", content_hash="2" * 64,
        ),
        DocumentSegment(
            id=uuid4(), extraction_id=uuid4(), attachment_id=attachment.id,
            page_number=None, paragraph_number=3, start_offset=12, end_offset=14,
            content="超额", content_hash="3" * 64,
        ),
    )
    uow = FakeUnitOfWork(
        FakeFeishuRepository(current, [current], (attachment,)),
        FakeSnapshotRepository(),
        FakeDocumentRepository(segments),
    )

    snapshot = await ContextSnapshotBuilder(
        lambda: uow,
        max_messages=2,
        max_text_characters=1000,
        max_attachment_segments=1,
        max_single_attachment_segment_characters=4,
        now=lambda: now,
    ).build_for_feishu_message(current.id)

    assert [value["paragraphNumber"] for value in snapshot.included_segments] == [2]
    assert [value["reason"] for value in snapshot.excluded_segments] == [
        "attachment_segment_character_limit",
        "attachment_segment_count_limit",
    ]
    assert snapshot.truncated is True
