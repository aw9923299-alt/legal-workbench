from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from types import TracebackType
from typing import Protocol
from uuid import UUID

from legal_workbench.domain.entities import (
    AuditEvent,
    ContextSnapshot,
    IdempotencyRecord,
    LegalMatter,
    MessageCandidate,
    OutboxEvent,
    WorkItem,
)
from legal_workbench.domain.enums import CandidateMatterRelation, CandidateStatus


class ContextSnapshotRepository(Protocol):
    async def add(self, snapshot: ContextSnapshot) -> None: ...


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


class LegalMatterRepository(Protocol):
    async def add(self, matter: LegalMatter) -> None: ...

    async def get(self, matter_id: UUID) -> LegalMatter | None: ...

    async def get_for_update(self, matter_id: UUID) -> LegalMatter | None: ...

    async def list(self, *, owner_id: str | None, limit: int) -> Sequence[LegalMatter]: ...


class WorkItemRepository(Protocol):
    async def add(self, work_item: WorkItem) -> None: ...

    async def add_many(self, work_items: Sequence[WorkItem]) -> None: ...

    async def get(self, work_item_id: UUID) -> WorkItem | None: ...

    async def list_by_matter(self, matter_id: UUID) -> Sequence[WorkItem]: ...


class AuditEventRepository(Protocol):
    async def add(self, event: AuditEvent) -> None: ...


class OutboxEventRepository(Protocol):
    async def add(self, event: OutboxEvent) -> None: ...


class IdempotencyRepository(Protocol):
    async def get(self, *, operation: str, key: str) -> IdempotencyRecord | None: ...

    async def add(self, record: IdempotencyRecord) -> None: ...


class UnitOfWork(Protocol):
    context_snapshots: ContextSnapshotRepository
    candidates: MessageCandidateRepository
    matters: LegalMatterRepository
    work_items: WorkItemRepository
    audit_events: AuditEventRepository
    outbox_events: OutboxEventRepository
    idempotency: IdempotencyRepository

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...

    async def lock_idempotency(self, *, operation: str, key: str) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


class AgentRuntime(Protocol):
    async def execute(self, run_id: str) -> None: ...


class EventPublisher(Protocol):
    async def publish_pending(self) -> AsyncIterator[str]: ...
