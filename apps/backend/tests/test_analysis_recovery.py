from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.analysis_recovery import AnalysisRecoveryService
from legal_workbench.domain.entities import (
    AgentExecutionPlan,
    AgentPlanStep,
    AgentRun,
    AgentRunAttempt,
    AuditEvent,
    FeishuMessage,
    OutboxEvent,
)
from legal_workbench.domain.enums import (
    AgentAttemptStatus,
    AgentExecutionPlanStatus,
    AgentPlanStepStatus,
    AgentRunRole,
    AgentRunStatus,
    FeishuMessageStatus,
)

NOW = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)


def _message(*, status: FeishuMessageStatus) -> FeishuMessage:
    return FeishuMessage(
        id=uuid4(),
        event_id=uuid4(),
        tenant_key="tenant",
        message_id=f"om_{uuid4().hex}",
        chat_id="oc_chat",
        thread_id=None,
        root_id=None,
        parent_id=None,
        sender_id="ou_sender",
        sender_type="user",
        message_type="text",
        content={"text": "请审核合同"},
        mentions=[],
        create_time=NOW,
        update_time=NOW,
        raw_message={},
        status=status,
    )


def _run(
    message: FeishuMessage,
    *,
    status: AgentRunStatus,
    attempt_number: int = 1,
    max_attempts: int = 2,
) -> AgentRun:
    return AgentRun(
        id=uuid4(),
        agent_definition_id=uuid4(),
        context_snapshot_id=uuid4(),
        status=status,
        objective="judge",
        prompt_snapshot="prompt",
        working_directory="/tmp/run",
        attempt_number=attempt_number,
        max_attempts=max_attempts,
        correlation_id="corr-old",
        created_by="system",
        feishu_message_id=message.id,
        heartbeat_at=NOW - timedelta(minutes=5),
        updated_at=NOW - timedelta(minutes=5),
        lease_expires_at=NOW - timedelta(minutes=4),
    )


class _FeishuRepo:
    def __init__(self, messages: list[FeishuMessage], queued: list[FeishuMessage]) -> None:
        self.messages = {value.id: value for value in messages}
        self.queued = queued

    async def list_queued_without_active_run(self, *, limit: int):  # type: ignore[no-untyped-def]
        return self.queued[:limit]

    async def get_message_for_update(self, message_id: UUID):  # type: ignore[no-untyped-def]
        return self.messages.get(message_id)

    async def save_message(self, message: FeishuMessage) -> None:
        self.messages[message.id] = message


class _RunRepo:
    def __init__(self, stale: list[AgentRun]) -> None:
        self.stale = stale

    async def list_stale(self, *, statuses, older_than, limit):  # type: ignore[no-untyped-def]
        del older_than
        return [value for value in self.stale if value.status in statuses][:limit]

    async def save(self, run: AgentRun) -> None:
        return None

    async def get_for_update(self, run_id: UUID):  # type: ignore[no-untyped-def]
        return next((value for value in self.stale if value.id == run_id), None)


class _PlanRepo:
    def __init__(self, plans: list[AgentExecutionPlan]) -> None:
        self.plans = {value.id: value for value in plans}

    async def get_for_update(self, plan_id: UUID):  # type: ignore[no-untyped-def]
        return self.plans.get(plan_id)

    async def get_step_for_update(self, plan_id: UUID, step_id: str):  # type: ignore[no-untyped-def]
        plan = self.plans.get(plan_id)
        if plan is None:
            return None
        return next((value for value in plan.steps if value.step_id == step_id), None)

    async def save(self, plan: AgentExecutionPlan) -> None:
        self.plans[plan.id] = plan

    async def save_step(self, step: AgentPlanStep) -> None:
        return None


class _AttemptRepo:
    def __init__(
        self,
        attempts: list[AgentRunAttempt],
        *,
        force_expire_result: bool | None = None,
    ) -> None:
        self.attempts = attempts
        self.force_expire_result = force_expire_result

    async def expire_current(
        self,
        *,
        run_id: UUID,
        attempt_number: int,
        finished_at: datetime,
    ) -> bool:
        if self.force_expire_result is False:
            return False
        attempt = next(
            (
                value
                for value in self.attempts
                if value.run_id == run_id
                and value.attempt_number == attempt_number
                and value.status == AgentAttemptStatus.RUNNING
            ),
            None,
        )
        if attempt is None:
            return False
        if attempt.lease_expires_at > finished_at:
            return False
        attempt.expire(now=finished_at)
        return True


class _OutboxRepo:
    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []

    async def exists_pending(self, *, event_type: str, aggregate_id: UUID) -> bool:
        return any(
            value.event_type == event_type and value.aggregate_id == aggregate_id
            for value in self.events
        )

    async def add(self, event: OutboxEvent) -> None:
        self.events.append(event)


class _AuditRepo:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def add(self, event: AuditEvent) -> None:
        self.events.append(event)


class _Uow:
    def __init__(
        self,
        *,
        messages: list[FeishuMessage],
        queued: list[FeishuMessage],
        stale: list[AgentRun],
        plans: list[AgentExecutionPlan] | None = None,
    ) -> None:
        self.feishu = _FeishuRepo(messages, queued)
        self.agent_runs = _RunRepo(stale)
        self.agent_execution_plans = _PlanRepo(plans or [])
        self.agent_run_attempts = _AttemptRepo(
            [
                AgentRunAttempt.start(
                    run_id=run.id,
                    attempt_number=run.attempt_number,
                    lease_token=uuid4(),
                    worker_id=run.worker_id or "worker-stale",
                    lease_expires_at=run.lease_expires_at or NOW,
                    now=run.started_at or run.updated_at,
                )
                for run in stale
                if run.status
                in {
                    AgentRunStatus.PREPARING,
                    AgentRunStatus.RUNNING,
                    AgentRunStatus.VALIDATING,
                }
            ]
        )
        self.outbox_events = _OutboxRepo()
        self.audit_events = _AuditRepo()
        self.locks: list[tuple[str, str]] = []
        self.commits = 0

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        self.locks.append((operation, key))

    async def commit(self) -> None:
        self.commits += 1


class _Factory:
    def __init__(self, uow: _Uow) -> None:
        self.uow = uow

    def __call__(self):  # type: ignore[no-untyped-def]
        return self.uow


@pytest.mark.asyncio
async def test_recovery_recreates_missing_queue_delivery_from_postgres() -> None:
    message = _message(status=FeishuMessageStatus.QUEUED_FOR_ANALYSIS)
    uow = _Uow(messages=[message], queued=[message], stale=[])

    result = await AnalysisRecoveryService(_Factory(uow), now=lambda: NOW).recover()

    assert result.missing_runs_requeued == 1
    assert result.stale_runs_requeued == 0
    assert len(uow.outbox_events.events) == 1
    event = uow.outbox_events.events[0]
    assert event.aggregate_id == message.id
    assert event.payload["recoverInterruptedRun"] is True
    assert uow.locks == [("analysis_recovery", "global")]
    assert uow.commits == 1


@pytest.mark.asyncio
async def test_recovery_expires_worker_lease_and_requeues_retryable_run() -> None:
    message = _message(status=FeishuMessageStatus.ANALYSING)
    run = _run(message, status=AgentRunStatus.RUNNING)
    uow = _Uow(messages=[message], queued=[], stale=[run])

    result = await AnalysisRecoveryService(_Factory(uow), now=lambda: NOW).recover()

    assert result.stale_runs_requeued == 1
    assert result.dead_lettered == 0
    assert run.status == AgentRunStatus.FAILED
    assert run.failure_code == "AGENT_LEASE_EXPIRED"
    assert uow.agent_run_attempts.attempts[0].status == AgentAttemptStatus.EXPIRED
    assert message.status == FeishuMessageStatus.ANALYSIS_FAILED
    assert len(uow.outbox_events.events) == 1


@pytest.mark.asyncio
async def test_recovery_leaves_run_and_plan_unchanged_when_attempt_expiry_cas_loses() -> None:
    plan, run = _legal_fixture(
        run_status=AgentRunStatus.RUNNING,
        run_role=AgentRunRole.SPECIALIST,
    )
    original_attempt_number = run.attempt_number
    original_step_status = plan.steps[1].status
    uow = _Uow(messages=[], queued=[], stale=[run], plans=[plan])
    uow.agent_run_attempts.force_expire_result = False

    result = await AnalysisRecoveryService(_Factory(uow), now=lambda: NOW).recover()

    assert result.legal_runs_requeued == 0
    assert result.legal_dead_lettered == 0
    assert run.status == AgentRunStatus.RUNNING
    assert run.attempt_number == original_attempt_number
    assert run.failure_code is None
    assert plan.status == AgentExecutionPlanStatus.RUNNING
    assert plan.steps[1].status == original_step_status
    assert uow.outbox_events.events == []
    assert uow.audit_events.events == []


@pytest.mark.asyncio
async def test_recovery_dead_letters_exhausted_worker_lease() -> None:
    message = _message(status=FeishuMessageStatus.ANALYSING)
    run = _run(
        message,
        status=AgentRunStatus.RUNNING,
        attempt_number=2,
        max_attempts=2,
    )
    uow = _Uow(messages=[message], queued=[], stale=[run])

    result = await AnalysisRecoveryService(_Factory(uow), now=lambda: NOW).recover()

    assert result.dead_lettered == 1
    assert run.status == AgentRunStatus.DEAD_LETTER
    assert message.status == FeishuMessageStatus.DEAD_LETTER
    assert uow.outbox_events.events == []


def _legal_fixture(
    *,
    run_status: AgentRunStatus,
    run_role: AgentRunRole,
    attempt_number: int = 1,
    max_attempts: int = 2,
) -> tuple[AgentExecutionPlan, AgentRun]:
    plan_id = uuid4()
    completed = AgentPlanStep(
        id=uuid4(),
        execution_plan_id=plan_id,
        step_id="completed-contract",
        sequence=1,
        agent_key="contract_review",
        objective="Completed fixture step.",
        depends_on=[],
        context_requirements=[],
        status=AgentPlanStepStatus.COMPLETED,
        latest_run_id=uuid4(),
        latest_valid_run_id=uuid4(),
        attempt_count=1,
    )
    interrupted = AgentPlanStep(
        id=uuid4(),
        execution_plan_id=plan_id,
        step_id="interrupted-ip",
        sequence=2,
        agent_key="ip_copyright",
        objective="Interrupted fixture step.",
        depends_on=[],
        context_requirements=[],
        status=AgentPlanStepStatus.RUNNING,
        attempt_count=1,
    )
    plan = AgentExecutionPlan(
        id=plan_id,
        matter_id=uuid4(),
        work_item_id=None,
        objective="Recovery fixture plan.",
        status=AgentExecutionPlanStatus.RUNNING,
        task_types=["contract", "ip"],
        synthesis_strategy="Fixture synthesis.",
        missing_information=[],
        requires_user_input=False,
        correlation_id="legal-recovery",
        idempotency_key=f"legal-recovery:{uuid4().hex}",
        created_by="test",
        steps=[completed, interrupted],
    )
    run = AgentRun(
        id=uuid4(),
        agent_definition_id=uuid4(),
        context_snapshot_id=uuid4(),
        status=run_status,
        objective="Interrupted legal phase.",
        prompt_snapshot="Non-sensitive fixture prompt.",
        working_directory="/isolated/legal-recovery",
        attempt_number=attempt_number,
        max_attempts=max_attempts,
        correlation_id=plan.correlation_id,
        created_by="test",
        matter_id=plan.matter_id,
        execution_plan_id=plan.id,
        plan_step_id=interrupted.id if run_role == AgentRunRole.SPECIALIST else None,
        run_role=run_role,
        heartbeat_at=NOW - timedelta(minutes=5),
        updated_at=NOW - timedelta(minutes=5),
        lease_expires_at=NOW - timedelta(minutes=4),
    )
    if run_role == AgentRunRole.SPECIALIST:
        interrupted.latest_run_id = run.id
    elif run_role == AgentRunRole.BUTLER_PLANNING:
        plan.planning_run_id = run.id
        plan.status = AgentExecutionPlanStatus.PLANNING
    else:
        plan.synthesis_run_id = run.id
    return plan, run


@pytest.mark.asyncio
async def test_recovery_requeues_only_stale_legal_specialist_and_preserves_completed_step() -> None:
    plan, run = _legal_fixture(
        run_status=AgentRunStatus.RUNNING,
        run_role=AgentRunRole.SPECIALIST,
    )
    uow = _Uow(messages=[], queued=[], stale=[run], plans=[plan])

    result = await AnalysisRecoveryService(_Factory(uow), now=lambda: NOW).recover()

    assert result.legal_runs_requeued == 1
    assert run.status == AgentRunStatus.QUEUED
    assert run.attempt_number == 2
    assert plan.steps[0].status == AgentPlanStepStatus.COMPLETED
    assert plan.steps[1].status == AgentPlanStepStatus.RUNNING
    assert uow.agent_run_attempts.attempts[0].status == AgentAttemptStatus.EXPIRED
    assert [value.event_type for value in uow.outbox_events.events] == [
        "LegalAgentRecoveryRequested"
    ]


@pytest.mark.asyncio
async def test_recovery_dead_letters_exhausted_synthesis_but_keeps_partial_success() -> None:
    plan, run = _legal_fixture(
        run_status=AgentRunStatus.VALIDATING,
        run_role=AgentRunRole.BUTLER_SYNTHESIS,
        attempt_number=2,
        max_attempts=2,
    )
    uow = _Uow(messages=[], queued=[], stale=[run], plans=[plan])

    result = await AnalysisRecoveryService(_Factory(uow), now=lambda: NOW).recover()

    assert result.legal_dead_lettered == 1
    assert run.status == AgentRunStatus.DEAD_LETTER
    assert plan.status == AgentExecutionPlanStatus.PARTIAL
    assert plan.steps[0].status == AgentPlanStepStatus.COMPLETED
    assert uow.outbox_events.events == []


@pytest.mark.asyncio
async def test_recovery_dead_letter_for_superseded_step_does_not_mutate_current_lineage() -> None:
    plan, stale_run = _legal_fixture(
        run_status=AgentRunStatus.RUNNING,
        run_role=AgentRunRole.SPECIALIST,
        attempt_number=1,
        max_attempts=1,
    )
    current_run_id = uuid4()
    current_step = plan.steps[1]
    current_step.latest_run_id = current_run_id
    current_step.status = AgentPlanStepStatus.RUNNING
    uow = _Uow(messages=[], queued=[], stale=[stale_run], plans=[plan])

    result = await AnalysisRecoveryService(_Factory(uow), now=lambda: NOW).recover()

    assert result.legal_dead_lettered == 1
    assert stale_run.status == AgentRunStatus.DEAD_LETTER
    assert plan.status == AgentExecutionPlanStatus.RUNNING
    assert current_step.status == AgentPlanStepStatus.RUNNING
    assert current_step.latest_run_id == current_run_id
