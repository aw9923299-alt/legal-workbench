from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.application.setup import REAL_FEISHU_PHASE_DEFERRED
from legal_workbench.domain.entities import (
    AuditEvent,
    IdempotencyRecord,
    IntegrationScope,
)
from legal_workbench.domain.enums import (
    IntegrationIdentityType,
    IntegrationScopeStatus,
    IntegrationScopeType,
    IntegrationSyncMode,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityNotFoundError,
    EntityVersionConflictError,
    IdempotencyConflictError,
)
from legal_workbench.integrations.feishu_local_connector import LocalFeishuRecord


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


class UserChatDiscoveryClient(Protocol):
    async def list_chats(
        self, *, authorization_id: UUID, page_token: str | None = None
    ) -> tuple[tuple[dict[str, object], ...], str | None]: ...


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
        identity_type: IntegrationIdentityType = IntegrationIdentityType.APP,
        scope_type: IntegrationScopeType = IntegrationScopeType.GROUP,
        authorization_id: UUID | None = None,
        backfill_days: int = 7,
    ) -> IntegrationScope:
        normalized_chat_id = chat_id.strip()
        normalized_name = (display_name or "").strip() or None
        if not normalized_chat_id:
            raise DomainValidationError("A Feishu chat ID is required.")
        operation = "register_feishu_scope"
        request_hash = _hash_payload(
            {
                "chatId": normalized_chat_id,
                "displayName": normalized_name,
                "identityType": identity_type.value,
                "scopeType": scope_type.value,
                "authorizationId": str(authorization_id) if authorization_id else None,
                "backfillDays": backfill_days,
            }
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
            scopes = await uow.setup.list_scopes(provider="feishu")
            existing = next(
                (
                    value
                    for value in scopes
                    if value.external_scope_id == normalized_chat_id
                    and value.identity_type == identity_type
                    and value.scope_type == scope_type
                    and value.authorization_id == authorization_id
                ),
                None,
            )
            if existing is None:
                existing = IntegrationScope(
                    id=uuid4(),
                    provider="feishu",
                    external_scope_id=normalized_chat_id,
                    display_name=normalized_name,
                    status=IntegrationScopeStatus.UNAPPROVED,
                    sync_mode=IntegrationSyncMode.DISABLED,
                    identity_type=identity_type,
                    scope_type=scope_type,
                    authorization_id=authorization_id,
                    backfill_days=backfill_days,
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
                            "identityType": existing.identity_type.value,
                            "scopeType": existing.scope_type.value,
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

    async def discover_user_groups(
        self,
        *,
        authorization_id: UUID,
        client: UserChatDiscoveryClient,
        actor_id: str,
        correlation_id: str,
    ) -> tuple[IntegrationScope, ...]:
        discovered: list[IntegrationScope] = []
        page_token: str | None = None
        while True:
            chats, page_token = await client.list_chats(
                authorization_id=authorization_id,
                page_token=page_token,
            )
            for chat in chats:
                chat_id = str(chat.get("chat_id") or "").strip()
                if not chat_id:
                    continue
                is_p2p = str(
                    chat.get("chat_mode") or chat.get("chat_type") or ""
                ).lower() == "p2p"
                scope = await self.register_known_chat(
                    chat_id=chat_id,
                    display_name=str(chat.get("name") or "").strip() or None,
                    actor_id=actor_id,
                    actor_source="feishu-user-discovery",
                    correlation_id=correlation_id,
                    idempotency_key=f"discover:{authorization_id}:{chat_id}",
                    identity_type=IntegrationIdentityType.USER,
                    scope_type=(
                        IntegrationScopeType.P2P
                        if is_p2p
                        else IntegrationScopeType.GROUP
                    ),
                    authorization_id=authorization_id,
                )
                discovered.append(scope)
            if page_token is None:
                break
        return tuple(discovered)

    async def discover_local_p2p_chats(
        self,
        *,
        authorization_id: UUID,
        records: tuple[LocalFeishuRecord, ...],
        actor_id: str,
        correlation_id: str,
    ) -> tuple[IntegrationScope, ...]:
        discovered: list[IntegrationScope] = []
        for chat_id in sorted(
            {
                value.chat_id
                for value in records
                if value.chat_type.lower() == "p2p" and value.chat_id
            }
        ):
            discovered.append(
                await self.register_known_chat(
                    chat_id=chat_id,
                    display_name=None,
                    actor_id=actor_id,
                    actor_source="feishu-local-discovery",
                    correlation_id=correlation_id,
                    idempotency_key=f"local-discover:{authorization_id}:{chat_id}",
                    identity_type=IntegrationIdentityType.USER,
                    scope_type=IntegrationScopeType.P2P,
                    authorization_id=authorization_id,
                )
            )
        return tuple(discovered)

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
