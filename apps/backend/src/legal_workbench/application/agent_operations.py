from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid4

from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import AuditEvent, IdempotencyRecord
from legal_workbench.domain.enums import AgentRunStatus, FeishuMessageStatus
from legal_workbench.domain.errors import (
    EntityNotFoundError,
    IdempotencyConflictError,
    InvalidStateTransitionError,
)


@dataclass(frozen=True, slots=True)
class CancelAgentRunCommand:
    run_id: UUID
    actor_id: str
    actor_source: str
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class AgentRunOperationResult:
    run_id: UUID
    status: AgentRunStatus
    idempotent_replay: bool = False


class CancelAgentRunHandler:
    OPERATION = "cancel_agent_run"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: CancelAgentRunCommand) -> AgentRunOperationResult:
        request_hash = hashlib.sha256(str(command.run_id).encode()).hexdigest()
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.idempotency_key)
            replay = await uow.idempotency.get(
                operation=self.OPERATION, key=command.idempotency_key
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was used for a different AgentRun."
                    )
                return AgentRunOperationResult(
                    run_id=UUID(str(replay.response_payload["runId"])),
                    status=AgentRunStatus(str(replay.response_payload["status"])),
                    idempotent_replay=True,
                )
            run = await uow.agent_runs.get_for_update(command.run_id)
            if run is None:
                raise EntityNotFoundError(
                    "Agent run was not found.", details={"runId": str(command.run_id)}
                )
            if run.status not in {
                AgentRunStatus.QUEUED,
                AgentRunStatus.PREPARING,
                AgentRunStatus.RUNNING,
                AgentRunStatus.VALIDATING,
            }:
                raise InvalidStateTransitionError(
                    "Only an active AgentRun can be cancelled.",
                    details={"status": run.status.value},
                )
            run.failure_code = "AGENT_RUNTIME_CANCELLED"
            run.failure_message = "Cancelled by an authenticated operator."
            run.lease_expires_at = None
            run.transition_to(AgentRunStatus.CANCELLED)
            if run.feishu_message_id is not None:
                message = await uow.feishu.get_message_for_update(run.feishu_message_id)
                if message is not None and message.status in {
                    FeishuMessageStatus.QUEUED_FOR_ANALYSIS,
                    FeishuMessageStatus.CONTEXT_PREPARED,
                    FeishuMessageStatus.AGENT_QUEUED,
                    FeishuMessageStatus.ANALYSING,
                }:
                    message.transition_to(
                        FeishuMessageStatus.ANALYSIS_FAILED,
                        failure_code=run.failure_code,
                        failure_message=run.failure_message,
                    )
                    await uow.feishu.save_message(message)
            await uow.agent_runs.save(run)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="agent_run",
                    aggregate_id=run.id,
                    event_type="agent_run_cancelled",
                    actor_id=command.actor_id,
                    actor_source=command.actor_source,
                    payload={"failureCode": run.failure_code},
                    correlation_id=command.correlation_id,
                )
            )
            response_payload: dict[str, object] = {
                "runId": str(run.id),
                "status": run.status.value,
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
            return AgentRunOperationResult(run_id=run.id, status=run.status)
