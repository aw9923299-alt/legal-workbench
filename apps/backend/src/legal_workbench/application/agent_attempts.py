from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from legal_workbench.application.ports import AgentRunAttemptRepository
from legal_workbench.domain.entities import AgentAttemptLease, AgentRunAttempt
from legal_workbench.domain.enums import AgentAttemptStatus


class AgentAttemptService:
    """Apply fencing through an Attempt repository inside the caller's transaction."""

    def __init__(
        self,
        repository: AgentRunAttemptRepository,
        *,
        lease_seconds: int,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._lease_seconds = lease_seconds
        self._now = now or (lambda: datetime.now(UTC))

    async def claim(
        self,
        *,
        run_id: UUID,
        attempt_number: int,
        worker_id: str,
    ) -> AgentAttemptLease:
        claimed_at = self._now()
        attempt = AgentRunAttempt.start(
            run_id=run_id,
            attempt_number=attempt_number,
            lease_token=uuid4(),
            worker_id=worker_id,
            lease_expires_at=claimed_at + timedelta(seconds=self._lease_seconds),
            now=claimed_at,
        )
        await self._repository.add(attempt)
        return attempt.lease

    async def heartbeat(self, lease: AgentAttemptLease) -> datetime:
        heartbeat_at = self._now()
        lease_expires_at = heartbeat_at + timedelta(seconds=self._lease_seconds)
        await self._repository.heartbeat(
            lease,
            heartbeat_at=heartbeat_at,
            lease_expires_at=lease_expires_at,
        )
        return lease_expires_at

    async def complete(self, lease: AgentAttemptLease) -> datetime:
        finished_at = self._now()
        await self._repository.complete(lease, finished_at=finished_at)
        return finished_at

    async def fail(
        self,
        lease: AgentAttemptLease,
        *,
        status: AgentAttemptStatus,
        failure_code: str,
        failure_message: str,
    ) -> datetime:
        finished_at = self._now()
        await self._repository.fail(
            lease,
            status=status,
            failure_code=failure_code,
            failure_message=failure_message,
            finished_at=finished_at,
        )
        return finished_at

    async def expire_current(
        self,
        *,
        run_id: UUID,
        attempt_number: int,
    ) -> bool:
        return await self._repository.expire_current(
            run_id=run_id,
            attempt_number=attempt_number,
            finished_at=self._now(),
        )
