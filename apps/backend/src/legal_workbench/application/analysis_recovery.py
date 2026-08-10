from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from legal_workbench.application.agent_attempts import (
    AgentAttemptService,
    AgentExecutionLeaseService,
)
from legal_workbench.application.ports import UnitOfWork, UnitOfWorkFactory
from legal_workbench.domain.entities import AgentRun, AuditEvent, OutboxEvent
from legal_workbench.domain.enums import (
    AgentExecutionPlanStatus,
    AgentPlanStepStatus,
    AgentRunRole,
    AgentRunStatus,
    FeishuMessageStatus,
)


@dataclass(frozen=True, slots=True)
class AnalysisRecoveryResult:
    missing_runs_requeued: int = 0
    stale_runs_requeued: int = 0
    dead_lettered: int = 0
    legal_runs_requeued: int = 0
    legal_dead_lettered: int = 0


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
        legal_runs_requeued = 0
        legal_dead_lettered = 0
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

            for run in stale_queued:
                if run.execution_plan_id is None:
                    continue
                recovered_run = await uow.agent_runs.get_for_update(run.id)
                if recovered_run is None or recovered_run.execution_plan_id is None:
                    continue
                if not await self._is_current_legal_run(uow, recovered_run):
                    await self._cancel_superseded_legal_run(
                        uow, recovered_run, now=now
                    )
                    continue
                if await self._ensure_legal_recovery_event(
                    uow,
                    plan_id=recovered_run.execution_plan_id,
                    run_id=recovered_run.id,
                    run_role=recovered_run.run_role,
                    reason="stale_queued_agent_run",
                    correlation_id=recovered_run.correlation_id,
                ):
                    legal_runs_requeued += 1

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
                attempt_expired = await AgentAttemptService(
                    uow.agent_run_attempts,
                    lease_seconds=self._stale_after_seconds,
                    now=self._now,
                ).expire_current(
                    run_id=run.id,
                    attempt_number=run.attempt_number,
                )
                if not attempt_expired:
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
                            "attemptExpired": attempt_expired,
                            "action": recovery_action,
                        },
                        correlation_id=run.correlation_id,
                    )
                )

            stale_legal_leases = await uow.agent_runs.list_stale(
                statuses=[
                    AgentRunStatus.PREPARING,
                    AgentRunStatus.RUNNING,
                    AgentRunStatus.VALIDATING,
                ],
                older_than=cutoff,
                limit=self._batch_size,
            )
            for candidate in stale_legal_leases:
                if candidate.execution_plan_id is None:
                    continue
                if (
                    candidate.lease_expires_at is not None
                    and candidate.lease_expires_at > now
                ):
                    continue
                recovered_run = await uow.agent_runs.get_for_update(candidate.id)
                if recovered_run is None or recovered_run.execution_plan_id is None:
                    continue
                current_lineage = await self._is_current_legal_run(uow, recovered_run)
                attempt_expired = await AgentExecutionLeaseService(
                    uow.agent_run_attempts,
                    lease_seconds=self._stale_after_seconds,
                    now=self._now,
                ).expire_current(recovered_run)
                if not attempt_expired:
                    continue
                if not current_lineage:
                    await self._cancel_superseded_legal_run(
                        uow, recovered_run, now=now
                    )
                    continue
                recovered_run.failure_code = "AGENT_LEASE_EXPIRED"
                recovered_run.failure_message = "Agent worker heartbeat lease expired."
                recovered_run.transition_to(AgentRunStatus.FAILED, now=now)
                if recovered_run.attempt_number >= recovered_run.max_attempts:
                    recovered_run.transition_to(AgentRunStatus.DEAD_LETTER, now=now)
                    await self._mark_legal_phase_terminal(uow, recovered_run, now=now)
                    legal_dead_lettered += 1
                    recovery_action = "dead_lettered"
                else:
                    recovered_run.attempt_number += 1
                    recovered_run.transition_to(AgentRunStatus.QUEUED, now=now)
                    recovered_run.finished_at = None
                    recovered_run.worker_id = None
                    recovered_run.failure_code = None
                    recovered_run.failure_message = None
                    created = await self._ensure_legal_recovery_event(
                        uow,
                        plan_id=recovered_run.execution_plan_id,
                        run_id=recovered_run.id,
                        run_role=recovered_run.run_role,
                        reason="expired_agent_lease",
                        correlation_id=recovered_run.correlation_id,
                    )
                    legal_runs_requeued += int(created)
                    recovery_action = "requeued" if created else "already_pending"
                await uow.agent_runs.save(recovered_run)
                await uow.audit_events.add(
                    AuditEvent(
                        id=uuid4(),
                        aggregate_type="agent_run",
                        aggregate_id=recovered_run.id,
                        event_type="legal_agent_run_lease_recovered",
                        actor_id="analysis-recovery",
                        actor_source="system",
                        payload={
                            "planId": str(recovered_run.execution_plan_id),
                            "runRole": recovered_run.run_role.value,
                            "attemptNumber": recovered_run.attempt_number,
                            "attemptExpired": attempt_expired,
                            "action": recovery_action,
                        },
                        correlation_id=recovered_run.correlation_id,
                    )
                )
            await uow.commit()
        return AnalysisRecoveryResult(
            missing_runs_requeued=missing_runs_requeued,
            stale_runs_requeued=stale_runs_requeued,
            dead_lettered=dead_lettered,
            legal_runs_requeued=legal_runs_requeued,
            legal_dead_lettered=legal_dead_lettered,
        )

    async def _is_current_legal_run(
        self,
        uow: UnitOfWork,
        run: AgentRun,
    ) -> bool:
        if run.execution_plan_id is None:
            return False
        plan = await uow.agent_execution_plans.get_for_update(run.execution_plan_id)
        if plan is None:
            return False
        if run.run_role == AgentRunRole.BUTLER_PLANNING:
            return plan.planning_run_id == run.id
        if run.run_role == AgentRunRole.BUTLER_SYNTHESIS:
            return plan.synthesis_run_id == run.id
        if run.run_role != AgentRunRole.SPECIALIST or run.plan_step_id is None:
            return False
        matching = next(
            (value for value in plan.steps if value.id == run.plan_step_id),
            None,
        )
        if matching is None:
            return False
        step = await uow.agent_execution_plans.get_step_for_update(
            plan.id, matching.step_id
        )
        return step is not None and step.latest_run_id == run.id

    async def _cancel_superseded_legal_run(
        self,
        uow: UnitOfWork,
        run: AgentRun,
        *,
        now: datetime,
    ) -> None:
        run.failure_code = "AGENT_RUN_SUPERSEDED"
        run.failure_message = "A newer current Run owns this legal execution phase."
        run.lease_expires_at = None
        run.worker_id = None
        run.transition_to(AgentRunStatus.CANCELLED, now=now)
        await uow.agent_runs.save(run)
        await uow.audit_events.add(
            AuditEvent(
                id=uuid4(),
                aggregate_type="agent_run",
                aggregate_id=run.id,
                event_type="legal_agent_run_superseded",
                actor_id="analysis-recovery",
                actor_source="system",
                payload={
                    "planId": str(run.execution_plan_id),
                    "runRole": run.run_role.value,
                    "attemptNumber": run.attempt_number,
                    "action": "cancelled_without_requeue",
                },
                correlation_id=run.correlation_id,
            )
        )

    async def _mark_legal_phase_terminal(
        self,
        uow: UnitOfWork,
        run: AgentRun,
        *,
        now: datetime,
    ) -> None:
        if run.execution_plan_id is None:
            return
        plan = await uow.agent_execution_plans.get_for_update(run.execution_plan_id)
        if plan is None:
            return
        if run.run_role == AgentRunRole.SPECIALIST and run.plan_step_id is not None:
            matching = next(
                (value for value in plan.steps if value.id == run.plan_step_id),
                None,
            )
            if matching is None:
                return
            step = await uow.agent_execution_plans.get_step_for_update(
                plan.id, matching.step_id
            )
            if step is None or step.latest_run_id != run.id:
                return
            step.status = AgentPlanStepStatus.FAILED
            step.failure_code = "AGENT_MAX_ATTEMPTS_EXHAUSTED"
            step.failure_message = "Agent lease recovery attempts were exhausted."
            step.updated_at = now
            step.version += 1
            await uow.agent_execution_plans.save_step(step)
        elif (
            run.run_role == AgentRunRole.BUTLER_PLANNING
            and plan.planning_run_id != run.id
        ) or (
            run.run_role == AgentRunRole.BUTLER_SYNTHESIS
            and plan.synthesis_run_id != run.id
        ):
            return
        completed = any(
            value.status
            in {
                AgentPlanStepStatus.COMPLETED,
                AgentPlanStepStatus.NEEDS_INFORMATION,
            }
            for value in plan.steps
        )
        plan.status = (
            AgentExecutionPlanStatus.PARTIAL
            if completed and run.run_role != AgentRunRole.BUTLER_PLANNING
            else AgentExecutionPlanStatus.FAILED
        )
        plan.updated_at = now
        plan.version += 1
        await uow.agent_execution_plans.save(plan)

    async def _ensure_legal_recovery_event(
        self,
        uow: UnitOfWork,
        *,
        plan_id: UUID,
        run_id: UUID,
        run_role: AgentRunRole,
        reason: str,
        correlation_id: str,
    ) -> bool:
        event_type = "LegalAgentRecoveryRequested"
        if await uow.outbox_events.exists_pending(
            event_type=event_type,
            aggregate_id=plan_id,
        ):
            return False
        payload: dict[str, object] = {
            "planId": str(plan_id),
            "runId": str(run_id),
            "runRole": run_role.value,
            "recoveryReason": reason,
        }
        await uow.outbox_events.add(
            OutboxEvent(
                id=uuid4(),
                event_type=event_type,
                aggregate_type="agent_execution_plan",
                aggregate_id=plan_id,
                payload=payload,
                correlation_id=correlation_id,
            )
        )
        await uow.audit_events.add(
            AuditEvent(
                id=uuid4(),
                aggregate_type="agent_execution_plan",
                aggregate_id=plan_id,
                event_type="legal_agent_recovery_enqueued",
                actor_id="analysis-recovery",
                actor_source="system",
                payload=payload,
                correlation_id=correlation_id,
            )
        )
        return True

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
