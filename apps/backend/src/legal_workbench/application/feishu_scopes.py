from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from uuid import UUID, uuid4

from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.application.setup import REAL_FEISHU_PHASE_DEFERRED
from legal_workbench.domain.entities import (
    AuditEvent,
    IdempotencyRecord,
    IntegrationScope,
)
from legal_workbench.domain.enums import (
    IntegrationScopeStatus,
    IntegrationSyncMode,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityNotFoundError,
    EntityVersionConflictError,
    IdempotencyConflictError,
)


def _hash_payload(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class DeferredCompensationResult:
    scope: IntegrationScope
    state: str
    error_code: str
    message: str
    correlation_id: str
    idempotent_replay: bool = False


class FeishuScopeService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def list_scopes(self) -> tuple[IntegrationScope, ...]:
        async with self._uow_factory() as uow:
            values = await uow.setup.list_scopes(provider="feishu")
        return tuple(
            sorted(
                values,
                key=lambda value: (
                    value.display_name or "",
                    value.external_scope_id,
                    str(value.id),
                ),
            )
        )

    async def register_known_chat(
        self,
        *,
        chat_id: str,
        display_name: str | None,
        actor_id: str,
        actor_source: str,
        correlation_id: str,
        idempotency_key: str,
    ) -> IntegrationScope:
        normalized_chat_id = chat_id.strip()
        normalized_name = (display_name or "").strip() or None
        if not normalized_chat_id:
            raise DomainValidationError("A Feishu chat ID is required.")
        operation = "register_feishu_scope"
        request_hash = _hash_payload(
            {"chatId": normalized_chat_id, "displayName": normalized_name}
        )
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=operation, key=idempotency_key)
            replay = await uow.idempotency.get(operation=operation, key=idempotency_key)
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "Idempotency key was used for another Feishu scope."
                    )
                existing = await uow.setup.get_scope(
                    UUID(str(replay.response_payload["scopeId"]))
                )
                if existing is None:
                    raise EntityNotFoundError("The registered Feishu scope was not found.")
                return copy.deepcopy(existing)
            existing = await uow.setup.find_scope(
                provider="feishu", external_scope_id=normalized_chat_id
            )
            if existing is None:
                existing = IntegrationScope(
                    id=uuid4(),
                    provider="feishu",
                    external_scope_id=normalized_chat_id,
                    display_name=normalized_name,
                    status=IntegrationScopeStatus.UNAPPROVED,
                    sync_mode=IntegrationSyncMode.DISABLED,
                )
                await uow.setup.add_scope(existing)
                await uow.audit_events.add(
                    AuditEvent(
                        id=uuid4(),
                        aggregate_type="integration_scope",
                        aggregate_id=existing.id,
                        event_type="feishu_scope_registered",
                        actor_id=actor_id,
                        actor_source=actor_source,
                        payload={
                            "status": existing.status.value,
                            "syncMode": existing.sync_mode.value,
                        },
                        correlation_id=correlation_id,
                    )
                )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=operation,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_payload={"scopeId": str(existing.id)},
                )
            )
            await uow.commit()
            return copy.deepcopy(existing)

    async def change_scope(
        self,
        *,
        scope_id: UUID,
        expected_version: int,
        action: str,
        sync_mode: IntegrationSyncMode | None,
        actor_id: str,
        actor_source: str,
        correlation_id: str,
        idempotency_key: str,
    ) -> IntegrationScope:
        if action not in {"allow", "exclude", "pause", "resume"}:
            raise DomainValidationError("Unsupported Feishu scope action.")
        operation = f"change_feishu_scope:{scope_id}:{action}"
        request_hash = _hash_payload(
            {
                "scopeId": str(scope_id),
                "expectedVersion": expected_version,
                "action": action,
                "syncMode": sync_mode.value if sync_mode else None,
            }
        )
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=operation, key=idempotency_key)
            replay = await uow.idempotency.get(operation=operation, key=idempotency_key)
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "Idempotency key was used for another scope change."
                    )
                stored = await uow.setup.get_scope(scope_id)
                if stored is None:
                    raise EntityNotFoundError("Feishu scope was not found.")
                return copy.deepcopy(stored)
            scope = await uow.setup.get_scope_for_update(scope_id)
            if scope is None:
                raise EntityNotFoundError("Feishu scope was not found.")
            if scope.version != expected_version:
                raise EntityVersionConflictError(
                    "Feishu scope changed before this decision was applied."
                )
            if action in {"allow", "resume"} and sync_mode in {
                None,
                IntegrationSyncMode.DISABLED,
            }:
                raise DomainValidationError(
                    "Allowing or resuming a scope requires a sync mode."
                )
            if action == "allow":
                assert sync_mode is not None
                scope.allow(sync_mode=sync_mode, actor_id=actor_id)
            elif action == "resume":
                assert sync_mode is not None
                scope.resume(sync_mode=sync_mode, actor_id=actor_id)
            elif action == "pause":
                scope.pause()
            else:
                scope.exclude()
            await uow.setup.save_scope(scope)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="integration_scope",
                    aggregate_id=scope.id,
                    event_type=f"feishu_scope_{action}",
                    actor_id=actor_id,
                    actor_source=actor_source,
                    payload={
                        "status": scope.status.value,
                        "syncMode": scope.sync_mode.value,
                        "version": scope.version,
                    },
                    correlation_id=correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=operation,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_payload={
                        "scopeId": str(scope.id),
                        "version": scope.version,
                    },
                )
            )
            await uow.commit()
            return copy.deepcopy(scope)

    async def defer_compensation(
        self,
        *,
        scope_id: UUID,
        expected_version: int,
        actor_id: str,
        actor_source: str,
        correlation_id: str,
        idempotency_key: str,
    ) -> DeferredCompensationResult:
        operation = f"defer_feishu_scope_compensation:{scope_id}"
        request_hash = _hash_payload(
            {"scopeId": str(scope_id), "expectedVersion": expected_version}
        )
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=operation, key=idempotency_key)
            replay = await uow.idempotency.get(operation=operation, key=idempotency_key)
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "Idempotency key was used for another compensation request."
                    )
                scope = await uow.setup.get_scope(scope_id)
                if scope is None:
                    raise EntityNotFoundError("Feishu scope was not found.")
                return self._deferred_result(
                    scope, correlation_id=correlation_id, replay=True
                )
            scope = await uow.setup.get_scope_for_update(scope_id)
            if scope is None:
                raise EntityNotFoundError("Feishu scope was not found.")
            if scope.version != expected_version:
                raise EntityVersionConflictError(
                    "Feishu scope changed before compensation was recorded."
                )
            scope.record_deferred_compensation()
            await uow.setup.save_scope(scope)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="integration_scope",
                    aggregate_id=scope.id,
                    event_type="feishu_scope_compensation_deferred",
                    actor_id=actor_id,
                    actor_source=actor_source,
                    payload={
                        "executed": False,
                        "errorCode": REAL_FEISHU_PHASE_DEFERRED,
                        "version": scope.version,
                    },
                    correlation_id=correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=operation,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_payload={
                        "scopeId": str(scope.id),
                        "version": scope.version,
                        "state": "not_executed",
                    },
                )
            )
            await uow.commit()
            return self._deferred_result(
                scope, correlation_id=correlation_id, replay=False
            )

    @staticmethod
    def _deferred_result(
        scope: IntegrationScope,
        *,
        correlation_id: str,
        replay: bool,
    ) -> DeferredCompensationResult:
        return DeferredCompensationResult(
            scope=copy.deepcopy(scope),
            state="not_executed",
            error_code=REAL_FEISHU_PHASE_DEFERRED,
            message="真实飞书补偿同步按当前实施阶段延后。",
            correlation_id=correlation_id,
            idempotent_replay=replay,
        )
