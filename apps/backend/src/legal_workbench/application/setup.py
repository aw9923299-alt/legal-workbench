from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from legal_workbench.agents.codex_health import (
    CodexHealthStatus,
    CodexRuntimeHealth,
)
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.config import Settings
from legal_workbench.domain.entities import (
    AuditEvent,
    IdempotencyRecord,
    IntegrationCheckRun,
    OutboxEvent,
)
from legal_workbench.domain.enums import IntegrationCheckStatus, SetupState
from legal_workbench.domain.errors import DomainValidationError, IdempotencyConflictError
from legal_workbench.infrastructure.secrets import LocalSecretProvider

REAL_FEISHU_PHASE_DEFERRED = "REAL_FEISHU_PHASE_DEFERRED"


class CodexHealthChecker(Protocol):
    async def check(self) -> CodexRuntimeHealth: ...


class CodexSmokeExecutor(Protocol):
    async def execute(self, *, check_run_id: UUID) -> tuple[str | None, str | None]: ...


BasicServicesProbe = Callable[[], Mapping[str, str] | Awaitable[Mapping[str, str]]]


@dataclass(frozen=True, slots=True)
class SetupComponent:
    state: SetupState
    message: str
    correlation_id: str
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class MaskedCredentialStatus:
    configured: bool
    app_id_masked: str | None
    secret_masked: str | None
    last_validation_status: str | None
    last_error_code: str | None


@dataclass(frozen=True, slots=True)
class FeishuSetupStatus:
    credentials: MaskedCredentialStatus
    permissions: SetupComponent
    scopes: SetupComponent
    connection: SetupComponent
    test_message: SetupComponent
    manual_unread_acceptance: SetupComponent
    event_source: str
    receive_direct_messages: bool
    group_mentions_only: bool
    configured_group_all_messages: bool
    allowed_scope_count: int
    excluded_scope_count: int


@dataclass(frozen=True, slots=True)
class CodexSetupStatus:
    cli: SetupComponent
    version: SetupComponent
    authentication: SetupComponent
    smoke_test: SetupComponent
    expected_version: str
    detected_version: str | None


@dataclass(frozen=True, slots=True)
class SetupStep:
    number: int
    key: str
    title: str
    component: SetupComponent


@dataclass(frozen=True, slots=True)
class SetupStatus:
    generated_at: datetime
    correlation_id: str
    overall_state: SetupState
    basic_services: dict[str, str]
    feishu: FeishuSetupStatus
    codex: CodexSetupStatus
    steps: tuple[SetupStep, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["generated_at"] = self.generated_at.isoformat()
        return value


@dataclass(frozen=True, slots=True)
class SetupActionResult:
    state: SetupState
    message: str
    correlation_id: str
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CodexCheckRequested:
    check_run_id: UUID
    state: SetupState
    message: str
    correlation_id: str
    idempotent_replay: bool = False


def _component(
    state: SetupState,
    message: str,
    correlation_id: str,
    error_code: str | None = None,
) -> SetupComponent:
    return SetupComponent(
        state=state,
        message=message,
        correlation_id=correlation_id,
        error_code=error_code,
    )


def _mask_identifier(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if len(normalized) <= 6:
        return "••••"
    return f"{normalized[:3]}••••{normalized[-3:]}"


class SetupService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        settings: Settings,
        secret_provider: LocalSecretProvider,
        codex_health_checker: CodexHealthChecker,
        basic_services_probe: BasicServicesProbe,
    ) -> None:
        self._uow_factory = uow_factory
        self._settings = settings
        self._secret_provider = secret_provider
        self._codex_health_checker = codex_health_checker
        self._basic_services_probe = basic_services_probe

    async def get_status(self, *, correlation_id: str) -> SetupStatus:
        probe_value = self._basic_services_probe()
        basic_services = dict(
            await probe_value if inspect.isawaitable(probe_value) else probe_value
        )
        health = await self._codex_health_checker.check()
        async with self._uow_factory() as uow:
            app_id_setting = await uow.setup.get_setting("feishu.app_id")
            policy_settings = {
                key: await uow.setup.get_setting(key)
                for key in (
                    "feishu.event_source",
                    "feishu.receive_direct_messages",
                    "feishu.group_mentions_only",
                    "feishu.configured_group_all_messages",
                    "feishu.allowed_chat_ids",
                    "feishu.excluded_chat_ids",
                )
            }
            credential = await uow.setup.get_credential(
                provider="feishu", credential_kind="app_secret"
            )
            scopes = await uow.setup.list_scopes(provider="feishu")
            latest_validate = await uow.setup.latest_check(provider="codex", check_kind="validate")
            latest_smoke = await uow.setup.latest_check(provider="codex", check_kind="smoke_test")
        app_id = (
            str(app_id_setting.value)
            if app_id_setting is not None
            else self._settings.feishu_app_id
        )
        secret_configured = bool(
            (
                credential
                and credential.configured
                and credential.secret_ref
                and self._secret_provider.exists(credential.secret_ref)
            )
            or (self._settings.feishu_app_secret or "").strip()
        )
        configured = bool((app_id or "").strip() and secret_configured)
        credentials = MaskedCredentialStatus(
            configured=configured,
            app_id_masked=_mask_identifier(app_id),
            secret_masked=(
                credential.masked_hint if credential else "••••" if secret_configured else None
            ),
            last_validation_status=(credential.last_validation_status if credential else None),
            last_error_code=(credential.last_error_code if credential else None),
        )

        def policy_value(key: str, fallback: object) -> object:
            setting = policy_settings[key]
            return setting.value if setting is not None else fallback

        configured_allowed = policy_value(
            "feishu.allowed_chat_ids", self._settings.feishu_allowed_chat_ids
        )
        configured_excluded = policy_value(
            "feishu.excluded_chat_ids", self._settings.feishu_excluded_chat_ids
        )
        allowed_ids = {
            str(value)
            for value in (configured_allowed if isinstance(configured_allowed, list) else [])
        }
        excluded_ids = {
            str(value)
            for value in (configured_excluded if isinstance(configured_excluded, list) else [])
        }
        allowed_ids.update(
            value.external_scope_id for value in scopes if value.status.value == "allowed"
        )
        excluded_ids.update(
            value.external_scope_id for value in scopes if value.status.value == "excluded"
        )
        deferred = _component(
            SetupState.NOT_EXECUTED,
            "按当前实施阶段。真实飞书联调与官方长连接尚未执行。",
            correlation_id,
            REAL_FEISHU_PHASE_DEFERRED,
        )
        credentials_component = _component(
            SetupState.NOT_EXECUTED if configured else SetupState.NOT_CONFIGURED,
            "凭证已安全配置。等待恢复真实验证。" if configured else "尚未配置完整飞书应用凭证。",
            correlation_id,
            REAL_FEISHU_PHASE_DEFERRED if configured else "FEISHU_CREDENTIALS_NOT_CONFIGURED",
        )
        scope_status = _component(
            SetupState.READY if allowed_ids or excluded_ids else SetupState.NOT_CONFIGURED,
            f"已记录 {len(allowed_ids)} 个允许群和 {len(excluded_ids)} 个排除群。"
            if allowed_ids or excluded_ids
            else "尚未记录群聊授权范围。敏感群默认不接入。",
            correlation_id,
            None if scopes else "FEISHU_SCOPES_NOT_CONFIGURED",
        )
        feishu = FeishuSetupStatus(
            credentials=credentials,
            permissions=deferred,
            scopes=scope_status,
            connection=deferred,
            test_message=deferred,
            manual_unread_acceptance=deferred,
            event_source=str(
                policy_value("feishu.event_source", self._settings.feishu_event_source.value)
            ),
            receive_direct_messages=bool(
                policy_value(
                    "feishu.receive_direct_messages",
                    self._settings.feishu_receive_direct_messages,
                )
            ),
            group_mentions_only=bool(
                policy_value(
                    "feishu.group_mentions_only",
                    self._settings.feishu_group_mentions_only,
                )
            ),
            configured_group_all_messages=bool(
                policy_value(
                    "feishu.configured_group_all_messages",
                    self._settings.feishu_configured_group_all_messages,
                )
            ),
            allowed_scope_count=len(allowed_ids),
            excluded_scope_count=len(excluded_ids),
        )
        cli, version, authentication = self._codex_components(
            health, latest_validate, correlation_id
        )
        smoke = self._check_component(
            latest_smoke,
            correlation_id=correlation_id,
            default_message="尚未执行真实 Codex 冒烟测试。",
            default_error="CODEX_SMOKE_TEST_NOT_EXECUTED",
        )
        codex = CodexSetupStatus(
            cli=cli,
            version=version,
            authentication=authentication,
            smoke_test=smoke,
            expected_version=self._settings.codex_expected_version,
            detected_version=health.detected_version,
        )
        basic_state = (
            SetupState.READY
            if basic_services and all(value == "ready" for value in basic_services.values())
            else SetupState.RUNTIME_UNREACHABLE
        )
        steps = (
            SetupStep(
                1,
                "basic_services",
                "基础服务",
                _component(basic_state, "基础服务状态已检测。", correlation_id),
            ),
            SetupStep(2, "feishu_credentials", "飞书凭证", credentials_component),
            SetupStep(3, "feishu_permissions", "飞书权限", deferred),
            SetupStep(4, "feishu_scopes", "群聊范围", scope_status),
            SetupStep(5, "feishu_connection", "长连接", deferred),
            SetupStep(6, "codex_version", "Codex 版本", version),
            SetupStep(7, "codex_authentication", "Codex 认证", authentication),
            SetupStep(8, "test_message", "测试消息", deferred),
            SetupStep(
                9,
                "completion",
                "完成状态",
                _component(
                    SetupState.NOT_EXECUTED,
                    "真实飞书验收延后。当前不能标记全部完成。",
                    correlation_id,
                    REAL_FEISHU_PHASE_DEFERRED,
                ),
            ),
        )
        return SetupStatus(
            generated_at=datetime.now(UTC),
            correlation_id=correlation_id,
            overall_state=SetupState.NOT_EXECUTED,
            basic_services=basic_services,
            feishu=feishu,
            codex=codex,
            steps=steps,
        )

    async def defer_feishu_action(
        self,
        *,
        action: str,
        actor_id: str,
        actor_source: str,
        correlation_id: str,
        credentials_supplied: bool = False,
    ) -> SetupActionResult:
        if action not in {"validate", "start", "stop"}:
            raise DomainValidationError("Unsupported Feishu setup action.")
        async with self._uow_factory() as uow:
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="integration_setup",
                    aggregate_id=uuid4(),
                    event_type=f"feishu_{action}_deferred",
                    actor_id=actor_id,
                    actor_source=actor_source,
                    payload={
                        "action": action,
                        "credentialsSupplied": credentials_supplied,
                        "executed": False,
                    },
                    correlation_id=correlation_id,
                )
            )
            await uow.commit()
        return SetupActionResult(
            state=SetupState.NOT_EXECUTED,
            message="按用户确认的实施顺序。本阶段不执行真实飞书验证或长连接操作。",
            correlation_id=correlation_id,
            error_code=REAL_FEISHU_PHASE_DEFERRED,
        )

    async def request_codex_check(
        self,
        *,
        check_kind: str,
        actor_id: str,
        actor_source: str,
        correlation_id: str,
        idempotency_key: str,
    ) -> CodexCheckRequested:
        if check_kind not in {"validate", "smoke_test"}:
            raise DomainValidationError("Unsupported Codex setup check.")
        operation = f"request_codex_setup_{check_kind}"
        request_hash = hashlib.sha256(
            json.dumps({"checkKind": check_kind}, sort_keys=True).encode()
        ).hexdigest()
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=operation, key=idempotency_key)
            replay = await uow.idempotency.get(operation=operation, key=idempotency_key)
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "Idempotency key was used for another setup check."
                    )
                return CodexCheckRequested(
                    check_run_id=UUID(str(replay.response_payload["checkRunId"])),
                    state=SetupState.PENDING,
                    message="Codex 检查已在 Worker 队列中。",
                    correlation_id=correlation_id,
                    idempotent_replay=True,
                )
            check = IntegrationCheckRun(
                id=uuid4(),
                provider="codex",
                check_kind=check_kind,
                status=IntegrationCheckStatus.PENDING,
                requested_by=actor_id,
                correlation_id=correlation_id,
                started_at=datetime.now(UTC),
            )
            await uow.setup.add_check(check)
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="CodexSetupCheckRequested",
                    aggregate_type="integration_check_run",
                    aggregate_id=check.id,
                    payload={"checkKind": check_kind},
                    correlation_id=correlation_id,
                )
            )
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="integration_check_run",
                    aggregate_id=check.id,
                    event_type="codex_setup_check_requested",
                    actor_id=actor_id,
                    actor_source=actor_source,
                    payload={"checkKind": check_kind},
                    correlation_id=correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=operation,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_payload={"checkRunId": str(check.id)},
                )
            )
            await uow.commit()
        return CodexCheckRequested(
            check_run_id=check.id,
            state=SetupState.PENDING,
            message="Codex 检查已提交给隔离 Worker。",
            correlation_id=correlation_id,
        )

    @staticmethod
    def _codex_components(
        health: CodexRuntimeHealth,
        latest_validate: IntegrationCheckRun | None,
        correlation_id: str,
    ) -> tuple[SetupComponent, SetupComponent, SetupComponent]:
        if health.status == CodexHealthStatus.MISCONFIGURED and health.executable is None:
            cli_state = SetupState.CLI_MISSING
        elif health.status == CodexHealthStatus.MISCONFIGURED:
            cli_state = SetupState.RUNTIME_UNREACHABLE
        elif health.status == CodexHealthStatus.VERSION_MISMATCH:
            cli_state = SetupState.VERSION_MISMATCH
        elif health.status == CodexHealthStatus.UNREACHABLE:
            cli_state = SetupState.RUNTIME_UNREACHABLE
        else:
            cli_state = SetupState.READY
        cli = _component(
            cli_state,
            health.detail,
            correlation_id,
            None if cli_state == SetupState.READY else f"CODEX_{cli_state.value.upper()}",
        )
        version = _component(
            SetupState.VERSION_MISMATCH
            if health.status == CodexHealthStatus.VERSION_MISMATCH
            else cli_state,
            health.detail,
            correlation_id,
            "CODEX_VERSION_MISMATCH"
            if health.status == CodexHealthStatus.VERSION_MISMATCH
            else None,
        )
        if latest_validate and latest_validate.status in {
            IntegrationCheckStatus.COMPLETED,
            IntegrationCheckStatus.FAILED,
        }:
            authentication = SetupService._check_component(
                latest_validate,
                correlation_id=correlation_id,
                default_message="尚未由 Worker 验证 Codex 认证。",
                default_error="CODEX_AUTH_NOT_EXECUTED",
            )
        elif health.status == CodexHealthStatus.AVAILABLE:
            authentication = _component(SetupState.AUTHENTICATED, health.detail, correlation_id)
        elif health.status == CodexHealthStatus.UNAUTHENTICATED:
            authentication = _component(
                SetupState.UNAUTHENTICATED, health.detail, correlation_id, "CODEX_UNAUTHENTICATED"
            )
        elif health.status == CodexHealthStatus.UNREACHABLE:
            authentication = _component(
                SetupState.RUNTIME_UNREACHABLE,
                health.detail,
                correlation_id,
                "CODEX_RUNTIME_UNREACHABLE",
            )
        else:
            authentication = _component(
                SetupState.NOT_EXECUTED,
                "CLI 未就绪。尚未检查认证。",
                correlation_id,
                "CODEX_AUTH_NOT_EXECUTED",
            )
        return cli, version, authentication

    @staticmethod
    def _check_component(
        check: IntegrationCheckRun | None,
        *,
        correlation_id: str,
        default_message: str,
        default_error: str,
    ) -> SetupComponent:
        if check is None:
            return _component(
                SetupState.NOT_EXECUTED, default_message, correlation_id, default_error
            )
        try:
            state = SetupState(check.state)
        except ValueError:
            state = SetupState.RUNTIME_UNREACHABLE
        return _component(
            state,
            check.detail or default_message,
            correlation_id,
            check.error_code,
        )


def _worker_health_result(
    health: CodexRuntimeHealth,
) -> tuple[SetupState, str | None, str]:
    if health.status == CodexHealthStatus.AVAILABLE:
        return SetupState.AUTHENTICATED, None, health.detail
    if health.status == CodexHealthStatus.VERSION_MISMATCH:
        return SetupState.VERSION_MISMATCH, "CODEX_VERSION_MISMATCH", health.detail
    if health.status == CodexHealthStatus.UNAUTHENTICATED:
        return SetupState.UNAUTHENTICATED, "CODEX_UNAUTHENTICATED", health.detail
    if health.status == CodexHealthStatus.UNREACHABLE:
        return SetupState.RUNTIME_UNREACHABLE, "CODEX_RUNTIME_UNREACHABLE", health.detail
    return SetupState.CLI_MISSING, "CODEX_CLI_MISSING", health.detail


async def execute_codex_setup_check(
    *,
    check_run_id: UUID,
    uow_factory: UnitOfWorkFactory,
    health_checker: CodexHealthChecker,
    real_runtime_enabled: bool,
    smoke_executor: CodexSmokeExecutor | None = None,
) -> IntegrationCheckRun:
    """Run outside a database transaction and persist only redacted health facts."""

    async with uow_factory() as uow:
        check = await uow.setup.get_check_for_update(check_run_id)
        if check is None:
            raise DomainValidationError("Codex integration check was not found.")
        if check.status != IntegrationCheckStatus.PENDING:
            return check
        check.start()
        await uow.setup.save_check(check)
        await uow.commit()

    health = await health_checker.check()
    state, error_code, detail = _worker_health_result(health)
    runtime_version = health.detected_version
    if check.check_kind == "smoke_test":
        if not real_runtime_enabled:
            state = SetupState.RUNTIME_UNREACHABLE
            error_code = "CODEX_REAL_RUNTIME_DISABLED"
            detail = "Real Codex runtime is disabled for this Worker."
        elif error_code is None and smoke_executor is None:
            state = SetupState.RUNTIME_UNREACHABLE
            error_code = "CODEX_SMOKE_RUNNER_UNREACHABLE"
            detail = "The isolated Codex smoke runner is unavailable."
        elif error_code is None and smoke_executor is not None:
            runtime_version, smoke_error = await smoke_executor.execute(check_run_id=check_run_id)
            if smoke_error is None:
                state = SetupState.READY
                detail = "Real Codex smoke inference completed with synthetic data."
            else:
                state = SetupState.RUNTIME_UNREACHABLE
                error_code = smoke_error
                detail = "Real Codex smoke inference failed."
    async with uow_factory() as uow:
        stored = await uow.setup.get_check_for_update(check_run_id)
        if stored is None:
            raise DomainValidationError("Codex integration check disappeared.")
        if stored.status != IntegrationCheckStatus.RUNNING:
            return stored
        stored.finish(
            state=state.value,
            error_code=error_code,
            detail=detail,
            runtime_version=runtime_version,
        )
        await uow.setup.save_check(stored)
        await uow.audit_events.add(
            AuditEvent(
                id=uuid4(),
                aggregate_type="integration_check_run",
                aggregate_id=stored.id,
                event_type="codex_setup_check_completed",
                actor_id="codex-worker",
                actor_source="worker",
                payload={
                    "checkKind": stored.check_kind,
                    "state": stored.state,
                    "errorCode": stored.error_code,
                    "runtimeVersion": stored.runtime_version,
                },
                correlation_id=stored.correlation_id,
            )
        )
        await uow.commit()
        return stored


__all__ = ["SetupService", "SetupState", "execute_codex_setup_check"]
