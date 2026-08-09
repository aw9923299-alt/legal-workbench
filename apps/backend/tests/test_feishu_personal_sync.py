from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from uuid import UUID

import httpx
import pytest

from legal_workbench.application.commands import IngestFeishuEventCommand
from legal_workbench.application.feishu_personal_sync import (
    PersonalMessageSyncService,
    UserMessageIngestionAdapter,
)
from legal_workbench.application.results import FeishuEventIngestedResult
from legal_workbench.domain.entities import FeishuSyncCheckpoint, IntegrationScope
from legal_workbench.domain.enums import (
    IntegrationIdentityType,
    IntegrationScopeStatus,
    IntegrationScopeType,
    IntegrationSyncMode,
)
from legal_workbench.domain.errors import DomainValidationError
from legal_workbench.infrastructure.database import Base
from legal_workbench.integrations.feishu_user_client import (
    FeishuUserClient,
    UserMessagePage,
)

AUTHORIZATION_ID = UUID("00000000-0000-0000-0000-000000000201")
SCOPE_ID = UUID("00000000-0000-0000-0000-000000000202")


class CapturingHandler:
    def __init__(self, *, fail_message_id: str | None = None) -> None:
        self.commands: list[IngestFeishuEventCommand] = []
        self.fail_message_id = fail_message_id

    async def execute(self, command: IngestFeishuEventCommand) -> FeishuEventIngestedResult:
        message = command.raw_payload["event"]["message"]  # type: ignore[index]
        if message["message_id"] == self.fail_message_id:  # type: ignore[index]
            raise RuntimeError("synthetic ingestion failure")
        self.commands.append(command)
        return FeishuEventIngestedResult(
            event_id=UUID("00000000-0000-0000-0000-000000000205"),
            message_id=UUID("00000000-0000-0000-0000-000000000206"),
            duplicate=False,
        )


class CheckpointRepository:
    def __init__(self) -> None:
        self.value: FeishuSyncCheckpoint | None = None
        self.transaction_active = False

    async def get_checkpoint_for_update(
        self, *, authorization_id: UUID, scope_id: UUID
    ) -> FeishuSyncCheckpoint | None:
        return self.value

    async def add_checkpoint(self, value: FeishuSyncCheckpoint) -> None:
        self.value = value

    async def save_checkpoint(self, value: FeishuSyncCheckpoint) -> None:
        self.value = value


class UnitOfWork:
    def __init__(self, repository: CheckpointRepository) -> None:
        self.feishu_personal_sync = repository

    async def __aenter__(self) -> UnitOfWork:
        assert self.feishu_personal_sync.transaction_active is False
        self.feishu_personal_sync.transaction_active = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        self.feishu_personal_sync.transaction_active = False
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        del operation, key

    async def commit(self) -> None:
        return None


class UserClient:
    def __init__(
        self,
        pages: list[UserMessagePage],
        *,
        checkpoint_repository: CheckpointRepository | None = None,
    ) -> None:
        self.pages = pages
        self.calls: list[dict[str, object]] = []
        self.checkpoint_repository = checkpoint_repository

    async def list_messages(self, **kwargs: object) -> UserMessagePage:
        if self.checkpoint_repository is not None:
            assert self.checkpoint_repository.transaction_active is False
        self.calls.append(kwargs)
        return self.pages[len(self.calls) - 1]

    async def list_thread_messages(self, **kwargs: object) -> UserMessagePage:
        raise AssertionError(f"Unexpected thread history request: {kwargs}")


class DocumentLinkSync:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def sync_document(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return object()


class AttachmentSync:
    def __init__(self) -> None:
        self.message_ids: list[UUID] = []

    async def download_attachments(self, message_id: UUID) -> None:
        self.message_ids.append(message_id)


def allowed_scope() -> IntegrationScope:
    return IntegrationScope(
        id=SCOPE_ID,
        provider="feishu",
        external_scope_id="oc_group",
        display_name="Legal group",
        status=IntegrationScopeStatus.ALLOWED,
        sync_mode=IntegrationSyncMode.ALL_MESSAGES,
        identity_type=IntegrationIdentityType.USER,
        scope_type=IntegrationScopeType.GROUP,
        authorization_id=AUTHORIZATION_ID,
        backfill_days=30,
    )


def raw_message(message_id: str, created: int, updated: int | None = None) -> dict[str, object]:
    return {
        "message_id": message_id,
        "chat_id": "oc_group",
        "msg_type": "text",
        "body": {"content": '{"text":"合同需要今天审核"}'},
        "sender": {"id": "ou_sender", "id_type": "open_id", "sender_type": "user"},
        "create_time": str(created),
        "update_time": str(updated or created),
        "mentions": [],
    }


@pytest.mark.asyncio
async def test_user_message_adapter_always_uses_unified_ingestion_handler() -> None:
    handler = CapturingHandler()
    adapter = UserMessageIngestionAdapter(handler)

    await adapter.ingest(
        raw_message=raw_message("om-user-1", 1786150000000),
        tenant_key="tenant-personal",
        authorization_open_id="ou_personal",
        analysis_disposition="store_only",
        correlation_id="corr-user-sync",
    )

    command = handler.commands[0]
    assert command.event_id == (
        "uat:tenant-personal:om-user-1:1786150000000:feishu-personal-analysis-v2"
    )
    assert command.raw_payload["source"] == "user_history_sync"
    assert command.raw_payload["source_channel"] == "user_api"
    assert command.raw_payload["analysis_disposition"] == "store_only"
    assert command.raw_payload["event"]["message"]["message_type"] == "text"  # type: ignore[index]


@pytest.mark.asyncio
async def test_checkpoint_uses_overlap_and_advances_only_after_all_pages() -> None:
    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    repository = CheckpointRepository()
    repository.value = FeishuSyncCheckpoint(
        id=UUID("00000000-0000-0000-0000-000000000203"),
        authorization_id=AUTHORIZATION_ID,
        scope_id=SCOPE_ID,
        watermark=datetime(2026, 8, 8, 7, 0, tzinfo=UTC),
    )
    client = UserClient(
        [
            UserMessagePage(
                items=(raw_message("om-1", 1786173000000),),
                next_page_token="page-2",
            ),
            UserMessagePage(
                items=(raw_message("om-2", 1786176000000),),
                next_page_token=None,
            ),
        ],
        checkpoint_repository=repository,
    )
    handler = CapturingHandler()
    service = PersonalMessageSyncService(
        lambda: UnitOfWork(repository),
        user_client=client,
        ingestion_adapter=UserMessageIngestionAdapter(handler),
        overlap=timedelta(minutes=5),
        clock=lambda: now,
    )

    result = await service.sync_scope(scope=allowed_scope(), tenant_key="tenant-personal")

    assert result.ingested_count == 2
    assert client.calls[0]["start_time"] == datetime(2026, 8, 8, 6, 55, tzinfo=UTC)
    assert client.calls[1]["page_token"] == "page-2"
    assert repository.value is not None
    assert repository.value.watermark == now
    assert repository.value.consecutive_failures == 0
    assert repository.value.lease_owner is None
    assert repository.value.lease_expires_at is None
    assert repository.value.lease_fence == 1


@pytest.mark.asyncio
async def test_sync_result_exposes_distinct_claim_window_and_completion_times() -> None:
    claimed_at = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    renewed_at = datetime(2026, 8, 8, 8, 1, tzinfo=UTC)
    succeeded_at = datetime(2026, 8, 8, 8, 2, tzinfo=UTC)
    completed_at = datetime(2026, 8, 8, 8, 3, tzinfo=UTC)
    clock_values = iter((claimed_at, renewed_at, succeeded_at, completed_at))
    repository = CheckpointRepository()
    repository.value = FeishuSyncCheckpoint(
        id=UUID("00000000-0000-0000-0000-000000000203"),
        authorization_id=AUTHORIZATION_ID,
        scope_id=SCOPE_ID,
        watermark=datetime(2026, 8, 8, 7, 0, tzinfo=UTC),
    )
    client = UserClient([UserMessagePage(items=(), next_page_token=None)])
    service = PersonalMessageSyncService(
        lambda: UnitOfWork(repository),
        user_client=client,
        ingestion_adapter=UserMessageIngestionAdapter(CapturingHandler()),
        overlap=timedelta(minutes=5),
        clock=lambda: next(clock_values),
    )

    result = await service.sync_scope(scope=allowed_scope(), tenant_key="tenant-personal")

    assert result.claimed_at == claimed_at
    assert result.window_start == datetime(2026, 8, 8, 6, 55, tzinfo=UTC)
    assert result.window_end == claimed_at
    assert result.completed_at == completed_at
    assert client.calls == [
        {
            "authorization_id": AUTHORIZATION_ID,
            "chat_id": "oc_group",
            "start_time": result.window_start,
            "end_time": result.window_end,
            "page_token": None,
        }
    ]


@pytest.mark.asyncio
async def test_message_document_link_is_imported_through_native_document_pipeline() -> None:
    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    repository = CheckpointRepository()
    linked_message = raw_message("om-doc", 1786176000000)
    linked_message["body"] = {
        "content": '{"text":"请看 https://acme.feishu.cn/docx/doccnAbCdEf"}'
    }
    document_sync = DocumentLinkSync()
    service = PersonalMessageSyncService(
        lambda: UnitOfWork(repository),
        user_client=UserClient(
            [UserMessagePage(items=(linked_message,), next_page_token=None)]
        ),
        ingestion_adapter=UserMessageIngestionAdapter(CapturingHandler()),
        document_sync=document_sync,
        clock=lambda: now,
    )

    await service.sync_scope(scope=allowed_scope(), tenant_key="tenant-personal")

    assert document_sync.calls == [
        {
            "authorization_id": AUTHORIZATION_ID,
            "document_token": "doccnAbCdEf",
            "document_type": "docx",
            "title": None,
            "source_url": "https://acme.feishu.cn/docx/doccnAbCdEf",
            "source_message_id": UUID("00000000-0000-0000-0000-000000000206"),
        }
    ]


@pytest.mark.asyncio
async def test_missing_document_capability_does_not_fail_message_checkpoint() -> None:
    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    repository = CheckpointRepository()
    linked_message = raw_message("om-doc-metadata-only", 1786176000000)
    linked_message["body"] = {
        "content": '{"text":"请看 https://acme.feishu.cn/docx/doccnNoPermission"}'
    }
    service = PersonalMessageSyncService(
        lambda: UnitOfWork(repository),
        user_client=UserClient(
            [UserMessagePage(items=(linked_message,), next_page_token=None)]
        ),
        ingestion_adapter=UserMessageIngestionAdapter(CapturingHandler()),
        document_sync=None,
        clock=lambda: now,
    )

    result = await service.sync_scope(
        scope=allowed_scope(),
        tenant_key="tenant-personal",
    )

    assert result.ingested_count == 1
    assert repository.value is not None
    assert repository.value.watermark == now


@pytest.mark.asyncio
async def test_personal_message_attachment_enters_existing_download_pipeline() -> None:
    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    repository = CheckpointRepository()
    attached_message = raw_message("om-file", 1786176000000)
    attached_message["msg_type"] = "file"
    attached_message["body"] = {
        "content": '{"file_key":"file-user","file_name":"test.txt"}'
    }
    attachment_sync = AttachmentSync()
    service = PersonalMessageSyncService(
        lambda: UnitOfWork(repository),
        user_client=UserClient(
            [UserMessagePage(items=(attached_message,), next_page_token=None)]
        ),
        ingestion_adapter=UserMessageIngestionAdapter(CapturingHandler()),
        attachment_sync=attachment_sync,
        clock=lambda: now,
    )

    await service.sync_scope(scope=allowed_scope(), tenant_key="tenant-personal")

    assert attachment_sync.message_ids == [
        UUID("00000000-0000-0000-0000-000000000206")
    ]


@pytest.mark.asyncio
async def test_checkpoint_does_not_advance_when_one_message_fails() -> None:
    old_watermark = datetime(2026, 8, 8, 7, 0, tzinfo=UTC)
    repository = CheckpointRepository()
    repository.value = FeishuSyncCheckpoint(
        id=UUID("00000000-0000-0000-0000-000000000204"),
        authorization_id=AUTHORIZATION_ID,
        scope_id=SCOPE_ID,
        watermark=old_watermark,
    )
    client = UserClient(
        [UserMessagePage(items=(raw_message("om-fail", 1786176000000),), next_page_token=None)]
    )
    service = PersonalMessageSyncService(
        lambda: UnitOfWork(repository),
        user_client=client,
        ingestion_adapter=UserMessageIngestionAdapter(
            CapturingHandler(fail_message_id="om-fail")
        ),
        clock=lambda: datetime(2026, 8, 8, 8, 0, tzinfo=UTC),
    )

    with pytest.raises(RuntimeError, match="synthetic ingestion failure"):
        await service.sync_scope(scope=allowed_scope(), tenant_key="tenant-personal")

    assert repository.value is not None
    assert repository.value.watermark == old_watermark
    assert repository.value.consecutive_failures == 1
    assert repository.value.last_error_code == "sync_failed"


@pytest.mark.asyncio
async def test_active_sync_lease_rejects_a_second_owner() -> None:
    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    repository = CheckpointRepository()
    repository.value = FeishuSyncCheckpoint(
        id=UUID("00000000-0000-0000-0000-000000000203"),
        authorization_id=AUTHORIZATION_ID,
        scope_id=SCOPE_ID,
        lease_owner="worker-already-running",
        lease_expires_at=now + timedelta(minutes=1),
        lease_fence=7,
    )
    service = PersonalMessageSyncService(
        lambda: UnitOfWork(repository),
        user_client=UserClient([], checkpoint_repository=repository),
        ingestion_adapter=UserMessageIngestionAdapter(CapturingHandler()),
        clock=lambda: now,
    )

    with pytest.raises(DomainValidationError, match="sync_lease_active"):
        await service.sync_scope(scope=allowed_scope(), tenant_key="tenant-personal")

    assert repository.value.lease_owner == "worker-already-running"
    assert repository.value.lease_fence == 7


@pytest.mark.asyncio
async def test_checkpoint_fencing_prevents_stale_owner_from_advancing() -> None:
    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    repository = CheckpointRepository()

    class LeaseStealingClient(UserClient):
        async def list_messages(self, **kwargs: object) -> UserMessagePage:
            page = await super().list_messages(**kwargs)
            assert repository.value is not None
            repository.value.lease_owner = "replacement-owner"
            repository.value.lease_fence += 1
            repository.value.lease_expires_at = now + timedelta(minutes=5)
            return page

    service = PersonalMessageSyncService(
        lambda: UnitOfWork(repository),
        user_client=LeaseStealingClient(
            [UserMessagePage(items=(), next_page_token=None)],
            checkpoint_repository=repository,
        ),
        ingestion_adapter=UserMessageIngestionAdapter(CapturingHandler()),
        clock=lambda: now,
    )

    with pytest.raises(DomainValidationError, match="sync_lease_lost"):
        await service.sync_scope(scope=allowed_scope(), tenant_key="tenant-personal")

    assert repository.value is not None
    assert repository.value.watermark is None
    assert repository.value.lease_owner == "replacement-owner"


def test_scope_and_checkpoint_schema_support_personal_identity() -> None:
    scope = Base.metadata.tables["integration_scopes"]
    checkpoint = Base.metadata.tables["feishu_sync_checkpoints"]

    assert {"identity_type", "scope_type", "authorization_id", "backfill_days"} <= set(
        scope.c.keys()
    )
    assert {"authorization_id", "scope_id", "watermark", "consecutive_failures"} <= set(
        checkpoint.c.keys()
    )


def test_personal_sync_migration_identifiers_fit_postgresql_limit() -> None:
    migrations = Path(__file__).parents[1] / "migrations" / "versions"
    identifiers: list[str] = []
    for path in sorted(migrations.glob("20260808_001*.py")):
        identifiers.extend(
            re.findall(r'"((?:fk|uq|ix|ck)_[a-z0-9_]+)"', path.read_text())
        )

    assert identifiers
    assert {value for value in identifiers if len(value) > 63} == set()


@pytest.mark.asyncio
async def test_user_client_retries_429_without_exposing_bearer_token() -> None:
    attempts = 0
    sleeps: list[float] = []

    class TokenProvider:
        async def get_access_token(self, authorization_id: UUID) -> str:
            assert authorization_id == AUTHORIZATION_ID
            return "sensitive-user-access-token"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        assert request.headers["authorization"] == "Bearer sensitive-user-access-token"
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "2"},
                json={"code": 99991400, "msg": "rate limited"},
            )
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [raw_message("om-http", 1786176000000)],
                    "has_more": False,
                },
            },
        )

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = FeishuUserClient(
            token_provider=TokenProvider(),
            http_client=http_client,
            base_url="https://open.feishu.test/open-apis",
            sleep=sleep,
        )
        page = await client.list_messages(
            authorization_id=AUTHORIZATION_ID,
            chat_id="oc_group",
            start_time=datetime(2026, 8, 8, 7, 0, tzinfo=UTC),
            end_time=datetime(2026, 8, 8, 8, 0, tzinfo=UTC),
            page_token=None,
        )

    assert [item["message_id"] for item in page.items] == ["om-http"]
    assert sleeps == [2.0]
    assert "sensitive-user-access-token" not in json.dumps(page.items)


@pytest.mark.asyncio
async def test_user_client_refreshes_once_after_401() -> None:
    force_refreshes: list[bool] = []

    class TokenProvider:
        async def get_access_token(
            self, authorization_id: UUID, *, force_refresh: bool = False
        ) -> str:
            assert authorization_id == AUTHORIZATION_ID
            force_refreshes.append(force_refresh)
            return "fresh-token" if force_refresh else "stale-token"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["authorization"] == "Bearer stale-token":
            return httpx.Response(401, json={"code": 99991663, "msg": "expired"})
        return httpx.Response(200, json={"code": 0, "data": {"items": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        page = await FeishuUserClient(
            token_provider=TokenProvider(),
            http_client=http_client,
            base_url="https://open.feishu.test/open-apis",
        ).list_messages(
            authorization_id=AUTHORIZATION_ID,
            chat_id="oc_group",
            start_time=datetime(2026, 8, 8, 7, 0, tzinfo=UTC),
            end_time=datetime(2026, 8, 8, 8, 0, tzinfo=UTC),
            page_token=None,
        )

    assert page.items == ()
    assert force_refreshes == [False, True]


@pytest.mark.asyncio
async def test_user_client_attempts_official_message_resource_with_user_token() -> None:
    class TokenProvider:
        async def get_access_token(
            self, authorization_id: UUID, *, force_refresh: bool = False
        ) -> str:
            assert authorization_id == AUTHORIZATION_ID
            assert force_refresh is False
            return "sensitive-user-access-token"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(
            "/im/v1/messages/om-file/resources/file-user"
        )
        assert request.url.params["type"] == "file"
        assert request.headers["authorization"] == "Bearer sensitive-user-access-token"
        return httpx.Response(
            200,
            headers={"Content-Type": "text/plain"},
            content=b"safe test attachment",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        content, mime_type, size = await FeishuUserClient(
            token_provider=TokenProvider(),
            http_client=http_client,
            base_url="https://open.feishu.test/open-apis",
        ).download_message_resource(
            authorization_id=AUTHORIZATION_ID,
            message_id="om-file",
            file_key="file-user",
            resource_type="file",
        )

    assert content == b"safe test attachment"
    assert mime_type == "text/plain"
    assert size == 20


@pytest.mark.asyncio
async def test_thread_replies_are_pulled_and_enter_unified_ingestion_once() -> None:
    class ThreadUserClient(UserClient):
        def __init__(self) -> None:
            root = raw_message("om-root", 1786176000000)
            root["thread_id"] = "omt-legal"
            super().__init__([UserMessagePage(items=(root,), next_page_token=None)])
            reply = raw_message("om-reply", 1786176060000)
            reply["thread_id"] = "omt-legal"
            reply["root_id"] = "om-root"
            reply["parent_id"] = "om-root"
            self.thread_calls: list[dict[str, object]] = []
            self.thread_pages = [
                UserMessagePage(items=(root, reply), next_page_token=None)
            ]

        async def list_thread_messages(self, **kwargs: object) -> UserMessagePage:
            self.thread_calls.append(kwargs)
            return self.thread_pages[len(self.thread_calls) - 1]

    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    client = ThreadUserClient()
    handler = CapturingHandler()
    repository = CheckpointRepository()
    service = PersonalMessageSyncService(
        lambda: UnitOfWork(repository),
        user_client=client,
        ingestion_adapter=UserMessageIngestionAdapter(handler),
        clock=lambda: now,
    )

    await service.sync_scope(scope=allowed_scope(), tenant_key="tenant-personal")

    assert client.thread_calls == [
        {
            "authorization_id": AUTHORIZATION_ID,
            "thread_id": "omt-legal",
            "page_token": None,
        }
    ]
    message_ids = [
        command.raw_payload["event"]["message"]["message_id"]  # type: ignore[index]
        for command in handler.commands
    ]
    assert message_ids == ["om-root", "om-reply"]


@pytest.mark.asyncio
async def test_user_client_lists_thread_container_messages() -> None:
    class TokenProvider:
        async def get_access_token(
            self, authorization_id: UUID, *, force_refresh: bool = False
        ) -> str:
            assert authorization_id == AUTHORIZATION_ID
            assert force_refresh is False
            return "sensitive-user-access-token"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/im/v1/messages")
        assert request.url.params["container_id_type"] == "thread"
        assert request.url.params["container_id"] == "omt-legal"
        assert "start_time" not in request.url.params
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"items": [raw_message("om-reply", 1786176060000)]},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        page = await FeishuUserClient(
            token_provider=TokenProvider(),
            http_client=http_client,
            base_url="https://open.feishu.test/open-apis",
        ).list_thread_messages(
            authorization_id=AUTHORIZATION_ID,
            thread_id="omt-legal",
            page_token=None,
        )

    assert page.items[0]["message_id"] == "om-reply"
