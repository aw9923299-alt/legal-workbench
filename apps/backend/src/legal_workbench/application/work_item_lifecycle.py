from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from legal_workbench.application.idempotency import (
    request_hash,
    require_matching_replay,
)
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import AuditEvent, IdempotencyRecord, OutboxEvent
from legal_workbench.domain.enums import DependencyStatus, WorkItemAction, WorkItemStatus
from legal_workbench.domain.errors import EntityNotFoundError, InvalidStateTransitionError


@dataclass(frozen=True, slots=True)
class WorkItemActionCommand:
    work_item_id: UUID
    action: WorkItemAction
    expected_version: int
    actor_id: str
    correlation_id: str
    idempotency_key: str
    reason: str | None = None
    owner_id: str | None = None
    deadline: datetime | None = None
    next_action: str | None = None
    waiting_party_id: str | None = None
    blocker_owner_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkItemActionResult:
    work_item_id: UUID
    status: WorkItemStatus
    version: int
    idempotent_replay: bool = False

    @classmethod
    def from_replay(cls, payload: dict[str, object]) -> WorkItemActionResult:
        return cls(
            work_item_id=UUID(str(payload["workItemId"])),
            status=WorkItemStatus(str(payload["status"])),
            version=int(str(payload["version"])),
            idempotent_replay=True,
        )


@dataclass(frozen=True, slots=True)
class ResolveDependencyCommand:
    work_item_id: UUID
    dependency_id: UUID
    work_item_version: int
    dependency_version: int
    actor_id: str
    correlation_id: str
    idempotency_key: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DependencyResolvedResult:
    work_item_id: UUID
    dependency_id: UUID
    work_item_version: int
    dependency_version: int
    status: DependencyStatus
    idempotent_replay: bool = False

    @classmethod
    def from_replay(cls, payload: dict[str, object]) -> DependencyResolvedResult:
        return cls(
            work_item_id=UUID(str(payload["workItemId"])),
            dependency_id=UUID(str(payload["dependencyId"])),
            work_item_version=int(str(payload["workItemVersion"])),
            dependency_version=int(str(payload["dependencyVersion"])),
            status=DependencyStatus(str(payload["status"])),
            idempotent_replay=True,
        )


class WorkItemLifecycleHandler:
    OPERATION = "work_item_action"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: WorkItemActionCommand) -> WorkItemActionResult:
        payload: dict[str, object] = {
            "workItemId": str(command.work_item_id),
            "action": command.action.value,
            "expectedVersion": command.expected_version,
            "reason": command.reason,
            "ownerId": command.owner_id,
            "deadline": command.deadline,
            "nextAction": command.next_action,
            "waitingPartyId": command.waiting_party_id,
            "blockerOwnerId": command.blocker_owner_id,
        }
        digest = request_hash(payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.idempotency_key)
            replay = require_matching_replay(
                await uow.idempotency.get(operation=self.OPERATION, key=command.idempotency_key),
                expected_hash=digest,
                idempotency_key=command.idempotency_key,
            )
            if replay is not None:
                return WorkItemActionResult.from_replay(replay.response_payload)
            item = await uow.work_items.get_for_update(command.work_item_id)
            if item is None:
                raise EntityNotFoundError(
                    "Work item was not found.",
                    details={"workItemId": str(command.work_item_id)},
                )
            dependencies = list(await uow.dependencies.list_by_work_item(item.id))
            item.apply(
                action=command.action,
                actor_id=command.actor_id,
                reason=command.reason,
                expected_version=command.expected_version,
                open_dependencies=[
                    value for value in dependencies if value.status == DependencyStatus.ACTIVE
                ],
                owner_id=command.owner_id,
                deadline=command.deadline,
                next_action=command.next_action,
                waiting_party_id=command.waiting_party_id,
                blocker_owner_id=command.blocker_owner_id,
            )
            await uow.work_items.save(item)
            response_payload: dict[str, object] = {
                "workItemId": str(item.id),
                "status": item.status.value,
                "version": item.version,
            }
            audit_payload = {
                **response_payload,
                "action": command.action.value,
                "reason": command.reason,
                "ownerId": command.owner_id,
                "deadline": command.deadline,
                "nextAction": command.next_action,
                "waitingPartyId": command.waiting_party_id,
                "blockerOwnerId": command.blocker_owner_id,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="work_item",
                    aggregate_id=item.id,
                    event_type=f"work_item_{command.action.value}",
                    actor_id=command.actor_id,
                    payload=audit_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="WorkItemChanged",
                    aggregate_type="work_item",
                    aggregate_id=item.id,
                    payload={**response_payload, "action": command.action.value},
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=digest,
                    response_payload=response_payload,
                )
            )
            await uow.commit()
        return WorkItemActionResult(work_item_id=item.id, status=item.status, version=item.version)


class ResolveDependencyHandler:
    OPERATION = "resolve_work_item_dependency"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: ResolveDependencyCommand) -> DependencyResolvedResult:
        payload: dict[str, object] = {
            "workItemId": str(command.work_item_id),
            "dependencyId": str(command.dependency_id),
            "workItemVersion": command.work_item_version,
            "dependencyVersion": command.dependency_version,
            "reason": command.reason,
        }
        digest = request_hash(payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.idempotency_key)
            replay = require_matching_replay(
                await uow.idempotency.get(operation=self.OPERATION, key=command.idempotency_key),
                expected_hash=digest,
                idempotency_key=command.idempotency_key,
            )
            if replay is not None:
                return DependencyResolvedResult.from_replay(replay.response_payload)
            item = await uow.work_items.get_for_update(command.work_item_id)
            if item is None:
                raise EntityNotFoundError("Work item was not found.")
            dependency = await uow.dependencies.get_for_update(command.dependency_id)
            if dependency is None:
                raise EntityNotFoundError("Work item dependency was not found.")
            if dependency.work_item_id != item.id:
                raise InvalidStateTransitionError(
                    "The dependency does not belong to this work item."
                )
            dependency.resolve(
                actor_id=command.actor_id, expected_version=command.dependency_version
            )
            item.touch_dependency_change(expected_version=command.work_item_version)
            await uow.dependencies.save(dependency)
            await uow.work_items.save(item)
            response_payload: dict[str, object] = {
                "workItemId": str(item.id),
                "dependencyId": str(dependency.id),
                "workItemVersion": item.version,
                "dependencyVersion": dependency.version,
                "status": dependency.status.value,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="work_item_dependency",
                    aggregate_id=dependency.id,
                    event_type="work_item_dependency_resolved",
                    actor_id=command.actor_id,
                    payload={**response_payload, "reason": command.reason},
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="WorkItemDependencyResolved",
                    aggregate_type="work_item_dependency",
                    aggregate_id=dependency.id,
                    payload=response_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=digest,
                    response_payload=response_payload,
                )
            )
            await uow.commit()
        return DependencyResolvedResult(
            work_item_id=item.id,
            dependency_id=dependency.id,
            work_item_version=item.version,
            dependency_version=dependency.version,
            status=dependency.status,
        )
