from __future__ import annotations

import hashlib
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from legal_workbench.application.feishu_local_sync import (
    LocalFeishuHostSyncService,
)
from legal_workbench.domain.entities import IntegrationScope
from legal_workbench.domain.enums import (
    IntegrationIdentityType,
    IntegrationScopeStatus,
    IntegrationScopeType,
    IntegrationSyncMode,
)
from legal_workbench.domain.errors import DomainValidationError
from legal_workbench.integrations.feishu_local_connector import (
    LocalFeishuRecord,
)

AUTHORIZATION_ID = UUID("00000000-0000-0000-0000-000000000401")
CONFIRMED_ACCOUNT_HASH = hashlib.sha256(b"account-local").hexdigest()


def local_record(*, chat_id: str = "oc-local-p2p") -> LocalFeishuRecord:
    return LocalFeishuRecord(
        account_id="account-local",
        chat_id=chat_id,
        chat_type="p2p",
        message_id="om-local-host-1",
        version="1",
        sender_id="ou-sender",
        message_type="text",
        content={"text": "请审核非敏感测试消息"},
        create_time="1786176000000",
        update_time=None,
        thread_id=None,
        root_id=None,
        parent_id=None,
        database_path_hash="a" * 64,
    )


class Connector:
    def __init__(self, records: tuple[LocalFeishuRecord, ...]) -> None:
        self.records = records

    def discover(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            to_dict=lambda: {
                "readOnly": True,
                "credentialLocationsExcluded": True,
                "readableMessageDatabases": 1 if self.records else 0,
            }
        )

    def read_messages(self) -> tuple[LocalFeishuRecord, ...]:
        return self.records


class AuthorizationRepository:
    async def get_authorization(self, value_id: UUID):  # type: ignore[no-untyped-def]
        assert value_id == AUTHORIZATION_ID
        return SimpleNamespace(
            id=value_id,
            tenant_key="tenant-local",
            open_id="ou-current-user",
        )


class UnitOfWork:
    def __init__(self) -> None:
        self.feishu_user_authorizations = AuthorizationRepository()

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
        return None


class ScopeService:
    def __init__(self, *, allowed: bool = False) -> None:
        self.allowed = allowed
        self.scopes: list[IntegrationScope] = []

    async def register_known_chat(self, **values):  # type: ignore[no-untyped-def]
        scope = IntegrationScope(
            id=UUID("00000000-0000-0000-0000-000000000402"),
            provider="feishu",
            external_scope_id=str(values["chat_id"]),
            display_name=None,
            status=(
                IntegrationScopeStatus.ALLOWED
                if self.allowed
                else IntegrationScopeStatus.UNAPPROVED
            ),
            sync_mode=(
                IntegrationSyncMode.ALL_MESSAGES
                if self.allowed
                else IntegrationSyncMode.DISABLED
            ),
            identity_type=IntegrationIdentityType.USER,
            scope_type=IntegrationScopeType.P2P,
            authorization_id=AUTHORIZATION_ID,
            backfill_days=7,
        )
        self.scopes.append(scope)
        return replace(scope)


class Adapter:
    def __init__(self) -> None:
        self.values: list[dict[str, object]] = []

    async def ingest(self, **values):  # type: ignore[no-untyped-def]
        self.values.append(values)
        return SimpleNamespace(duplicate=False)


@pytest.mark.asyncio
async def test_new_local_p2p_is_unapproved_disabled_and_ingested_store_only() -> None:
    adapter = Adapter()
    scopes = ScopeService()
    result = await LocalFeishuHostSyncService(
        lambda: UnitOfWork(),
        connector=Connector((local_record(),)),
        scope_service=scopes,
        ingestion_adapter=adapter,
    ).sync(
        authorization_id=AUTHORIZATION_ID,
        confirmed_account_hash=CONFIRMED_ACCOUNT_HASH,
    )

    assert result.status == "completed"
    assert result.records_discovered == 1
    assert result.ingested == 1
    assert scopes.scopes[0].status == IntegrationScopeStatus.UNAPPROVED
    assert scopes.scopes[0].sync_mode == IntegrationSyncMode.DISABLED
    assert adapter.values[0]["analysis_disposition"] == "store_only"
    assert "account-local" not in str(result.to_dict())


@pytest.mark.asyncio
async def test_allowed_local_p2p_uses_message_analysis_policy() -> None:
    adapter = Adapter()
    result = await LocalFeishuHostSyncService(
        lambda: UnitOfWork(),
        connector=Connector((local_record(),)),
        scope_service=ScopeService(allowed=True),
        ingestion_adapter=adapter,
    ).sync(
        authorization_id=AUTHORIZATION_ID,
        confirmed_account_hash=CONFIRMED_ACCOUNT_HASH,
    )

    assert result.status == "completed"
    assert adapter.values[0]["analysis_disposition"] == "analyze"


@pytest.mark.asyncio
async def test_no_readable_local_records_has_explicit_supported_status() -> None:
    adapter = Adapter()
    result = await LocalFeishuHostSyncService(
        lambda: UnitOfWork(),
        connector=Connector(()),
        scope_service=ScopeService(),
        ingestion_adapter=adapter,
    ).sync(
        authorization_id=AUTHORIZATION_ID,
        confirmed_account_hash=CONFIRMED_ACCOUNT_HASH,
    )

    assert result.status == "supported_but_no_readable_local_records"
    assert result.records_discovered == 0
    assert result.ingested == 0
    assert adapter.values == []


@pytest.mark.asyncio
async def test_multiple_local_accounts_only_ingest_the_confirmed_binding() -> None:
    adapter = Adapter()
    other = replace(
        local_record(chat_id="oc-other-account"),
        account_id="account-other",
        message_id="om-other-account",
    )
    result = await LocalFeishuHostSyncService(
        lambda: UnitOfWork(),
        connector=Connector((local_record(), other)),
        scope_service=ScopeService(),
        ingestion_adapter=adapter,
    ).sync(
        authorization_id=AUTHORIZATION_ID,
        confirmed_account_hash=CONFIRMED_ACCOUNT_HASH,
    )

    assert result.records_discovered == 1
    assert result.skipped == 1
    assert len(adapter.values) == 1
    assert adapter.values[0]["record"].account_id == "account-local"


@pytest.mark.asyncio
async def test_unknown_local_account_binding_fails_closed() -> None:
    with pytest.raises(DomainValidationError, match="confirmed local account"):
        await LocalFeishuHostSyncService(
            lambda: UnitOfWork(),
            connector=Connector((local_record(),)),
            scope_service=ScopeService(),
            ingestion_adapter=Adapter(),
        ).sync(
            authorization_id=AUTHORIZATION_ID,
            confirmed_account_hash=hashlib.sha256(b"unknown-account").hexdigest(),
        )
