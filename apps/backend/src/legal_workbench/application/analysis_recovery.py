from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from legal_workbench.application.ports import UnitOfWork, UnitOfWorkFactory
from legal_workbench.domain.entities import AuditEvent, OutboxEvent
from legal_workbench.domain.enums import AgentRunStatus, FeishuMessageStatus


@dataclass(frozen=True, slots=True)
class AnalysisRecoveryResult:
    missing_runs_requeued: int = 0
    stale_runs_requeued: int = 0
    dead_lettered: int = 0


class AnalysisRecoveryService:
    """Recover durable analysis work after Redis or worker process loss."""

    EVENT_TYPE = "FeishuMessageAnalysisRequested"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        stale_after_seconds: int = 120,
        batch_size: int = 100,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._stale_after_seconds = stale_after_seconds
        self._batch_size = batch_size
        self._now = now or (lambda: datetime.now(UTC))

    async def recover(self) -> AnalysisRecoveryResult:
        now = self._now()
        cutoff = now - timedelta(seconds=self._stale_after_seconds)
        missing_runs_requeued = 0
        stale_runs_requeued = 0
        dead_lettered = 0
        async with self._uow_factory() as uow:
            # The transaction advisory lock prevents a scheduler and manual API
            # recovery from emitting duplicate durable work concurrently.
            await uow.lock_idempotency(operation="analysis_recovery", key="global")
            queued_messages = await uow.feishu.list_queued_without_active_run(
                limit=self._batch_size
            )
            for message in queued_messages:
                if await self._ensure_recovery_event(
                    uow,
                    message_id=message.id,
                    reason="missing_active_agent_run",
                    correlation_id=f"analysis-recovery:{uuid4()}",
                ):
                    missing_runs_requeued += 1

            stale_queued = await uow.agent_runs.list_stale(
                statuses=[AgentRunStatus.QUEUED],
                older_than=cutoff,
                limit=self._batch_size,
            )
            for run in stale_queued:
                if run.feishu_message_id is None:
                    continue
                if await self._ensure_recovery_event(
                    uow,
                    message_id=run.feishu_message_id,
                    reason="stale_queued_agent_run",
                    correlation_id=run.correlation_id,
                ):
                    stale_runs_requeued += 1

            stale_leases = await uow.agent_runs.list_stale(
                statuses=[AgentRunStatus.PREPARING, AgentRunStatus.RUNNING],
                older_than=cutoff,
                limit=self._batch_size,
            )
            for run in stale_leases:
                if run.feishu_message_id is None:
                    continue
                if run.lease_expires_at is not None and run.lease_expires_at > now:
                    continue
                recovered_message = await uow.feishu.get_message_for_update(
                    run.feishu_message_id
                )
                if recovered_message is None:
                    continue
                run.failure_code = "AGENT_LEASE_EXPIRED"
                run.failure_message = "Agent worker heartbeat lease expired."
                run.lease_expires_at = None
                run.transition_to(AgentRunStatus.FAILED, now=now)
                if recovered_message.status in {
                    FeishuMessageStatus.QUEUED_FOR_ANALYSIS,
                    FeishuMessageStatus.CONTEXT_PREPARED,
                    FeishuMessageStatus.AGENT_QUEUED,
                    FeishuMessageStatus.ANALYSING,
                }:
                    recovered_message.transition_to(
                        FeishuMessageStatus.ANALYSIS_FAILED,
                        failure_code=run.failure_code,
                        failure_message=run.failure_message,
                    )
                if run.attempt_number >= run.max_attempts:
                    run.transition_to(AgentRunStatus.DEAD_LETTER, now=now)
                    if recovered_message.status == FeishuMessageStatus.ANALYSIS_FAILED:
                        recovered_message.transition_to(
                            FeishuMessageStatus.DEAD_LETTER,
                            failure_code=run.failure_code,
                            failure_message=run.failure_message,
                        )
                    dead_lettered += 1
                    recovery_action = "dead_lettered"
                else:
                    created = await self._ensure_recovery_event(
                        uow,
                        message_id=recovered_message.id,
                        reason="expired_agent_lease",
                        correlation_id=run.correlation_id,
                    )
                    stale_runs_requeued += int(created)
                    recovery_action = "requeued" if created else "already_pending"
                await uow.agent_runs.save(run)
                await uow.feishu.save_message(recovered_message)
                await uow.audit_events.add(
                    AuditEvent(
                        id=uuid4(),
                        aggregate_type="agent_run",
                        aggregate_id=run.id,
                        event_type="agent_run_lease_recovered",
                        actor_id="analysis-recovery",
                        actor_source="system",
                        payload={
                            "messageId": str(recovered_message.id),
                            "failureCode": run.failure_code,
                            "attemptNumber": run.attempt_number,
                            "action": recovery_action,
                        },
                        correlation_id=run.correlation_id,
                    )
                )
            await uow.commit()
        return AnalysisRecoveryResult(
            missing_runs_requeued=missing_runs_requeued,
            stale_runs_requeued=stale_runs_requeued,
            dead_lettered=dead_lettered,
        )

    async def _ensure_recovery_event(
        self,
        uow: UnitOfWork,
        *,
        message_id: UUID,
        reason: str,
        correlation_id: str,
    ) -> bool:
        if await uow.outbox_events.exists_pending(
            event_type=self.EVENT_TYPE,
            aggregate_id=message_id,
        ):
            return False
        payload: dict[str, object] = {
            "messageId": str(message_id),
            "actorId": "analysis-recovery",
            "actorSource": "system",
            "forceNewRun": False,
            "recoverInterruptedRun": True,
            "recoveryReason": reason,
        }
        await uow.outbox_events.add(
            OutboxEvent(
                id=uuid4(),
                event_type=self.EVENT_TYPE,
                aggregate_type="feishu_message",
                aggregate_id=message_id,
                payload=payload,
                correlation_id=correlation_id,
            )
        )
        await uow.audit_events.add(
            AuditEvent(
                id=uuid4(),
                aggregate_type="feishu_message",
                aggregate_id=message_id,
                event_type="message_analysis_recovery_enqueued",
                actor_id="analysis-recovery",
                actor_source="system",
                payload=payload,
                correlation_id=correlation_id,
            )
        )
        return True
