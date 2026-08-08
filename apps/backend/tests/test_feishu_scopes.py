from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from uuid import UUID

import pytest

from legal_workbench.application.feishu_scopes import FeishuScopeService
from legal_workbench.domain.entities import (
    IdempotencyRecord,
    IntegrationScope,
)
from legal_workbench.domain.enums import (
    IntegrationIdentityType,
    IntegrationScopeStatus,
    IntegrationScopeType,
    IntegrationSyncMode,
)
from legal_workbench.domain.errors import EntityVersionConflictError


class ScopeRepository:
    def __init__(self) -> None:
        self.values: dict[UUID, IntegrationScope] = {}

    async def list_scopes(self, *, provider: str) -> Sequence[IntegrationScope]:
        return [value for value in self.values.values() if value.provider == provider]

    async def find_scope(
        self, *, provider: str, external_scope_id: str
    ) -> IntegrationScope | None:
        return next(
            (
                value
                for value in self.values.values()
                if value.provider == provider
                and value.external_scope_id == external_scope_id
            ),
            None,
        )

    async def get_scope(self, scope_id: UUID) -> IntegrationScope | None:
        return self.values.get(scope_id)

    async def get_scope_for_update(self, scope_id: UUID) -> IntegrationScope | None:
        return self.values.get(scope_id)

    async def add_scope(self, value: IntegrationScope) -> None:
        self.values[value.id] = value

    async def save_scope(self, value: IntegrationScope) -> None:
        self.values[value.id] = value


class AppendRepository:
    def __init__(self) -> None:
        self.values: list[object] = []

    async def add(self, value: object) -> None:
        self.values.append(value)


class IdempotencyRepository:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], IdempotencyRecord] = {}

    async def get(self, *, operation: str, key: str) -> IdempotencyRecord | None:
        return self.values.get((operation, key))

    async def add(self, value: IdempotencyRecord) -> None:
        self.values[(value.operation, value.idempotency_key)] = value


class State:
    def __init__(self) -> None:
        self.setup = ScopeRepository()
        self.audit_events = AppendRepository()
        self.idempotency = IdempotencyRepository()

    def factory(self) -> UnitOfWork:
        return UnitOfWork(self)


class UnitOfWork:
    def __init__(self, state: State) -> None:
        self.setup = state.setup
        self.audit_events = state.audit_events
        self.idempotency = state.idempotency

    async def __aenter__(self) -> UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        return None

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_new_chat_is_unapproved_and_disabled_until_legal_allows_it() -> None:
    state = State()
    service = FeishuScopeService(state.factory)

    scope = await service.register_known_chat(
        chat_id="oc_synthetic_sensitive_group",
        display_name="合成敏感群",
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-register",
        idempotency_key="idem-register",
    )

    assert scope.status == IntegrationScopeStatus.UNAPPROVED
    assert scope.sync_mode == IntegrationSyncMode.DISABLED
    assert len(state.audit_events.values) == 1


@pytest.mark.asyncio
async def test_user_group_discovery_creates_unapproved_identity_bound_scopes() -> None:
    state = State()
    service = FeishuScopeService(state.factory)
    authorization_id = UUID("00000000-0000-0000-0000-000000000301")

    class Client:
        async def list_chats(
            self, *, authorization_id: UUID, page_token: str | None = None
        ) -> tuple[tuple[dict[str, object], ...], str | None]:
            assert page_token is None
            return (({"chat_id": "oc_discovered", "name": "发现的法务群"}),), None

    scopes = await service.discover_user_groups(
        authorization_id=authorization_id,
        client=Client(),
        actor_id="legal",
        correlation_id="corr-discover",
    )

    assert len(scopes) == 1
    scope = scopes[0]
    assert scope.status == IntegrationScopeStatus.UNAPPROVED
    assert scope.sync_mode == IntegrationSyncMode.DISABLED
    assert scope.identity_type == IntegrationIdentityType.USER
    assert scope.scope_type == IntegrationScopeType.GROUP
    assert scope.authorization_id == authorization_id


@pytest.mark.asyncio
async def test_allow_pause_resume_and_exclude_use_domain_versions() -> None:
    state = State()
    service = FeishuScopeService(state.factory)
    scope = await service.register_known_chat(
        chat_id="oc_synthetic_scope",
        display_name="合成测试群",
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-register",
        idempotency_key="idem-register",
    )

    allowed = await service.change_scope(
        scope_id=scope.id,
        expected_version=1,
        action="allow",
        sync_mode=IntegrationSyncMode.ALL_MESSAGES,
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-allow",
        idempotency_key="idem-allow",
    )
    paused = await service.change_scope(
        scope_id=scope.id,
        expected_version=2,
        action="pause",
        sync_mode=None,
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-pause",
        idempotency_key="idem-pause",
    )
    resumed = await service.change_scope(
        scope_id=scope.id,
        expected_version=3,
        action="resume",
        sync_mode=IntegrationSyncMode.MENTIONS_ONLY,
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-resume",
        idempotency_key="idem-resume",
    )
    excluded = await service.change_scope(
        scope_id=scope.id,
        expected_version=4,
        action="exclude",
        sync_mode=None,
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-exclude",
        idempotency_key="idem-exclude",
    )

    assert (allowed.status, allowed.sync_mode, allowed.version) == (
        IntegrationScopeStatus.ALLOWED,
        IntegrationSyncMode.ALL_MESSAGES,
        2,
    )
    assert (paused.status, paused.sync_mode, paused.version) == (
        IntegrationScopeStatus.PAUSED,
        IntegrationSyncMode.DISABLED,
        3,
    )
    assert (resumed.status, resumed.sync_mode, resumed.version) == (
        IntegrationScopeStatus.ALLOWED,
        IntegrationSyncMode.MENTIONS_ONLY,
        4,
    )
    assert (excluded.status, excluded.sync_mode, excluded.version) == (
        IntegrationScopeStatus.EXCLUDED,
        IntegrationSyncMode.DISABLED,
        5,
    )


@pytest.mark.asyncio
async def test_scope_version_conflict_never_overwrites_newer_decision() -> None:
    state = State()
    service = FeishuScopeService(state.factory)
    scope = await service.register_known_chat(
        chat_id="oc_versioned_scope",
        display_name=None,
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-register",
        idempotency_key="idem-register",
    )
    await service.change_scope(
        scope_id=scope.id,
        expected_version=1,
        action="allow",
        sync_mode=IntegrationSyncMode.MENTIONS_ONLY,
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-allow",
        idempotency_key="idem-allow",
    )

    with pytest.raises(EntityVersionConflictError):
        await service.change_scope(
            scope_id=scope.id,
            expected_version=1,
            action="exclude",
            sync_mode=None,
            actor_id="legal",
            actor_source="test",
            correlation_id="corr-stale",
            idempotency_key="idem-stale",
        )

    stored = state.setup.values[scope.id]
    assert stored.status == IntegrationScopeStatus.ALLOWED
    assert stored.version == 2


@pytest.mark.asyncio
async def test_manual_compensation_is_recorded_but_not_executed() -> None:
    state = State()
    service = FeishuScopeService(state.factory)
    scope = await service.register_known_chat(
        chat_id="oc_deferred_reconcile",
        display_name="延后补偿群",
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-register",
        idempotency_key="idem-register",
    )

    result = await service.defer_compensation(
        scope_id=scope.id,
        expected_version=1,
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-reconcile",
        idempotency_key="idem-reconcile",
    )

    assert result.state == "not_executed"
    assert result.error_code == "REAL_FEISHU_PHASE_DEFERRED"
    assert result.scope.last_compensation_status == "not_executed"
    assert result.scope.last_compensated_at is not None
    assert result.scope.version == 2


@pytest.mark.asyncio
async def test_scope_api_exposes_versioned_decisions_and_deferred_compensation() -> None:
    from httpx import ASGITransport, AsyncClient

    from legal_workbench.api.auth import RequestActor
    from legal_workbench.api.dependencies import get_request_actor
    from legal_workbench.api.routes.feishu_scopes import get_feishu_scope_service
    from legal_workbench.main import app

    state = State()
    service = FeishuScopeService(state.factory)
    app.dependency_overrides[get_request_actor] = lambda: RequestActor(
        actor_id="legal", identity_source="test"
    )
    app.dependency_overrides[get_feishu_scope_service] = lambda: service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            registered = await client.post(
                "/api/v1/settings/feishu-scopes",
                headers={
                    "Idempotency-Key": "api-register",
                    "X-Correlation-ID": "api-register-correlation",
                },
                json={"chatId": "oc_api_scope", "displayName": "合成 API 群"},
            )
            scope_id = registered.json()["id"]
            allowed = await client.patch(
                f"/api/v1/settings/feishu-scopes/{scope_id}",
                headers={"Idempotency-Key": "api-allow", "If-Match": "1"},
                json={"action": "allow", "syncMode": "mentions_only"},
            )
            stale = await client.patch(
                f"/api/v1/settings/feishu-scopes/{scope_id}",
                headers={"Idempotency-Key": "api-stale", "If-Match": "1"},
                json={"action": "exclude"},
            )
            compensated = await client.post(
                f"/api/v1/settings/feishu-scopes/{scope_id}/compensate",
                headers={
                    "Idempotency-Key": "api-compensate",
                    "If-Match": "2",
                    "X-Correlation-ID": "api-compensation-correlation",
                },
            )
            listed = await client.get("/api/v1/settings/feishu-scopes")
    finally:
        app.dependency_overrides.pop(get_request_actor, None)
        app.dependency_overrides.pop(get_feishu_scope_service, None)

    assert registered.status_code == 200
    assert registered.json()["status"] == "unapproved"
    assert allowed.status_code == 200
    assert allowed.json()["syncMode"] == "mentions_only"
    assert allowed.json()["version"] == 2
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "ENTITY_VERSION_CONFLICT"
    assert compensated.status_code == 200
    assert compensated.json()["state"] == "not_executed"
    assert compensated.json()["errorCode"] == "REAL_FEISHU_PHASE_DEFERRED"
    assert compensated.json()["correlationId"] == "api-compensation-correlation"
    assert listed.status_code == 200
    assert listed.json()[0]["lastCompensationStatus"] == "not_executed"
