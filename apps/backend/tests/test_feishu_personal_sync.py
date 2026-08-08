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
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None

    async def commit(self) -> None:
        return None


class UserClient:
    def __init__(self, pages: list[UserMessagePage]) -> None:
        self.pages = pages
        self.calls: list[dict[str, object]] = []

    async def list_messages(self, **kwargs: object) -> UserMessagePage:
        self.calls.append(kwargs)
        return self.pages[len(self.calls) - 1]


class DocumentLinkSync:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def sync_document(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return object()


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
    assert command.event_id == "uat:tenant-personal:om-user-1:1786150000000"
    assert command.raw_payload["source"] == "user_history_sync"
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
        ]
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
