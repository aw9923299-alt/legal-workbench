from __future__ import annotations

from uuid import uuid4

from legal_workbench.application.commands import (
    ConfirmPriorityCommand,
    CreateDeadlineCommand,
    CreateDependencyCommand,
)
from legal_workbench.application.idempotency import (
    replay_uuid,
    request_hash,
    require_matching_replay,
)
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.application.results import (
    DeadlineCreatedResult,
    DependencyCreatedResult,
    PriorityConfirmedResult,
)
from legal_workbench.domain.entities import (
    AuditEvent,
    Deadline,
    IdempotencyRecord,
    OutboxEvent,
    PriorityConfirmation,
    WorkItemDependency,
)
from legal_workbench.domain.enums import PriorityConfirmationStatus
from legal_workbench.domain.errors import EntityNotFoundError


class ConfirmPriorityHandler:
    OPERATION = "confirm_work_item_priority"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: ConfirmPriorityCommand) -> PriorityConfirmedResult:
        payload = {
            "workItemId": str(command.work_item_id),
            "workItemVersion": command.work_item_version,
            "confirmedPriority": command.confirmed_priority.value,
            "confirmedCompleteAt": command.confirmed_complete_at,
            "reasons": command.reasons,
            "overrideReason": command.override_reason,
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
                return PriorityConfirmedResult(
                    work_item_id=replay_uuid(replay, "workItemId"),
                    confirmation_id=replay_uuid(replay, "confirmationId"),
                    version=int(str(replay.response_payload["version"])),
                    idempotent_replay=True,
                )

            work_item = await uow.work_items.get_for_update(command.work_item_id)
            if work_item is None:
                raise EntityNotFoundError(
                    "Work item was not found.",
                    details={"workItemId": str(command.work_item_id)},
                )
            proposed_priority = work_item.ai_suggested_priority or work_item.priority
            proposed_complete_at = work_item.planned_complete_at
            work_item.confirm_priority(
                actor_id=command.actor_id,
                priority=command.confirmed_priority,
                planned_complete_at=command.confirmed_complete_at,
                reasons=command.reasons,
                override_reason=command.override_reason,
                expected_version=command.work_item_version,
            )
            confirmation = PriorityConfirmation(
                id=uuid4(),
                work_item_id=work_item.id,
                proposed_priority=proposed_priority,
                confirmed_priority=command.confirmed_priority,
                proposed_complete_at=proposed_complete_at,
                confirmed_complete_at=command.confirmed_complete_at,
                reasons=work_item.priority_reasons,
                override_reason=work_item.override_reason,
                confirmed_by=command.actor_id,
                status=PriorityConfirmationStatus.CONFIRMED,
            )
            await uow.work_items.save(work_item)
            await uow.priority_confirmations.add(confirmation)
            event_payload: dict[str, object] = {
                "workItemId": str(work_item.id),
                "confirmationId": str(confirmation.id),
                "priority": command.confirmed_priority.value,
                "plannedCompleteAt": command.confirmed_complete_at,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="work_item",
                    aggregate_id=work_item.id,
                    event_type="work_item_priority_confirmed",
                    actor_id=command.actor_id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="WorkItemPriorityConfirmed",
                    aggregate_type="work_item",
                    aggregate_id=work_item.id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            next_version = work_item.version + 1
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=digest,
                    response_payload={
                        "workItemId": str(work_item.id),
                        "confirmationId": str(confirmation.id),
                        "version": next_version,
                    },
                )
            )
            await uow.commit()
        return PriorityConfirmedResult(
            work_item_id=work_item.id,
            confirmation_id=confirmation.id,
            version=next_version,
        )


class CreateDeadlineHandler:
    OPERATION = "create_deadline"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: CreateDeadlineCommand) -> DeadlineCreatedResult:
        payload = {
            "matterId": str(command.matter_id) if command.matter_id else None,
            "workItemId": str(command.work_item_id) if command.work_item_id else None,
            "deadlineType": command.deadline_type.value,
            "source": command.source.value,
            "dueAt": command.due_at,
            "timezone": command.timezone,
            "isHard": command.is_hard,
            "sourceReference": command.source_reference,
            "confidence": command.confidence,
            "reminderPolicy": command.reminder_policy,
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
                return DeadlineCreatedResult(
                    deadline_id=replay_uuid(replay, "deadlineId"), idempotent_replay=True
                )
            if command.matter_id is not None and await uow.matters.get(command.matter_id) is None:
                raise EntityNotFoundError("Legal matter was not found.")
            if (
                command.work_item_id is not None
                and await uow.work_items.get(command.work_item_id) is None
            ):
                raise EntityNotFoundError("Work item was not found.")
            deadline = Deadline.create(
                deadline_type=command.deadline_type,
                source=command.source,
                due_at=command.due_at,
                timezone=command.timezone,
                is_hard=command.is_hard,
                matter_id=command.matter_id,
                work_item_id=command.work_item_id,
                source_reference=command.source_reference,
                confidence=command.confidence,
                reminder_policy=command.reminder_policy,
                actor_id=command.actor_id,
            )
            await uow.deadlines.add(deadline)
            event_payload: dict[str, object] = {
                "deadlineId": str(deadline.id),
                "matterId": str(command.matter_id) if command.matter_id else None,
                "workItemId": str(command.work_item_id) if command.work_item_id else None,
                "dueAt": command.due_at,
                "isHard": command.is_hard,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="deadline",
                    aggregate_id=deadline.id,
                    event_type="deadline_created",
                    actor_id=command.actor_id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="DeadlineCreated",
                    aggregate_type="deadline",
                    aggregate_id=deadline.id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=digest,
                    response_payload={"deadlineId": str(deadline.id)},
                )
            )
            await uow.commit()
        return DeadlineCreatedResult(deadline_id=deadline.id)


class CreateDependencyHandler:
    OPERATION = "create_work_item_dependency"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: CreateDependencyCommand) -> DependencyCreatedResult:
        payload = {
            "workItemId": str(command.work_item_id),
            "workItemVersion": command.work_item_version,
            "dependsOnWorkItemId": (
                str(command.depends_on_work_item_id) if command.depends_on_work_item_id else None
            ),
            "dependencyType": command.dependency_type.value,
            "externalPartyId": command.external_party_id,
            "description": command.description,
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
                return DependencyCreatedResult(
                    dependency_id=replay_uuid(replay, "dependencyId"),
                    work_item_version=int(str(replay.response_payload["workItemVersion"])),
                    idempotent_replay=True,
                )
            work_item = await uow.work_items.get_for_update(command.work_item_id)
            if work_item is None:
                raise EntityNotFoundError("Work item was not found.")
            if (
                command.depends_on_work_item_id is not None
                and await uow.work_items.get(command.depends_on_work_item_id) is None
            ):
                raise EntityNotFoundError("Predecessor work item was not found.")
            dependency = WorkItemDependency.create(
                work_item_id=command.work_item_id,
                dependency_type=command.dependency_type,
                depends_on_work_item_id=command.depends_on_work_item_id,
                external_party_id=command.external_party_id,
                description=command.description,
            )
            work_item.touch_dependency_change(expected_version=command.work_item_version)
            await uow.dependencies.add(dependency)
            await uow.work_items.save(work_item)
            event_payload: dict[str, object] = {
                "dependencyId": str(dependency.id),
                "workItemId": str(dependency.work_item_id),
                "dependsOnWorkItemId": (
                    str(dependency.depends_on_work_item_id)
                    if dependency.depends_on_work_item_id
                    else None
                ),
                "dependencyType": dependency.dependency_type.value,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="work_item_dependency",
                    aggregate_id=dependency.id,
                    event_type="work_item_dependency_created",
                    actor_id=command.actor_id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="WorkItemDependencyCreated",
                    aggregate_type="work_item_dependency",
                    aggregate_id=dependency.id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=digest,
                    response_payload={
                        "dependencyId": str(dependency.id),
                        "workItemVersion": work_item.version,
                    },
                )
            )
            await uow.commit()
        return DependencyCreatedResult(
            dependency_id=dependency.id, work_item_version=work_item.version
        )
