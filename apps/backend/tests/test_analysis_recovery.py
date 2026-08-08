from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.analysis_recovery import AnalysisRecoveryService
from legal_workbench.domain.entities import (
    AgentRun,
    AgentRunAttempt,
    AuditEvent,
    FeishuMessage,
    OutboxEvent,
)
from legal_workbench.domain.enums import (
    AgentAttemptStatus,
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


class _AttemptRepo:
    def __init__(self, attempts: list[AgentRunAttempt]) -> None:
        self.attempts = attempts

    async def expire_current(
        self,
        *,
        run_id: UUID,
        attempt_number: int,
        finished_at: datetime,
    ) -> bool:
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
    ) -> None:
        self.feishu = _FeishuRepo(messages, queued)
        self.agent_runs = _RunRepo(stale)
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
                if run.status in {AgentRunStatus.PREPARING, AgentRunStatus.RUNNING}
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
