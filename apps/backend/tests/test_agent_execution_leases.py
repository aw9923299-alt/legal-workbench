from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.agent_attempts import AgentExecutionLeaseService
from legal_workbench.domain.entities import AgentAttemptLease, AgentRun, AgentRunAttempt
from legal_workbench.domain.enums import AgentAttemptStatus, AgentRunStatus
from legal_workbench.domain.errors import StaleAgentAttemptError

NOW = datetime(2026, 8, 9, 9, 0, tzinfo=UTC)


class _AttemptRepository:
    def __init__(self) -> None:
        self.values: dict[tuple[UUID, int], AgentRunAttempt] = {}

    async def add(self, attempt: AgentRunAttempt) -> None:
        self.values[(attempt.run_id, attempt.attempt_number)] = attempt

    def _current(self, lease: AgentAttemptLease) -> AgentRunAttempt:
        return self.values[(lease.run_id, lease.attempt_number)]

    async def heartbeat(
        self,
        lease: AgentAttemptLease,
        *,
        heartbeat_at: datetime,
        lease_expires_at: datetime,
    ) -> None:
        self._current(lease).heartbeat(
            lease,
            heartbeat_at=heartbeat_at,
            lease_expires_at=lease_expires_at,
        )

    async def complete(self, lease: AgentAttemptLease, *, finished_at: datetime) -> None:
        self._current(lease).complete(lease, now=finished_at)

    async def fail(
        self,
        lease: AgentAttemptLease,
        *,
        status: AgentAttemptStatus,
        failure_code: str,
        failure_message: str,
        finished_at: datetime,
    ) -> None:
        self._current(lease).fail(
            lease,
            status=status,
            failure_code=failure_code,
            failure_message=failure_message,
            now=finished_at,
        )

    async def expire_current(
        self,
        *,
        run_id: UUID,
        attempt_number: int,
        finished_at: datetime,
    ) -> bool:
        attempt = self.values[(run_id, attempt_number)]
        if attempt.status != AgentAttemptStatus.RUNNING:
            return False
        attempt.expire(now=finished_at)
        return True

    async def list_by_run(self, run_id: UUID) -> list[AgentRunAttempt]:
        return [value for key, value in self.values.items() if key[0] == run_id]


def _run() -> AgentRun:
    return AgentRun(
        id=uuid4(),
        agent_definition_id=uuid4(),
        context_snapshot_id=uuid4(),
        status=AgentRunStatus.QUEUED,
        objective="Lease lifecycle fixture.",
        prompt_snapshot="Non-sensitive test prompt.",
        working_directory="/isolated/fixture",
        attempt_number=1,
        max_attempts=2,
        correlation_id="lease-fixture",
        created_by="test",
    )


@pytest.mark.asyncio
async def test_execution_lease_drives_normal_run_lifecycle_and_heartbeat() -> None:
    repository = _AttemptRepository()
    run = _run()
    service = AgentExecutionLeaseService(
        repository,
        lease_seconds=60,
        now=lambda: NOW,
    )

    lease = await service.start(run, worker_id="legal-worker")

    assert run.status == AgentRunStatus.RUNNING
    assert run.worker_id == "legal-worker"
    assert run.lease_expires_at == NOW + timedelta(seconds=60)
    assert [event.to_status for event in run.pending_status_changes] == [
        AgentRunStatus.PREPARING,
        AgentRunStatus.RUNNING,
    ]

    await service.heartbeat(run, lease)
    await service.complete(run, lease)
    run.transition_to(AgentRunStatus.VALIDATING, now=NOW)
    run.transition_to(AgentRunStatus.COMPLETED, now=NOW)

    assert run.status == AgentRunStatus.COMPLETED
    assert run.lease_expires_at is None
    assert repository.values[(run.id, 1)].status == AgentAttemptStatus.COMPLETED


@pytest.mark.asyncio
async def test_execution_lease_rejects_late_owner_before_result_can_commit() -> None:
    repository = _AttemptRepository()
    run = _run()
    service = AgentExecutionLeaseService(
        repository,
        lease_seconds=60,
        now=lambda: NOW,
    )
    stale = await service.start(run, worker_id="worker-old")
    assert await service.expire_current(run) is True
    run.failure_code = "AGENT_LEASE_EXPIRED"
    run.failure_message = "Expired fixture lease."
    run.transition_to(AgentRunStatus.FAILED, now=NOW)
    run.attempt_number += 1
    run.transition_to(AgentRunStatus.QUEUED, now=NOW)
    current = await service.start(run, worker_id="worker-current")

    with pytest.raises(StaleAgentAttemptError):
        await service.complete(run, stale)

    assert repository.values[(run.id, 1)].status == AgentAttemptStatus.EXPIRED
    assert repository.values[(run.id, 2)].status == AgentAttemptStatus.RUNNING
    await service.complete(run, current)


@pytest.mark.asyncio
async def test_execution_lease_cannot_be_revived_after_natural_expiry() -> None:
    repository = _AttemptRepository()
    run = _run()
    current_time = NOW
    service = AgentExecutionLeaseService(
        repository,
        lease_seconds=60,
        now=lambda: current_time,
    )
    lease = await service.start(run, worker_id="worker-expired")
    current_time = NOW + timedelta(seconds=61)

    with pytest.raises(StaleAgentAttemptError):
        await service.heartbeat(run, lease)
    with pytest.raises(StaleAgentAttemptError):
        await service.complete(run, lease)

    assert repository.values[(run.id, 1)].status == AgentAttemptStatus.RUNNING
    assert repository.values[(run.id, 1)].lease_expires_at == NOW + timedelta(seconds=60)
