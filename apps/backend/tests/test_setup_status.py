from __future__ import annotations

import json
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from uuid import UUID

import pytest

from legal_workbench.agents.codex_health import (
    CodexHealthStatus,
    CodexRuntimeHealth,
)
from legal_workbench.api.auth import RequestActor
from legal_workbench.application.setup import (
    SetupService,
    SetupState,
    execute_codex_setup_check,
)
from legal_workbench.config import Settings
from legal_workbench.domain.entities import (
    AuditEvent,
    IdempotencyRecord,
    IntegrationCheckRun,
    IntegrationCredential,
    IntegrationScope,
    OutboxEvent,
    SystemSetting,
)
from legal_workbench.infrastructure.secrets import LocalSecretProvider


class SetupRepository:
    def __init__(self) -> None:
        self.settings: dict[str, SystemSetting] = {}
        self.credentials: dict[tuple[str, str], IntegrationCredential] = {}
        self.scopes: list[IntegrationScope] = []
        self.checks: dict[UUID, IntegrationCheckRun] = {}

    async def get_setting(self, key: str) -> SystemSetting | None:
        return self.settings.get(key)

    async def save_setting(self, value: SystemSetting) -> None:
        self.settings[value.key] = value

    async def get_credential(
        self, *, provider: str, credential_kind: str
    ) -> IntegrationCredential | None:
        return self.credentials.get((provider, credential_kind))

    async def save_credential(self, value: IntegrationCredential) -> None:
        self.credentials[(value.provider, value.credential_kind)] = value

    async def list_scopes(self, *, provider: str) -> Sequence[IntegrationScope]:
        return [value for value in self.scopes if value.provider == provider]

    async def add_check(self, value: IntegrationCheckRun) -> None:
        self.checks[value.id] = value

    async def get_check(self, check_run_id: UUID) -> IntegrationCheckRun | None:
        return self.checks.get(check_run_id)

    async def get_check_for_update(self, check_run_id: UUID) -> IntegrationCheckRun | None:
        return self.checks.get(check_run_id)

    async def save_check(self, value: IntegrationCheckRun) -> None:
        self.checks[value.id] = value

    async def latest_check(self, *, provider: str, check_kind: str) -> IntegrationCheckRun | None:
        values = [
            value
            for value in self.checks.values()
            if value.provider == provider and value.check_kind == check_kind
        ]
        return max(values, key=lambda value: value.created_at) if values else None


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


class FakeState:
    def __init__(self) -> None:
        self.setup = SetupRepository()
        self.audit_events = AppendRepository()
        self.outbox_events = AppendRepository()
        self.idempotency = IdempotencyRepository()

    def factory(self) -> FakeUnitOfWork:
        return FakeUnitOfWork(self)


class FakeUnitOfWork:
    def __init__(self, state: FakeState) -> None:
        self.setup = state.setup
        self.audit_events = state.audit_events
        self.outbox_events = state.outbox_events
        self.idempotency = state.idempotency

    async def __aenter__(self) -> FakeUnitOfWork:
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


@dataclass
class HealthChecker:
    health: CodexRuntimeHealth

    async def check(self) -> CodexRuntimeHealth:
        return self.health


def health(
    status: CodexHealthStatus,
    *,
    detected: str | None = "0.146.0",
    authentication: str = "not_checked",
) -> CodexRuntimeHealth:
    return CodexRuntimeHealth(
        status=status,
        executable=None if detected is None else "/opt/codex",
        detected_version=detected,
        expected_version="0.146.0",
        authentication=authentication,
        runtime_directory_writable=True,
        detail=f"synthetic {status.value}",
    )


def service(
    state: FakeState,
    *,
    codex_health: CodexRuntimeHealth,
    secret_provider: LocalSecretProvider,
    settings: Settings | None = None,
) -> SetupService:
    return SetupService(
        state.factory,
        settings=settings
        or Settings(
            environment="test",
            session_secret="test-session-secret-that-is-long-enough",
            _env_file=None,
        ),
        secret_provider=secret_provider,
        codex_health_checker=HealthChecker(codex_health),
        basic_services_probe=lambda: {
            "api": "ready",
            "postgresql": "ready",
            "redis": "ready",
            "worker": "ready",
            "scheduler": "ready",
        },
    )


def test_local_secret_provider_uses_private_atomic_files(tmp_path: Path) -> None:
    provider = LocalSecretProvider(tmp_path / "secrets")

    reference = provider.write("feishu_app_secret", "sensitive-feishu-secret")

    assert provider.exists(reference)
    assert provider.read(reference) == "sensitive-feishu-secret"
    assert stat.S_IMODE((tmp_path / "secrets").stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "secrets" / "feishu_app_secret.secret").stat().st_mode) == 0o600
    assert "sensitive-feishu-secret" not in repr(provider)
    assert not list((tmp_path / "secrets").glob("*.tmp"))


@pytest.mark.asyncio
async def test_setup_status_never_returns_secret_and_marks_feishu_deferred(
    tmp_path: Path,
) -> None:
    state = FakeState()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    secret_ref = secrets.write("feishu_app_secret", "sensitive-feishu-secret")
    state.setup.credentials[("feishu", "app_secret")] = IntegrationCredential(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        provider="feishu",
        credential_kind="app_secret",
        secret_ref=secret_ref,
        configured=True,
        masked_hint="••••cret",
    )
    state.setup.settings["feishu.app_id"] = SystemSetting.create(
        key="feishu.app_id",
        value="cli_test_app_id",
        updated_by="legal",
    )

    status = await service(
        state,
        codex_health=health(CodexHealthStatus.UNAUTHENTICATED),
        secret_provider=secrets,
    ).get_status(correlation_id="corr-setup")
    serialized = json.dumps(status.to_dict(), ensure_ascii=False)

    assert status.feishu.credentials.configured is True
    assert status.feishu.connection.state == SetupState.NOT_EXECUTED
    assert status.feishu.connection.error_code == "REAL_FEISHU_PHASE_DEFERRED"
    assert status.feishu.manual_unread_acceptance.state == SetupState.NOT_EXECUTED
    assert "sensitive-feishu-secret" not in serialized
    assert "cli_test_app_id" not in serialized
    assert "corr-setup" in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime_health", "expected_cli", "expected_auth"),
    [
        (health(CodexHealthStatus.MISCONFIGURED, detected=None), "cli_missing", "not_executed"),
        (health(CodexHealthStatus.VERSION_MISMATCH), "version_mismatch", "not_executed"),
        (health(CodexHealthStatus.UNAUTHENTICATED), "ready", "unauthenticated"),
        (health(CodexHealthStatus.UNREACHABLE), "runtime_unreachable", "runtime_unreachable"),
        (
            health(CodexHealthStatus.AVAILABLE, authentication="api_key"),
            "ready",
            "authenticated",
        ),
    ],
)
async def test_setup_status_maps_codex_health_states(
    tmp_path: Path,
    runtime_health: CodexRuntimeHealth,
    expected_cli: str,
    expected_auth: str,
) -> None:
    state = FakeState()

    status = await service(
        state,
        codex_health=runtime_health,
        secret_provider=LocalSecretProvider(tmp_path / "secrets"),
    ).get_status(correlation_id="corr-codex")

    assert status.codex.cli.state.value == expected_cli
    assert status.codex.authentication.state.value == expected_auth


@pytest.mark.asyncio
async def test_deferred_feishu_action_does_not_store_supplied_secret(tmp_path: Path) -> None:
    state = FakeState()
    secrets = LocalSecretProvider(tmp_path / "secrets")
    setup = service(
        state,
        codex_health=health(CodexHealthStatus.UNAUTHENTICATED),
        secret_provider=secrets,
    )

    result = await setup.defer_feishu_action(
        action="validate",
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-feishu",
        credentials_supplied=True,
    )

    assert result.state == SetupState.NOT_EXECUTED
    assert result.error_code == "REAL_FEISHU_PHASE_DEFERRED"
    assert not secrets.exists("feishu_app_secret")
    assert state.setup.credentials == {}
    assert isinstance(state.audit_events.values[0], AuditEvent)


@pytest.mark.asyncio
async def test_codex_validate_is_queued_for_worker_and_idempotent(tmp_path: Path) -> None:
    state = FakeState()
    setup = service(
        state,
        codex_health=health(CodexHealthStatus.UNAUTHENTICATED),
        secret_provider=LocalSecretProvider(tmp_path / "secrets"),
    )

    first = await setup.request_codex_check(
        check_kind="validate",
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-worker",
        idempotency_key="idem-worker",
    )
    replay = await setup.request_codex_check(
        check_kind="validate",
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-worker",
        idempotency_key="idem-worker",
    )

    assert first.check_run_id == replay.check_run_id
    assert replay.idempotent_replay is True
    assert len(state.setup.checks) == 1
    assert len(state.outbox_events.values) == 1
    event = state.outbox_events.values[0]
    assert isinstance(event, OutboxEvent)
    assert event.event_type == "CodexSetupCheckRequested"
    assert event.payload == {"checkKind": "validate"}


@pytest.mark.asyncio
async def test_codex_worker_check_persists_redacted_ready_result(tmp_path: Path) -> None:
    state = FakeState()
    setup = service(
        state,
        codex_health=health(CodexHealthStatus.UNAUTHENTICATED),
        secret_provider=LocalSecretProvider(tmp_path / "secrets"),
    )
    requested = await setup.request_codex_check(
        check_kind="validate",
        actor_id="legal",
        actor_source="test",
        correlation_id="corr-worker-run",
        idempotency_key="idem-worker-run",
    )

    completed = await execute_codex_setup_check(
        check_run_id=requested.check_run_id,
        uow_factory=state.factory,
        health_checker=HealthChecker(
            health(CodexHealthStatus.AVAILABLE, authentication="api_key")
        ),
        real_runtime_enabled=True,
    )

    assert completed.state == "authenticated"
    assert completed.error_code is None
    assert completed.runtime_version == "0.146.0"
    serialized = json.dumps(completed.detail)
    assert "api_key" not in serialized


@pytest.mark.asyncio
async def test_setup_api_returns_correlation_and_stable_deferred_code(
    tmp_path: Path,
) -> None:
    from httpx import ASGITransport, AsyncClient

    from legal_workbench.api.dependencies import get_request_actor
    from legal_workbench.api.routes.setup import get_setup_service
    from legal_workbench.main import app

    state = FakeState()
    setup = service(
        state,
        codex_health=health(CodexHealthStatus.UNAUTHENTICATED),
        secret_provider=LocalSecretProvider(tmp_path / "secrets"),
    )
    app.dependency_overrides[get_request_actor] = lambda: RequestActor(
        actor_id="legal", identity_source="test"
    )
    app.dependency_overrides[get_setup_service] = lambda: setup
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            status_response = await client.get(
                "/api/v1/setup/status", headers={"X-Correlation-ID": "corr-status-api"}
            )
            deferred_response = await client.post(
                "/api/v1/setup/feishu/validate",
                headers={"X-Correlation-ID": "corr-feishu-api"},
                json={"appId": "cli_test", "appSecret": "must-not-be-returned"},
            )
    finally:
        app.dependency_overrides.pop(get_request_actor, None)
        app.dependency_overrides.pop(get_setup_service, None)

    assert status_response.status_code == 200
    assert status_response.json()["correlationId"] == "corr-status-api"
    assert deferred_response.status_code == 200
    assert deferred_response.json()["state"] == "not_executed"
    assert deferred_response.json()["errorCode"] == "REAL_FEISHU_PHASE_DEFERRED"
    assert deferred_response.json()["correlationId"] == "corr-feishu-api"
    assert "must-not-be-returned" not in deferred_response.text
