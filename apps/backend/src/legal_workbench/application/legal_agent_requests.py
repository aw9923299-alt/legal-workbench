from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from legal_workbench.agents.professional import LEGAL_SPECIALIST_KEYS
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import AuditEvent, IdempotencyRecord, OutboxEvent
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityNotFoundError,
    IdempotencyConflictError,
)


@dataclass(frozen=True, slots=True)
class RequestLegalAgentOrchestrationCommand:
    matter_id: UUID
    actor_id: str
    correlation_id: str
    idempotency_key: str
    objective: str | None = None
    special_requirements: str | None = None
    specialist_only: str | None = None
    work_item_id: UUID | None = None
    context_snapshot_id: UUID | None = None
    jurisdiction: str = "CN"
    historical_as_of: date | None = None


@dataclass(frozen=True, slots=True)
class LegalAgentRequestResult:
    request_id: UUID
    matter_id: UUID
    context_snapshot_id: UUID
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class RequestLegalAgentStepRerunCommand:
    plan_id: UUID
    step_id: str
    actor_id: str
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class LegalAgentStepRerunRequestResult:
    request_id: UUID
    plan_id: UUID
    step_id: str
    idempotent_replay: bool = False


class RequestLegalAgentOrchestrationHandler:
    OPERATION = "request_legal_agent_orchestration"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, command: RequestLegalAgentOrchestrationCommand
    ) -> LegalAgentRequestResult:
        if (
            command.specialist_only
            and command.specialist_only not in LEGAL_SPECIALIST_KEYS
        ):
            raise DomainValidationError("Only a registered Legal specialist may be requested.")
        request_payload: dict[str, object] = {
            "matterId": str(command.matter_id),
            "workItemId": str(command.work_item_id) if command.work_item_id else None,
            "contextSnapshotId": (
                str(command.context_snapshot_id) if command.context_snapshot_id else None
            ),
            "objective": command.objective,
            "specialRequirements": command.special_requirements,
            "specialistOnly": command.specialist_only,
            "jurisdiction": command.jurisdiction,
            "historicalAsOf": (
                command.historical_as_of.isoformat()
                if command.historical_as_of is not None
                else None
            ),
        }
        request_hash = hashlib.sha256(
            json.dumps(request_payload, sort_keys=True).encode()
        ).hexdigest()
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation=self.OPERATION, key=command.idempotency_key
            )
            replay = await uow.idempotency.get(
                operation=self.OPERATION, key=command.idempotency_key
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was already used for another Legal Agent request."
                    )
                return LegalAgentRequestResult(
                    request_id=UUID(str(replay.response_payload["requestId"])),
                    matter_id=UUID(str(replay.response_payload["matterId"])),
                    context_snapshot_id=UUID(
                        str(replay.response_payload["contextSnapshotId"])
                    ),
                    idempotent_replay=True,
                )
            matter = await uow.matters.get(command.matter_id)
            if matter is None:
                raise EntityNotFoundError("Legal matter was not found.")
            if command.work_item_id is not None:
                work_item = await uow.work_items.get(command.work_item_id)
                if work_item is None or work_item.matter_id != matter.id:
                    raise DomainValidationError(
                        "The requested WorkItem does not belong to this matter."
                    )
            snapshot = (
                await uow.context_snapshots.get(command.context_snapshot_id)
                if command.context_snapshot_id
                else await uow.context_snapshots.find_latest_for_matter(matter.id)
            )
            if snapshot is None:
                raise DomainValidationError(
                    "No authorized ContextSnapshot is available for this matter."
                )
            request_id = uuid4()
            objective = (command.objective or matter.objective or matter.title).strip()
            event_payload = {
                **request_payload,
                "requestId": str(request_id),
                "contextSnapshotId": str(snapshot.id),
                "objective": objective,
                "actorId": command.actor_id,
                "idempotencyKey": f"manual:{matter.id}:{command.idempotency_key}",
                "triggerSource": "manual",
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="legal_matter",
                    aggregate_id=matter.id,
                    event_type="legal_butler_requested",
                    actor_id=command.actor_id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=request_id,
                    event_type="LegalButlerRequested",
                    aggregate_type="legal_matter",
                    aggregate_id=matter.id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            response_payload: dict[str, object] = {
                "requestId": str(request_id),
                "matterId": str(matter.id),
                "contextSnapshotId": str(snapshot.id),
            }
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=request_hash,
                    response_payload=response_payload,
                )
            )
            await uow.commit()
        return LegalAgentRequestResult(
            request_id=request_id,
            matter_id=matter.id,
            context_snapshot_id=snapshot.id,
        )


class RequestLegalAgentStepRerunHandler:
    OPERATION = "request_legal_agent_step_rerun"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, command: RequestLegalAgentStepRerunCommand
    ) -> LegalAgentStepRerunRequestResult:
        request_hash = hashlib.sha256(
            f"{command.plan_id}:{command.step_id}".encode()
        ).hexdigest()
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation=self.OPERATION, key=command.idempotency_key
            )
            replay = await uow.idempotency.get(
                operation=self.OPERATION, key=command.idempotency_key
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was already used for another Step rerun."
                    )
                return LegalAgentStepRerunRequestResult(
                    request_id=UUID(str(replay.response_payload["requestId"])),
                    plan_id=command.plan_id,
                    step_id=command.step_id,
                    idempotent_replay=True,
                )
            plan = await uow.agent_execution_plans.get(command.plan_id)
            if plan is None:
                raise EntityNotFoundError("Agent execution plan was not found.")
            if not any(step.step_id == command.step_id for step in plan.steps):
                raise EntityNotFoundError("Agent execution plan Step was not found.")
            request_id = uuid4()
            payload: dict[str, object] = {
                "requestId": str(request_id),
                "planId": str(plan.id),
                "stepId": command.step_id,
                "actorId": command.actor_id,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="agent_execution_plan",
                    aggregate_id=plan.id,
                    event_type="legal_agent_step_rerun_requested",
                    actor_id=command.actor_id,
                    payload=payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=request_id,
                    event_type="LegalAgentStepRerunRequested",
                    aggregate_type="agent_execution_plan",
                    aggregate_id=plan.id,
                    payload=payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=request_hash,
                    response_payload=payload,
                )
            )
            await uow.commit()
        return LegalAgentStepRerunRequestResult(
            request_id=request_id,
            plan_id=plan.id,
            step_id=command.step_id,
        )
