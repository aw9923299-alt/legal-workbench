from __future__ import annotations

from collections.abc import AsyncIterator
from types import TracebackType
from typing import Protocol
from uuid import UUID

from legal_workbench.application.ports.agents import (
    AgentDefinitionRepository,
    AgentExecutionPlanRepository,
    AgentRunAttemptRepository,
    AgentRunRepository,
    AgentRunSourceRepository,
    ContextSnapshotRepository,
    DraftArtifactRepository,
    MessageCandidateRepository,
)
from legal_workbench.application.ports.documents import (
    AttachmentStorageQuotaRepository,
    DocumentRepository,
    KnowledgeRepository,
)
from legal_workbench.application.ports.evaluations import (
    EvaluationRepository,
)
from legal_workbench.application.ports.feishu import (
    FeishuPersonalSyncRepository,
    FeishuRepository,
    FeishuUserAuthorizationRepository,
)
from legal_workbench.application.ports.matters import (
    DeadlineRepository,
    DependencyRepository,
    LegalMatterRepository,
    MatterUpdateProposalRepository,
    PriorityConfirmationRepository,
    WorkItemRepository,
)
from legal_workbench.application.ports.reviews import (
    CommunicationRepository,
    ReviewPackageRepository,
    ReviewRecordRepository,
)
from legal_workbench.application.ports.setup import (
    SetupRepository,
)
from legal_workbench.domain.audit import (
    AuditEvent,
    IdempotencyRecord,
    OutboxEvent,
)

__all__ = [
    "AgentRuntime",
    "AuditEventRepository",
    "EventPublisher",
    "IdempotencyRepository",
    "OutboxEventRepository",
    "UnitOfWork",
    "UnitOfWorkFactory",
]


class AuditEventRepository(Protocol):
    async def add(self, event: AuditEvent) -> None: ...


class OutboxEventRepository(Protocol):
    async def add(self, event: OutboxEvent) -> None: ...
    async def exists_pending(self, *, event_type: str, aggregate_id: UUID) -> bool: ...


class IdempotencyRepository(Protocol):
    async def get(self, *, operation: str, key: str) -> IdempotencyRecord | None: ...
    async def add(self, record: IdempotencyRecord) -> None: ...


class UnitOfWork(Protocol):
    context_snapshots: ContextSnapshotRepository
    candidates: MessageCandidateRepository
    agent_definitions: AgentDefinitionRepository
    agent_execution_plans: AgentExecutionPlanRepository
    agent_runs: AgentRunRepository
    agent_run_attempts: AgentRunAttemptRepository
    agent_run_sources: AgentRunSourceRepository
    draft_artifacts: DraftArtifactRepository
    matters: LegalMatterRepository
    matter_update_proposals: MatterUpdateProposalRepository
    work_items: WorkItemRepository
    priority_confirmations: PriorityConfirmationRepository
    deadlines: DeadlineRepository
    dependencies: DependencyRepository
    review_packages: ReviewPackageRepository
    review_records: ReviewRecordRepository
    communications: CommunicationRepository
    feishu: FeishuRepository
    feishu_user_authorizations: FeishuUserAuthorizationRepository
    feishu_personal_sync: FeishuPersonalSyncRepository
    documents: DocumentRepository
    knowledge: KnowledgeRepository
    storage_quota: AttachmentStorageQuotaRepository
    evaluations: EvaluationRepository
    setup: SetupRepository
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
