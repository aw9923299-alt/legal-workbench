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
from legal_workbench.domain.enums import FeishuUserAuthorizationStatus
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

    async def exchange_code(self, *, code: str, code_verifier: str) -> FeishuOAuthTokens:
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
                        "refresh_expires_in": 2592000,
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
        tokens = await client.exchange_code(code="oauth-code", code_verifier="verifier")
        assert tokens.access_token == "http-access-token"
        assert tokens.refresh_token == "http-refresh-token"
        with pytest.raises(FeishuUserApiError) as captured:
            await client.get_identity(access_token="sensitive-refresh-token")

    assert captured.value.code == 20001
    assert "sensitive-refresh-token" not in str(captured.value)
    assert "sensitive-app-secret" not in str(captured.value)
    assert requests[0].headers["content-type"].startswith("application/json")
