from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import httpx
import pytest

from legal_workbench.api.routes.feishu_user import USER_SCOPES, _authorization_response
from legal_workbench.application.feishu_capabilities import (
    CORE_IDENTITY_SCOPES,
    FeishuCapability,
    FeishuCapabilityStatus,
)
from legal_workbench.application.feishu_user_auth import (
    FeishuOAuthService,
    FeishuOAuthTokens,
    FeishuUserTokenProvider,
    OAuthIdentity,
    build_pkce_challenge,
)
from legal_workbench.domain.entities import (
    AuditEvent,
    FeishuOAuthAttempt,
    FeishuUserAuthorization,
    IdempotencyRecord,
)
from legal_workbench.domain.enums import (
    FeishuTokenRotationPhase,
    FeishuUserAuthorizationStatus,
)
from legal_workbench.domain.errors import DomainValidationError
from legal_workbench.infrastructure.database import Base
from legal_workbench.infrastructure.secrets import LocalSecretProvider
from legal_workbench.integrations.feishu_user_oauth import (
    FeishuOAuthHttpClient,
    FeishuUserApiError,
)


class FakeAuthorizationRepository:
    def __init__(self) -> None:
        self.attempts: dict[str, FeishuOAuthAttempt] = {}
        self.authorizations: dict[UUID, FeishuUserAuthorization] = {}
        self.lock = asyncio.Lock()
        self.audit_values: list[AuditEvent] = []
        self.idempotency_values: dict[tuple[str, str], IdempotencyRecord] = {}

    async def add_oauth_attempt(self, value: FeishuOAuthAttempt) -> None:
        self.attempts[value.state_hash] = value

    async def get_oauth_attempt_for_update(
        self, state_hash: str
    ) -> FeishuOAuthAttempt | None:
        return self.attempts.get(state_hash)

    async def save_oauth_attempt(self, value: FeishuOAuthAttempt) -> None:
        self.attempts[value.state_hash] = value

    async def add_authorization(self, value: FeishuUserAuthorization) -> None:
        self.authorizations[value.id] = value

    async def get_authorization(self, value_id: UUID) -> FeishuUserAuthorization | None:
        return self.authorizations.get(value_id)

    async def get_authorization_for_update(
        self, value_id: UUID
    ) -> FeishuUserAuthorization | None:
        return self.authorizations.get(value_id)

    async def save_authorization(self, value: FeishuUserAuthorization) -> None:
        self.authorizations[value.id] = value

    async def list_authorizations(self) -> Sequence[FeishuUserAuthorization]:
        return list(self.authorizations.values())


class FakeUnitOfWork:
    def __init__(self, repository: FakeAuthorizationRepository) -> None:
        self.feishu_user_authorizations = repository
        self._lock = repository.lock
        self.audit_events = self
        self.idempotency = self
        self._repository = repository

    async def __aenter__(self) -> FakeUnitOfWork:
        await self._lock.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        self._lock.release()
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        return None

    async def add(self, value: AuditEvent | IdempotencyRecord) -> None:
        if isinstance(value, AuditEvent):
            self._repository.audit_values.append(value)
        else:
            self._repository.idempotency_values[(value.operation, value.idempotency_key)] = value

    async def get(self, *, operation: str, key: str) -> IdempotencyRecord | None:
        return self._repository.idempotency_values.get((operation, key))


class OAuthClient:
    def __init__(self) -> None:
        self.exchange_verifier: str | None = None
        self.refresh_calls = 0

    async def exchange_code(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> FeishuOAuthTokens:
        assert redirect_uri == "http://localhost/callback"
        self.exchange_verifier = code_verifier
        return FeishuOAuthTokens(
            access_token="initial-access-token",
            refresh_token="initial-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=2),
            refresh_expires_at=datetime.now(UTC) + timedelta(days=20),
            scopes=("offline_access", "im:message"),
        )

    async def get_identity(self, *, access_token: str) -> OAuthIdentity:
        assert access_token == "initial-access-token"
        return OAuthIdentity(
            open_id="ou_personal",
            union_id="on_personal",
            tenant_key="tenant-personal",
            display_name="Legal User",
        )

    async def refresh(self, *, refresh_token: str) -> FeishuOAuthTokens:
        assert refresh_token in {"initial-refresh-token", "old-refresh-token"}
        self.refresh_calls += 1
        await asyncio.sleep(0.01)
        return FeishuOAuthTokens(
            access_token="rotated-access-token",
            refresh_token="rotated-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=2),
            refresh_expires_at=datetime.now(UTC) + timedelta(days=20),
            scopes=("offline_access", "im:message"),
        )


class InjectedRotationCrash(RuntimeError):
    pass


class CrashAt:
    def __init__(self, stage: str) -> None:
        self.stage = stage
        self.triggered = False

    def __call__(self, stage: str) -> None:
        if stage == self.stage and not self.triggered:
            self.triggered = True
            raise InjectedRotationCrash(stage)


def expired_authorization(
    repository: FakeAuthorizationRepository,
    secrets: LocalSecretProvider,
    *,
    value_id: UUID,
) -> tuple[str, str]:
    access_ref = secrets.write(f"feishu_uat_{value_id.hex}_v1", "old-access-token")
    refresh_ref = secrets.write(f"feishu_urt_{value_id.hex}_v1", "old-refresh-token")
    repository.authorizations[value_id] = FeishuUserAuthorization(
        id=value_id,
        open_id="ou_personal",
        union_id="on_personal",
        tenant_key="tenant-personal",
        display_name="Legal User",
        scopes=("offline_access", "im:message"),
        access_token_ref=access_ref,
        refresh_token_ref=refresh_ref,
        access_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=20),
        token_version=1,
        status=FeishuUserAuthorizationStatus.CONNECTED,
    )
    return access_ref, refresh_ref


def test_user_oauth_request_uses_minimum_personal_message_sync_scopes(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    service = FeishuOAuthService(
        lambda: FakeUnitOfWork(repository),
        oauth_client=OAuthClient(),
        secret_provider=LocalSecretProvider(tmp_path / "secrets"),
        app_id="cli_test_app",
    )

    result = asyncio.run(
        service.start_authorization(
            redirect_uri="http://localhost/callback",
            requested_by="legal-user",
            scopes=USER_SCOPES,
        )
    )

    granted = set(parse_qs(urlparse(result.authorization_url).query)["scope"][0].split())
    assert granted == {
        "offline_access",
        "contact:user.base:readonly",
        "im:message:readonly",
        "im:message.p2p_msg:get_as_user",
        "im:message.group_msg:get_as_user",
        "im:chat:read",
    }
    assert granted.isdisjoint(
        {
            "im:chat:readonly",
            "drive:drive.search:readonly",
            "drive:drive.metadata:readonly",
            "docs:document.content:read",
        }
    )


def test_pkce_challenge_is_s256_and_authorization_url_contains_no_secret(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    client = OAuthClient()
    service = FeishuOAuthService(
        lambda: FakeUnitOfWork(repository),
        oauth_client=client,
        secret_provider=secrets,
        app_id="cli_test_app",
        authorize_url="https://accounts.feishu.cn/open-apis/authen/v1/authorize",
    )

    result = asyncio.run(
        service.start_authorization(
            redirect_uri="http://localhost:8000/api/integrations/feishu/user/callback",
            requested_by="legal-user",
            scopes=("offline_access", "im:message"),
            idempotency_key="oauth-start-1",
            correlation_id="correlation-oauth-start-1",
        )
    )

    query = parse_qs(urlparse(result.authorization_url).query)
    verifier = secrets.read(result.verifier_reference)
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [build_pkce_challenge(verifier)]
    assert query["scope"] == ["offline_access im:message"]
    assert query["state"] == [result.state]
    assert "secret" not in result.authorization_url.lower()
    attempt = repository.attempts[hashlib.sha256(result.state.encode()).hexdigest()]
    assert attempt.state_hash != result.state
    assert attempt.code_verifier_ref == result.verifier_reference
    idempotency_payload = repository.idempotency_values[
        ("start_feishu_user_authorization", "oauth-start-1")
    ].response_payload
    assert result.state not in json.dumps(idempotency_payload)
    assert result.authorization_url not in json.dumps(idempotency_payload)


@pytest.mark.asyncio
async def test_oauth_callback_persists_only_versioned_secret_references(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    client = OAuthClient()
    service = FeishuOAuthService(
        lambda: FakeUnitOfWork(repository),
        oauth_client=client,
        secret_provider=secrets,
        app_id="cli_test_app",
    )
    started = await service.start_authorization(
        redirect_uri="http://localhost/callback",
        requested_by="legal-user",
        scopes=("offline_access", "im:message"),
    )

    authorization = await service.complete_authorization(
        state=started.state,
        code="single-use-code",
    )

    assert authorization.status == FeishuUserAuthorizationStatus.CONNECTED
    assert authorization.open_id == "ou_personal"
    assert secrets.read(authorization.access_token_ref) == "initial-access-token"
    assert secrets.read(authorization.refresh_token_ref) == "initial-refresh-token"
    assert client.exchange_verifier is not None
    assert not secrets.exists(started.verifier_reference)
    serialized = repr(authorization)
    assert "initial-access-token" not in serialized
    assert "initial-refresh-token" not in serialized


@pytest.mark.asyncio
async def test_oauth_callback_does_not_hold_database_transaction_during_http(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()

    class TransactionBoundaryOAuthClient(OAuthClient):
        async def exchange_code(
            self, *, code: str, code_verifier: str, redirect_uri: str
        ) -> FeishuOAuthTokens:
            assert not repository.lock.locked()
            return await super().exchange_code(
                code=code,
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
            )

        async def get_identity(self, *, access_token: str) -> OAuthIdentity:
            assert not repository.lock.locked()
            return await super().get_identity(access_token=access_token)

    service = FeishuOAuthService(
        lambda: FakeUnitOfWork(repository),
        oauth_client=TransactionBoundaryOAuthClient(),
        secret_provider=LocalSecretProvider(tmp_path / "secrets"),
        app_id="cli_test_app",
    )
    started = await service.start_authorization(
        redirect_uri="http://localhost/callback",
        requested_by="legal-user",
        scopes=("offline_access", "im:message"),
    )

    authorization = await service.complete_authorization(
        state=started.state,
        code="single-use-code",
    )

    assert authorization.status == FeishuUserAuthorizationStatus.CONNECTED


@pytest.mark.asyncio
async def test_oauth_callback_marks_missing_granted_scope_without_storing_token_body(
    tmp_path: Path,
) -> None:
    required_scopes = (
        "offline_access",
        "im:message:readonly",
        "im:message.p2p_msg:get_as_user",
        "im:message.group_msg:get_as_user",
    )

    class PartiallyGrantedOAuthClient(OAuthClient):
        async def exchange_code(
            self, *, code: str, code_verifier: str, redirect_uri: str
        ) -> FeishuOAuthTokens:
            del code
            assert redirect_uri == "http://localhost/callback"
            self.exchange_verifier = code_verifier
            return FeishuOAuthTokens(
                access_token="partial-access-token",
                refresh_token="partial-refresh-token",
                access_expires_at=datetime.now(UTC) + timedelta(hours=2),
                refresh_expires_at=datetime.now(UTC) + timedelta(days=20),
                scopes=required_scopes[:-1],
            )

        async def get_identity(self, *, access_token: str) -> OAuthIdentity:
            assert access_token == "partial-access-token"
            return OAuthIdentity(
                open_id="ou_partial",
                union_id=None,
                tenant_key="tenant-personal",
                display_name="Legal User",
            )

    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    service = FeishuOAuthService(
        lambda: FakeUnitOfWork(repository),
        oauth_client=PartiallyGrantedOAuthClient(),
        secret_provider=secrets,
        app_id="cli_test_app",
        required_scopes=required_scopes,
    )
    started = await service.start_authorization(
        redirect_uri="http://localhost/callback",
        requested_by="legal-user",
        scopes=required_scopes,
    )

    authorization = await service.complete_authorization(
        state=started.state,
        code="single-use-code",
    )

    assert authorization.scopes == required_scopes[:-1]
    assert authorization.status == FeishuUserAuthorizationStatus.PERMISSION_MISSING
    assert authorization.last_error_code == "permission_missing"
    persisted = json.dumps(
        [event.payload for event in repository.audit_values], ensure_ascii=False
    )
    assert "partial-access-token" not in persisted
    assert "partial-refresh-token" not in persisted


def test_authorization_api_projects_optional_capability_gaps_without_disabling_token(
    tmp_path: Path,
) -> None:
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000110")
    authorization = FeishuUserAuthorization(
        id=value_id,
        open_id="ou_capabilities",
        union_id=None,
        tenant_key="tenant-personal",
        display_name="Legal User",
        scopes=(*CORE_IDENTITY_SCOPES, "im:message:readonly"),
        access_token_ref=secrets.write("api_access_ref", "api-access-token"),
        refresh_token_ref=secrets.write("api_refresh_ref", "api-refresh-token"),
        access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
        token_version=1,
        status=FeishuUserAuthorizationStatus.PERMISSION_MISSING,
        last_error_code="permission_missing",
    )

    response = _authorization_response(authorization)
    capabilities = {item.capability: item for item in response.capabilities}

    assert response.usable is True
    assert response.status == FeishuUserAuthorizationStatus.CONNECTED
    assert response.missing_scopes == ()
    assert capabilities[FeishuCapability.MESSAGE_HISTORY].status == FeishuCapabilityStatus.PARTIAL
    assert (
        capabilities[FeishuCapability.DOCUMENT_READ].status
        == FeishuCapabilityStatus.PERMISSION_MISSING
    )
    assert (
        capabilities[FeishuCapability.DRIVE_SEARCH].status
        == FeishuCapabilityStatus.PERMISSION_MISSING
    )


@pytest.mark.asyncio
async def test_optional_scope_gap_does_not_make_existing_token_unusable(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000111")
    access_ref = secrets.write(f"feishu_uat_{value_id.hex}_v1", "usable-access")
    refresh_ref = secrets.write(f"feishu_urt_{value_id.hex}_v1", "usable-refresh")
    repository.authorizations[value_id] = FeishuUserAuthorization(
        id=value_id,
        open_id="ou_legacy_permission_status",
        union_id=None,
        tenant_key="tenant-personal",
        display_name=None,
        scopes=CORE_IDENTITY_SCOPES,
        access_token_ref=access_ref,
        refresh_token_ref=refresh_ref,
        access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
        token_version=1,
        status=FeishuUserAuthorizationStatus.PERMISSION_MISSING,
        last_error_code="permission_missing",
    )
    client = OAuthClient()

    token = await FeishuUserTokenProvider(
        lambda: FakeUnitOfWork(repository),
        oauth_client=client,
        secret_provider=secrets,
        required_scopes=CORE_IDENTITY_SCOPES,
    ).get_access_token(value_id)

    assert token == "usable-access"
    assert repository.authorizations[value_id].status == FeishuUserAuthorizationStatus.CONNECTED
    assert repository.authorizations[value_id].last_error_code is None
    assert client.refresh_calls == 0


@pytest.mark.asyncio
async def test_concurrent_refresh_rotates_pair_once_and_removes_old_secrets(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000101")
    old_access_ref = secrets.write(f"feishu_uat_{value_id.hex}_v1", "old-access-token")
    old_refresh_ref = secrets.write(f"feishu_urt_{value_id.hex}_v1", "old-refresh-token")
    repository.authorizations[value_id] = FeishuUserAuthorization(
        id=value_id,
        open_id="ou_personal",
        union_id="on_personal",
        tenant_key="tenant-personal",
        display_name="Legal User",
        scopes=("offline_access", "im:message"),
        access_token_ref=old_access_ref,
        refresh_token_ref=old_refresh_ref,
        access_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=20),
        token_version=1,
        status=FeishuUserAuthorizationStatus.CONNECTED,
    )
    client = OAuthClient()
    provider = FeishuUserTokenProvider(
        lambda: FakeUnitOfWork(repository),
        oauth_client=client,
        secret_provider=secrets,
    )

    tokens = await asyncio.gather(
        provider.get_access_token(value_id),
        provider.get_access_token(value_id),
    )

    assert tokens == ["rotated-access-token", "rotated-access-token"]
    assert client.refresh_calls == 1
    saved = repository.authorizations[value_id]
    assert saved.token_version == 2
    assert secrets.read(saved.access_token_ref) == "rotated-access-token"
    assert secrets.read(saved.refresh_token_ref) == "rotated-refresh-token"
    assert not secrets.exists(old_access_ref)
    assert not secrets.exists(old_refresh_ref)


@pytest.mark.asyncio
async def test_refresh_crash_before_request_started_can_retry_old_refresh_token(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000201")
    expired_authorization(repository, secrets, value_id=value_id)
    client = OAuthClient()

    with pytest.raises(InjectedRotationCrash, match="before_request_started"):
        await FeishuUserTokenProvider(
            lambda: FakeUnitOfWork(repository),
            oauth_client=client,
            secret_provider=secrets,
            fault_injector=CrashAt("before_request_started"),
        ).get_access_token(value_id)

    saved = repository.authorizations[value_id]
    assert saved.rotation_phase == FeishuTokenRotationPhase.CLAIMED
    assert saved.rotation_request_started_at is None
    assert client.refresh_calls == 0
    saved.rotation_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    token = await FeishuUserTokenProvider(
        lambda: FakeUnitOfWork(repository),
        oauth_client=client,
        secret_provider=secrets,
    ).get_access_token(value_id)

    assert token == "rotated-access-token"
    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_refresh_crash_after_request_started_fails_closed(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000202")
    expired_authorization(repository, secrets, value_id=value_id)
    client = OAuthClient()

    with pytest.raises(InjectedRotationCrash, match="after_request_started"):
        await FeishuUserTokenProvider(
            lambda: FakeUnitOfWork(repository),
            oauth_client=client,
            secret_provider=secrets,
            fault_injector=CrashAt("after_request_started"),
        ).get_access_token(value_id)

    saved = repository.authorizations[value_id]
    assert saved.status == FeishuUserAuthorizationStatus.REAUTH_REQUIRED
    assert saved.rotation_phase == FeishuTokenRotationPhase.REQUEST_STARTED
    assert saved.rotation_request_started_at is not None
    assert saved.rotation_reauth_reason == "refresh_outcome_uncertain"
    assert client.refresh_calls == 0


@pytest.mark.asyncio
async def test_refresh_crash_after_http_success_before_bundle_fails_closed(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000203")
    expired_authorization(repository, secrets, value_id=value_id)
    client = OAuthClient()

    with pytest.raises(InjectedRotationCrash, match="after_http_success_before_bundle"):
        await FeishuUserTokenProvider(
            lambda: FakeUnitOfWork(repository),
            oauth_client=client,
            secret_provider=secrets,
            fault_injector=CrashAt("after_http_success_before_bundle"),
        ).get_access_token(value_id)

    saved = repository.authorizations[value_id]
    assert saved.status == FeishuUserAuthorizationStatus.REAUTH_REQUIRED
    assert saved.rotation_reauth_reason == "refresh_outcome_uncertain"
    assert client.refresh_calls == 1
    assert not secrets.exists(f"feishu_rotation_{value_id.hex}_v2")


@pytest.mark.asyncio
async def test_refresh_crash_after_bundle_fsync_recovers_without_second_http(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000204")
    expired_authorization(repository, secrets, value_id=value_id)
    client = OAuthClient()

    with pytest.raises(InjectedRotationCrash, match="after_bundle_fsync"):
        await FeishuUserTokenProvider(
            lambda: FakeUnitOfWork(repository),
            oauth_client=client,
            secret_provider=secrets,
            fault_injector=CrashAt("after_bundle_fsync"),
        ).get_access_token(value_id)

    assert secrets.exists(f"feishu_rotation_{value_id.hex}_v2")
    token = await FeishuUserTokenProvider(
        lambda: FakeUnitOfWork(repository),
        oauth_client=client,
        secret_provider=secrets,
    ).get_access_token(value_id)

    assert token == "rotated-access-token"
    assert client.refresh_calls == 1
    assert repository.authorizations[value_id].token_version == 2


@pytest.mark.asyncio
async def test_refresh_crash_before_activation_commit_recovers_durable_result(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000205")
    expired_authorization(repository, secrets, value_id=value_id)
    client = OAuthClient()

    with pytest.raises(InjectedRotationCrash, match="before_activation_commit"):
        await FeishuUserTokenProvider(
            lambda: FakeUnitOfWork(repository),
            oauth_client=client,
            secret_provider=secrets,
            fault_injector=CrashAt("before_activation_commit"),
        ).get_access_token(value_id)

    saved = repository.authorizations[value_id]
    assert saved.rotation_phase == FeishuTokenRotationPhase.RESULT_DURABLE
    assert saved.rotation_result_written_at is not None
    assert saved.token_version == 1

    token = await FeishuUserTokenProvider(
        lambda: FakeUnitOfWork(repository),
        oauth_client=client,
        secret_provider=secrets,
    ).get_access_token(value_id)
    assert token == "rotated-access-token"
    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_refresh_crash_after_activation_commit_keeps_new_generation_active(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000206")
    expired_authorization(repository, secrets, value_id=value_id)
    client = OAuthClient()

    with pytest.raises(InjectedRotationCrash, match="after_activation_commit"):
        await FeishuUserTokenProvider(
            lambda: FakeUnitOfWork(repository),
            oauth_client=client,
            secret_provider=secrets,
            fault_injector=CrashAt("after_activation_commit"),
        ).get_access_token(value_id)

    saved = repository.authorizations[value_id]
    assert saved.token_version == 2
    assert saved.status == FeishuUserAuthorizationStatus.CONNECTED
    assert saved.rotation_phase == FeishuTokenRotationPhase.ACTIVATED
    assert await FeishuUserTokenProvider(
        lambda: FakeUnitOfWork(repository),
        oauth_client=client,
        secret_provider=secrets,
    ).get_access_token(value_id) == "rotated-access-token"
    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_refresh_crash_during_orphan_cleanup_is_recoverable(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000207")
    old_access_ref, old_refresh_ref = expired_authorization(
        repository, secrets, value_id=value_id
    )
    client = OAuthClient()

    with pytest.raises(InjectedRotationCrash, match="during_orphan_cleanup"):
        await FeishuUserTokenProvider(
            lambda: FakeUnitOfWork(repository),
            oauth_client=client,
            secret_provider=secrets,
            fault_injector=CrashAt("during_orphan_cleanup"),
        ).get_access_token(value_id)

    assert repository.authorizations[value_id].token_version == 2
    assert secrets.exists(old_access_ref)
    assert secrets.exists(old_refresh_ref)

    assert await FeishuUserTokenProvider(
        lambda: FakeUnitOfWork(repository),
        oauth_client=client,
        secret_provider=secrets,
    ).get_access_token(value_id) == "rotated-access-token"
    assert not secrets.exists(old_access_ref)
    assert not secrets.exists(old_refresh_ref)


@pytest.mark.asyncio
async def test_stale_rotation_owner_cannot_activate_durable_generation(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000208")
    expired_authorization(repository, secrets, value_id=value_id)
    client = OAuthClient()

    def steal_fence(stage: str) -> None:
        if stage == "before_activation_commit":
            saved = repository.authorizations[value_id]
            saved.rotation_owner = "replacement-owner"
            saved.rotation_fence += 1

    with pytest.raises(DomainValidationError, match="fenced"):
        await FeishuUserTokenProvider(
            lambda: FakeUnitOfWork(repository),
            oauth_client=client,
            secret_provider=secrets,
            fault_injector=steal_fence,
        ).get_access_token(value_id)

    saved = repository.authorizations[value_id]
    assert saved.token_version == 1
    assert secrets.exists(f"feishu_rotation_{value_id.hex}_v2")
    assert await FeishuUserTokenProvider(
        lambda: FakeUnitOfWork(repository),
        oauth_client=client,
        secret_provider=secrets,
    ).get_access_token(value_id) == "rotated-access-token"
    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_pending_token_generation_recovers_after_crash_without_reusing_refresh(
    tmp_path: Path,
) -> None:
    class RefreshMustNotRun(OAuthClient):
        async def refresh(self, *, refresh_token: str) -> FeishuOAuthTokens:
            raise AssertionError(f"Refresh token was reused: {refresh_token}")

    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000105")
    old_access_ref = secrets.write(
        f"feishu_uat_{value_id.hex}_v1", "old-access-token"
    )
    old_refresh_ref = secrets.write(
        f"feishu_urt_{value_id.hex}_v1", "old-refresh-token"
    )
    bundle_ref = f"feishu_rotation_{value_id.hex}_v2"
    access_expires_at = datetime.now(UTC) + timedelta(hours=2)
    refresh_expires_at = datetime.now(UTC) + timedelta(days=20)
    secrets.write_token_generation(
        bundle_ref,
        access_token="crash-recovered-access-token",
        refresh_token="crash-recovered-refresh-token",
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
        scopes=("offline_access", "im:message"),
    )
    repository.authorizations[value_id] = FeishuUserAuthorization(
        id=value_id,
        open_id="ou_personal",
        union_id="on_personal",
        tenant_key="tenant-personal",
        display_name="Legal User",
        scopes=("offline_access", "im:message"),
        access_token_ref=old_access_ref,
        refresh_token_ref=old_refresh_ref,
        access_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=20),
        token_version=1,
        status=FeishuUserAuthorizationStatus.CONNECTED,
        pending_token_version=2,
        pending_token_bundle_ref=bundle_ref,
        rotation_owner="crashed-worker",
        rotation_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    token = await FeishuUserTokenProvider(
        lambda: FakeUnitOfWork(repository),
        oauth_client=RefreshMustNotRun(),
        secret_provider=secrets,
    ).get_access_token(value_id)

    saved = repository.authorizations[value_id]
    assert token == "crash-recovered-access-token"
    assert saved.token_version == 2
    assert saved.pending_token_version is None
    assert saved.pending_token_bundle_ref is None
    assert saved.rotation_owner is None
    assert saved.rotation_expires_at is None
    assert secrets.read(saved.refresh_token_ref) == "crash-recovered-refresh-token"
    assert not secrets.exists(bundle_ref)
    assert not secrets.exists(old_access_ref)
    assert not secrets.exists(old_refresh_ref)


@pytest.mark.asyncio
async def test_activated_generation_cleans_orphan_bundle_after_commit_crash(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000106")
    access_ref = secrets.write(
        f"feishu_uat_{value_id.hex}_v2", "active-access-token"
    )
    refresh_ref = secrets.write(
        f"feishu_urt_{value_id.hex}_v2", "active-refresh-token"
    )
    orphan_bundle = secrets.write_token_generation(
        f"feishu_rotation_{value_id.hex}_v2",
        access_token="active-access-token",
        refresh_token="active-refresh-token",
        access_expires_at=datetime.now(UTC) + timedelta(hours=2),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=20),
        scopes=("offline_access", "im:message"),
    )
    repository.authorizations[value_id] = FeishuUserAuthorization(
        id=value_id,
        open_id="ou_personal",
        union_id="on_personal",
        tenant_key="tenant-personal",
        display_name="Legal User",
        scopes=("offline_access", "im:message"),
        access_token_ref=access_ref,
        refresh_token_ref=refresh_ref,
        access_expires_at=datetime.now(UTC) + timedelta(hours=2),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=20),
        token_version=2,
        status=FeishuUserAuthorizationStatus.CONNECTED,
    )

    token = await FeishuUserTokenProvider(
        lambda: FakeUnitOfWork(repository),
        oauth_client=OAuthClient(),
        secret_provider=secrets,
    ).get_access_token(value_id)

    assert token == "active-access-token"
    assert not secrets.exists(orphan_bundle)


def test_token_generation_bundle_and_database_metadata_do_not_expose_token_body(
    tmp_path: Path,
) -> None:
    secrets = LocalSecretProvider(tmp_path / "secrets")
    bundle = secrets.write_token_generation(
        "feishu_rotation_test_v2",
        access_token="sensitive-access-token",
        refresh_token="sensitive-refresh-token",
        access_expires_at=datetime.now(UTC) + timedelta(hours=2),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=20),
        scopes=("offline_access",),
    )
    recovered = secrets.read_token_generation(bundle)

    assert "sensitive-access-token" not in repr(recovered)
    assert "sensitive-refresh-token" not in repr(recovered)
    authorization = Base.metadata.tables["feishu_user_authorizations"]
    assert {
        "pending_token_version",
        "pending_token_bundle_ref",
        "rotation_owner",
        "rotation_expires_at",
        "rotation_phase",
        "rotation_request_started_at",
        "rotation_fence",
        "rotation_result_written_at",
        "rotation_reauth_reason",
    } <= set(authorization.c.keys())
    assert "pending_access_token" not in authorization.c
    assert "pending_refresh_token" not in authorization.c


@pytest.mark.asyncio
async def test_expired_refresh_token_marks_authorization_expired_without_http_call(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000102")
    access_ref = secrets.write(f"feishu_uat_{value_id.hex}_v1", "expired-access")
    refresh_ref = secrets.write(f"feishu_urt_{value_id.hex}_v1", "expired-refresh")
    repository.authorizations[value_id] = FeishuUserAuthorization(
        id=value_id,
        open_id="ou_expired",
        union_id=None,
        tenant_key="tenant-personal",
        display_name=None,
        scopes=("offline_access",),
        access_token_ref=access_ref,
        refresh_token_ref=refresh_ref,
        access_expires_at=datetime.now(UTC) - timedelta(hours=1),
        refresh_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        token_version=1,
        status=FeishuUserAuthorizationStatus.CONNECTED,
    )
    client = OAuthClient()

    with pytest.raises(DomainValidationError, match="renewed"):
        await FeishuUserTokenProvider(
            lambda: FakeUnitOfWork(repository),
            oauth_client=client,
            secret_provider=secrets,
        ).get_access_token(value_id)

    saved = repository.authorizations[value_id]
    assert saved.status == FeishuUserAuthorizationStatus.EXPIRED
    assert saved.last_error_code == "refresh_token_expired"
    assert client.refresh_calls == 0


@pytest.mark.asyncio
async def test_refresh_rejection_marks_reauthorization_required(
    tmp_path: Path,
) -> None:
    class RejectedOAuthClient(OAuthClient):
        async def refresh(self, *, refresh_token: str) -> FeishuOAuthTokens:
            raise FeishuUserApiError(code=20028, http_status=400)

    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000103")
    access_ref = secrets.write(f"feishu_uat_{value_id.hex}_v1", "rejected-access")
    refresh_ref = secrets.write(f"feishu_urt_{value_id.hex}_v1", "rejected-refresh")
    repository.authorizations[value_id] = FeishuUserAuthorization(
        id=value_id,
        open_id="ou_rejected",
        union_id=None,
        tenant_key="tenant-personal",
        display_name=None,
        scopes=("offline_access",),
        access_token_ref=access_ref,
        refresh_token_ref=refresh_ref,
        access_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
        token_version=1,
        status=FeishuUserAuthorizationStatus.CONNECTED,
    )

    with pytest.raises(FeishuUserApiError):
        await FeishuUserTokenProvider(
            lambda: FakeUnitOfWork(repository),
            oauth_client=RejectedOAuthClient(),
            secret_provider=secrets,
        ).get_access_token(value_id)

    saved = repository.authorizations[value_id]
    assert saved.status == FeishuUserAuthorizationStatus.REAUTH_REQUIRED
    assert saved.last_error_code == "refresh_rejected:20028"
    assert secrets.read(saved.refresh_token_ref) == "rejected-refresh"


@pytest.mark.asyncio
async def test_disconnect_revokes_authorization_and_deletes_both_secrets(
    tmp_path: Path,
) -> None:
    repository = FakeAuthorizationRepository()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    value_id = UUID("00000000-0000-0000-0000-000000000104")
    access_ref = secrets.write(f"feishu_uat_{value_id.hex}_v1", "disconnect-access")
    refresh_ref = secrets.write(f"feishu_urt_{value_id.hex}_v1", "disconnect-refresh")
    repository.authorizations[value_id] = FeishuUserAuthorization(
        id=value_id,
        open_id="ou_disconnect",
        union_id=None,
        tenant_key="tenant-personal",
        display_name=None,
        scopes=("offline_access",),
        access_token_ref=access_ref,
        refresh_token_ref=refresh_ref,
        access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
        token_version=1,
        status=FeishuUserAuthorizationStatus.CONNECTED,
    )

    disconnected = await FeishuOAuthService(
        lambda: FakeUnitOfWork(repository),
        oauth_client=OAuthClient(),
        secret_provider=secrets,
        app_id="cli_test_app",
    ).disconnect(value_id)

    assert disconnected.status == FeishuUserAuthorizationStatus.REVOKED
    assert not secrets.exists(access_ref)
    assert not secrets.exists(refresh_ref)


def test_authorization_tables_contain_references_but_no_token_body_columns() -> None:
    authorization = Base.metadata.tables["feishu_user_authorizations"]
    attempt = Base.metadata.tables["feishu_oauth_attempts"]

    assert {"access_token_ref", "refresh_token_ref", "token_version"} <= set(
        authorization.c.keys()
    )
    assert "access_token" not in authorization.c
    assert "refresh_token" not in authorization.c
    assert "code_verifier_ref" in attempt.c
    assert "code_verifier" not in attempt.c


@pytest.mark.asyncio
async def test_oauth_http_client_supports_rotation_and_redacts_error_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "access_token": "http-access-token",
                        "refresh_token": "http-refresh-token",
                        "expires_in": 7200,
                        "refresh_token_expires_in": 2592000,
                        "scope": "offline_access im:message",
                    },
                },
            )
        return httpx.Response(
            400,
            json={"code": 20001, "msg": "bad sensitive-refresh-token"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = FeishuOAuthHttpClient(
            app_id="cli_test_app",
            app_secret="sensitive-app-secret",
            http_client=http_client,
            base_url="https://open.feishu.test",
        )
        tokens = await client.exchange_code(
            code="oauth-code",
            code_verifier="verifier",
            redirect_uri="http://localhost/callback",
        )
        assert tokens.access_token == "http-access-token"
        assert tokens.refresh_token == "http-refresh-token"
        with pytest.raises(FeishuUserApiError) as captured:
            await client.get_identity(access_token="sensitive-refresh-token")

    assert captured.value.code == 20001
    assert "sensitive-refresh-token" not in str(captured.value)
    assert "sensitive-app-secret" not in str(captured.value)
    assert requests[0].headers["content-type"].startswith("application/json")
    assert json.loads(requests[0].content)["redirect_uri"] == (
        "http://localhost/callback"
    )
