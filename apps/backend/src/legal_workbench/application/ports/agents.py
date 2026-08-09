from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from legal_workbench.domain.agents import (
    AgentAttemptLease,
    AgentDefinition,
    AgentExecutionPlan,
    AgentPlanStep,
    AgentRun,
    AgentRunAttempt,
    AgentRunSource,
    AgentRunStatusChange,
    CandidateRevision,
    ContextSnapshot,
    DraftArtifact,
)
from legal_workbench.domain.candidates import (
    MessageCandidate,
)
from legal_workbench.domain.enums import (
    AgentAttemptStatus,
    AgentRunStatus,
    CandidateMatterRelation,
    CandidateStatus,
)

__all__ = [
    "AgentDefinitionRepository",
    "AgentExecutionPlanRepository",
    "AgentRunAttemptRepository",
    "AgentRunRepository",
    "AgentRunSourceRepository",
    "ContextSnapshotRepository",
    "DraftArtifactRepository",
    "MessageCandidateRepository",
]


class ContextSnapshotRepository(Protocol):
    async def add(self, snapshot: ContextSnapshot) -> None: ...
    async def get(self, snapshot_id: UUID) -> ContextSnapshot | None: ...
    async def find_by_source_hash(
        self, *, source_type: str, source_id: str, content_hash: str
    ) -> ContextSnapshot | None: ...


class MessageCandidateRepository(Protocol):
    async def add(self, candidate: MessageCandidate) -> None: ...
    async def get(self, candidate_id: UUID) -> MessageCandidate | None: ...
    async def get_for_update(self, candidate_id: UUID) -> MessageCandidate | None: ...
    async def save(self, candidate: MessageCandidate) -> None: ...
    async def list(
        self, *, status: CandidateStatus | None, limit: int
    ) -> Sequence[MessageCandidate]: ...
    async def link_to_matter(
        self,
        *,
        candidate_id: UUID,
        matter_id: UUID,
        relation_type: CandidateMatterRelation,
        confirmed_by: str,
    ) -> None: ...
    async def get_active_for_message(self, message_id: UUID) -> MessageCandidate | None: ...
    async def append_revision(self, revision: CandidateRevision) -> None: ...
    async def list_revisions(self, candidate_id: UUID) -> Sequence[CandidateRevision]: ...


class AgentDefinitionRepository(Protocol):
    async def add(self, definition: AgentDefinition) -> None: ...
    async def get(self, definition_id: UUID) -> AgentDefinition | None: ...
    async def get_active(self, key: str) -> AgentDefinition | None: ...


class AgentExecutionPlanRepository(Protocol):
    async def add(self, plan: AgentExecutionPlan) -> None: ...
    async def get(self, plan_id: UUID) -> AgentExecutionPlan | None: ...
    async def get_for_update(self, plan_id: UUID) -> AgentExecutionPlan | None: ...
    async def get_by_idempotency_key(self, key: str) -> AgentExecutionPlan | None: ...
    async def list_by_matter(
        self, matter_id: UUID, *, limit: int = 50
    ) -> Sequence[AgentExecutionPlan]: ...
    async def get_step_for_update(self, plan_id: UUID, step_id: str) -> AgentPlanStep | None: ...
    async def save(self, plan: AgentExecutionPlan) -> None: ...
    async def save_step(self, step: AgentPlanStep) -> None: ...


class AgentRunRepository(Protocol):
    async def add(self, run: AgentRun) -> None: ...
    async def get(self, run_id: UUID) -> AgentRun | None: ...
    async def get_for_update(self, run_id: UUID) -> AgentRun | None: ...
    async def save(self, run: AgentRun) -> None: ...
    async def list(self, *, status: AgentRunStatus | None, limit: int) -> Sequence[AgentRun]: ...
    async def list_by_message(self, message_id: UUID) -> Sequence[AgentRun]: ...
    async def list_by_plan(self, plan_id: UUID) -> Sequence[AgentRun]: ...
    async def list_children(self, parent_run_id: UUID) -> Sequence[AgentRun]: ...
    async def list_status_events(self, run_id: UUID) -> Sequence[AgentRunStatusChange]: ...
    async def list_stale(
        self,
        *,
        statuses: Sequence[AgentRunStatus],
        older_than: datetime,
        limit: int,
    ) -> Sequence[AgentRun]: ...


class AgentRunAttemptRepository(Protocol):
    async def add(self, attempt: AgentRunAttempt) -> None: ...
    async def heartbeat(
        self,
        lease: AgentAttemptLease,
        *,
        heartbeat_at: datetime,
        lease_expires_at: datetime,
    ) -> None: ...
    async def complete(self, lease: AgentAttemptLease, *, finished_at: datetime) -> None: ...
    async def fail(
        self,
        lease: AgentAttemptLease,
        *,
        status: AgentAttemptStatus,
        failure_code: str,
        failure_message: str,
        finished_at: datetime,
    ) -> None: ...
    async def expire_current(
        self,
        *,
        run_id: UUID,
        attempt_number: int,
        finished_at: datetime,
    ) -> bool: ...
    async def list_by_run(self, run_id: UUID) -> Sequence[AgentRunAttempt]: ...


class AgentRunSourceRepository(Protocol):
    async def add_many(self, sources: Sequence[AgentRunSource]) -> None: ...
    async def list_by_run(self, run_id: UUID) -> Sequence[AgentRunSource]: ...


class DraftArtifactRepository(Protocol):
    async def add(self, artifact: DraftArtifact) -> None: ...
