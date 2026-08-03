from __future__ import annotations

from pathlib import Path
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.feishu_operations import FeishuOperationsService
from legal_workbench.config import Settings
from legal_workbench.domain.entities import FeishuMessage, MessageAttachment, OutboxEvent
from legal_workbench.domain.enums import (
    AttachmentDownloadStatus,
    DocumentExtractionStatus,
)
from legal_workbench.integrations.feishu_client import FeishuApiError


class _Client:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    async def download_message_resource(self, **_: object) -> tuple[bytes, str, int]:
        if self.error is not None:
            raise self.error
        content = "附件正文".encode()
        return content, "text/plain", len(content)


class _FeishuRepository:
    def __init__(self, state: _State) -> None:
        self.state = state

    async def get_message_by_id(self, message_id: UUID) -> FeishuMessage | None:
        return self.state.message if self.state.message.id == message_id else None

    async def list_pending_attachments(
        self, message_id: UUID
    ) -> tuple[MessageAttachment, ...]:
        if self.state.attachment.feishu_message_id != message_id:
            return ()
        if self.state.attachment.download_status != AttachmentDownloadStatus.PENDING:
            return ()
        return (self.state.attachment,)

    async def list_attachments(
        self, message_id: UUID
    ) -> tuple[MessageAttachment, ...]:
        return (
            (self.state.attachment,)
            if self.state.attachment.feishu_message_id == message_id
            else ()
        )

    async def save_attachment(self, attachment: MessageAttachment) -> None:
        self.state.attachment = attachment


class _QuotaRepository:
    def __init__(self, state: _State) -> None:
        self.state = state

    async def reserve(self, **_: object) -> UUID | None:
        if not self.state.quota_available:
            return None
        self.state.reservation = uuid4()
        return self.state.reservation

    async def commit(self, reservation_token: UUID) -> None:
        assert reservation_token == self.state.reservation
        self.state.quota_status = "committed"

    async def release(self, reservation_token: UUID) -> None:
        assert reservation_token == self.state.reservation
        self.state.quota_status = "released"


class _OutboxRepository:
    def __init__(self, state: _State) -> None:
        self.state = state

    async def add(self, event: OutboxEvent) -> None:
        self.state.outbox.append(event)

    async def exists_pending(self, *, event_type: str, aggregate_id: UUID) -> bool:
        return any(
            value.event_type == event_type and value.aggregate_id == aggregate_id
            for value in self.state.outbox
        )


class _UnitOfWork:
    def __init__(self, state: _State) -> None:
        self.state = state
        self.feishu = _FeishuRepository(state)
        self.storage_quota = _QuotaRepository(state)
        self.outbox_events = _OutboxRepository(state)

    async def __aenter__(self) -> _UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.state.commits += 1

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        del operation, key


class _State:
    def __init__(self) -> None:
        self.message = FeishuMessage(
            id=uuid4(),
            event_id=uuid4(),
            tenant_key="../../tenant",
            message_id="om-download",
            chat_id="oc-test",
            thread_id=None,
            root_id=None,
            parent_id=None,
            sender_id="ou-test",
            sender_type="user",
            message_type="file",
            content={},
            mentions=[],
            create_time=None,
            update_time=None,
            raw_message={},
        )
        self.attachment = MessageAttachment(
            id=uuid4(),
            feishu_message_id=self.message.id,
            message_version_id=uuid4(),
            file_key="file-test",
            file_name="../../合同.txt",
            mime_type=None,
            size=None,
            download_status=AttachmentDownloadStatus.PENDING,
        )
        self.quota_available = True
        self.reservation: UUID | None = None
        self.quota_status: str | None = None
        self.outbox: list[OutboxEvent] = []
        self.commits = 0

    def factory(self) -> _UnitOfWork:
        return _UnitOfWork(self)


def _settings(root: str) -> Settings:
    return Settings(
        enable_real_feishu=True,
        feishu_app_id="cli-test",
        feishu_app_secret="local-test-secret",
        feishu_attachment_root=root,
        feishu_attachment_max_bytes=1024,
        feishu_attachment_total_quota_bytes=4096,
        _env_file=None,
    )


@pytest.mark.asyncio
async def test_download_uses_safe_path_and_enqueues_extraction(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = _State()
    root = tmp_path / "attachments"

    await FeishuOperationsService(
        settings=_settings(str(root)),
        uow_factory=state.factory,
        client=_Client(),  # type: ignore[arg-type]
    ).download_attachments(state.message.id)

    attachment = state.attachment
    assert attachment.download_status == AttachmentDownloadStatus.DOWNLOADED
    assert attachment.extraction_status == DocumentExtractionStatus.PENDING
    assert attachment.local_path is not None
    stored = Path(attachment.local_path)
    assert stored.resolve().is_relative_to(root.resolve())
    assert stored.name.endswith("-合同.txt")
    assert state.quota_status == "committed"
    assert [value.event_type for value in state.outbox] == [
        "DocumentExtractionRequested"
    ]


@pytest.mark.asyncio
async def test_quota_failure_persists_code_without_external_error_text(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = _State()
    state.quota_available = False

    await FeishuOperationsService(
        settings=_settings(str(tmp_path / "attachments")),
        uow_factory=state.factory,
        client=_Client(),  # type: ignore[arg-type]
    ).download_attachments(state.message.id)

    assert state.attachment.download_status == AttachmentDownloadStatus.FAILED
    assert state.attachment.download_error == "ATTACHMENT_STORAGE_QUOTA_EXCEEDED"
    assert [value.event_type for value in state.outbox] == [
        "FeishuMessageAnalysisRequested"
    ]


@pytest.mark.asyncio
async def test_download_failure_does_not_store_sensitive_response(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = _State()

    await FeishuOperationsService(
        settings=_settings(str(tmp_path / "attachments")),
        uow_factory=state.factory,
        client=_Client(error=FeishuApiError("secret response body")),  # type: ignore[arg-type]
    ).download_attachments(state.message.id)

    assert state.attachment.download_error == "FEISHU_ATTACHMENT_DOWNLOAD_FAILED"
    assert "secret" not in (state.attachment.download_error or "")
