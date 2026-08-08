from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID

import pytest

from legal_workbench.application.feishu_personal_sync import PersonalSyncResult
from legal_workbench.config import Settings
from legal_workbench.domain.entities import FeishuUserAuthorization, IntegrationScope
from legal_workbench.domain.enums import (
    FeishuUserAuthorizationStatus,
    IntegrationIdentityType,
    IntegrationScopeStatus,
    IntegrationScopeType,
    IntegrationSyncMode,
)
from legal_workbench.infrastructure.feishu_personal_runtime import (
    PersonalSyncRuntime,
    PersonalSyncRuntimeFactory,
)
from legal_workbench.infrastructure.secrets import LocalSecretProvider

AUTHORIZATION_ID = UUID("00000000-0000-0000-0000-000000000701")
SCOPE_ID = UUID("00000000-0000-0000-0000-000000000702")


def _scope() -> IntegrationScope:
    return IntegrationScope(
        id=SCOPE_ID,
        provider="feishu",
        external_scope_id="oc-runtime",
        display_name="Runtime parity",
        status=IntegrationScopeStatus.ALLOWED,
        sync_mode=IntegrationSyncMode.ALL_MESSAGES,
        identity_type=IntegrationIdentityType.USER,
        scope_type=IntegrationScopeType.GROUP,
        authorization_id=AUTHORIZATION_ID,
    )


def _authorization() -> FeishuUserAuthorization:
    now = datetime(2026, 8, 8, tzinfo=UTC)
    return FeishuUserAuthorization(
        id=AUTHORIZATION_ID,
        open_id="ou-runtime",
        union_id=None,
        tenant_key="tenant-runtime",
        display_name="Runtime User",
        scopes=(
            "offline_access",
            "contact:user.base:readonly",
            "im:message:readonly",
            "im:message:get_as_user",
            "im:message.p2p_msg:get_as_user",
            "im:message.group_msg:get_as_user",
        ),
        access_token_ref="runtime_access_ref",
        refresh_token_ref="runtime_refresh_ref",
        access_expires_at=now,
        refresh_expires_at=now,
        token_version=1,
        status=FeishuUserAuthorizationStatus.CONNECTED,
    )


class _SetupRepository:
    async def get_scope(self, scope_id: UUID) -> IntegrationScope | None:
        return _scope() if scope_id == SCOPE_ID else None

    async def list_scopes(self, *, provider: str) -> tuple[IntegrationScope, ...]:
        assert provider == "feishu"
        return (_scope(),)


class _AuthorizationRepository:
    async def get_authorization(
        self, authorization_id: UUID
    ) -> FeishuUserAuthorization | None:
        return _authorization() if authorization_id == AUTHORIZATION_ID else None

    async def list_authorizations(self) -> tuple[FeishuUserAuthorization, ...]:
        return (_authorization(),)


class _DocumentRepository:
    async def list_feishu_document_subscriptions(
        self, *, active_only: bool
    ) -> tuple[object, ...]:
        assert active_only is True
        return ()


class _UnitOfWork:
    def __init__(self) -> None:
        self.setup = _SetupRepository()
        self.feishu_user_authorizations = _AuthorizationRepository()
        self.documents = _DocumentRepository()

    async def __aenter__(self) -> _UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class _CredentialSetupRepository:
    def __init__(self, *, secret_ref: str) -> None:
        self.secret_ref = secret_ref

    async def get_setting(self, key: str) -> object:
        assert key == "feishu.app_id"
        return type("Setting", (), {"value": "workbench-app-id"})()

    async def get_credential(self, *, provider: str, credential_kind: str) -> object:
        assert provider == "feishu"
        assert credential_kind == "app_secret"
        return type("Credential", (), {"secret_ref": self.secret_ref})()


class _CredentialUnitOfWork:
    def __init__(self, *, secret_ref: str) -> None:
        self.setup = _CredentialSetupRepository(secret_ref=secret_ref)

    async def __aenter__(self) -> _CredentialUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class _MessageSync:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, str, str]] = []

    async def sync_scope(
        self,
        *,
        scope: IntegrationScope,
        tenant_key: str,
        authorization_open_id: str,
    ) -> PersonalSyncResult:
        self.calls.append((scope.id, tenant_key, authorization_open_id))
        now = datetime(2026, 8, 8, tzinfo=UTC)
        return PersonalSyncResult(
            scope_id=scope.id,
            ingested_count=1,
            started_at=now,
            completed_at=now,
        )


class _FolderService:
    async def sync_subscription(self, subscription_id: UUID) -> object:
        raise AssertionError(f"Unexpected folder subscription: {subscription_id}")


@pytest.mark.asyncio
async def test_manual_and_scheduled_sync_use_the_same_runtime_scope_path() -> None:
    message_sync = _MessageSync()
    built_for: list[tuple[UUID, tuple[str, ...]]] = []

    def build_message_sync(
        authorization_id: UUID,
        granted_scopes: tuple[str, ...],
    ) -> _MessageSync:
        built_for.append((authorization_id, granted_scopes))
        return message_sync

    runtime = PersonalSyncRuntime(
        uow_factory=_UnitOfWork,
        oauth=object(),
        user_client=object(),
        message_sync_factory=build_message_sync,
        document_sync=object(),
        folder_service=_FolderService(),
    )

    manual = await runtime.sync_scope(SCOPE_ID)
    scheduled = await runtime.sync_all_eligible_scopes()

    assert manual.ingested_count == 1
    assert scheduled == {
        "state": "completed",
        "scopeCount": 1,
        "ingestedCount": 1,
        "failedScopeIds": [],
        "folderSubscriptionCount": 0,
        "synchronizedDocumentCount": 0,
        "failedFolderSubscriptionIds": [],
    }
    assert built_for == [
        (AUTHORIZATION_ID, _authorization().scopes),
        (AUTHORIZATION_ID, _authorization().scopes),
    ]
    assert message_sync.calls == [
        (SCOPE_ID, "tenant-runtime", "ou-runtime"),
        (SCOPE_ID, "tenant-runtime", "ou-runtime"),
    ]


@pytest.mark.asyncio
async def test_host_process_credentials_use_the_workbench_secret_provider(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    secret_provider = LocalSecretProvider(tmp_path / "secrets")
    secret_ref = secret_provider.write("feishu_app_secret", "workbench-secret")
    factory = PersonalSyncRuntimeFactory(
        settings=Settings(
            setup_secret_root=str(tmp_path / "secrets"),
            _env_file=None,
        ),
        uow_factory=lambda: _CredentialUnitOfWork(secret_ref=secret_ref),
    )

    assert await factory.resolve_app_credentials() == (
        "workbench-app-id",
        "workbench-secret",
    )
