from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.commands import (
    AddWorkItemCommand,
    ConfirmCandidateCreateMatterCommand,
    CreateCandidateCommand,
    InitialWorkItemInput,
    ResolveCandidateCommand,
)
from legal_workbench.application.handlers import (
    AddWorkItemHandler,
    ConfirmCandidateCreateMatterHandler,
    CreateCandidateHandler,
    ResolveCandidateHandler,
)
from legal_workbench.domain.entities import (
    AuditEvent,
    ContextSnapshot,
    IdempotencyRecord,
    LegalMatter,
    MessageCandidate,
    OutboxEvent,
    WorkItem,
)
from legal_workbench.domain.enums import (
    BusinessImpact,
    CandidateMatterRelation,
    CandidateResolutionAction,
    CandidateStatus,
    Confidentiality,
    LegalRelevance,
    LegalRisk,
    MatterCategory,
    MessageRole,
    Priority,
    PrioritySource,
    RecommendedAction,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityVersionConflictError,
    IdempotencyConflictError,
)


class FakeContextSnapshots:
    def __init__(self, store: dict[UUID, ContextSnapshot]) -> None:
        self.store = store

    async def add(self, snapshot: ContextSnapshot) -> None:
        self.store[snapshot.id] = snapshot

    async def find_by_source_hash(
        self, *, source_type: str, source_id: str, content_hash: str
    ) -> ContextSnapshot | None:
        return next(
            (
                snapshot
                for snapshot in self.store.values()
                if snapshot.source_type == source_type
                and snapshot.source_id == source_id
                and snapshot.content_hash == content_hash
            ),
            None,
        )


class FakeCandidates:
    def __init__(
        self,
        store: dict[UUID, MessageCandidate],
        links: list[tuple[UUID, UUID, CandidateMatterRelation, str]],
    ) -> None:
        self.store = store
        self.links = links

    async def add(self, candidate: MessageCandidate) -> None:
        self.store[candidate.id] = candidate

    async def get(self, candidate_id: UUID) -> MessageCandidate | None:
        return self.store.get(candidate_id)

    async def get_for_update(self, candidate_id: UUID) -> MessageCandidate | None:
        return self.store.get(candidate_id)

    async def save(self, candidate: MessageCandidate) -> None:
        self.store[candidate.id] = candidate

    async def list(
        self, *, status: CandidateStatus | None, limit: int
    ) -> Sequence[MessageCandidate]:
        values = list(self.store.values())
        if status is not None:
            values = [item for item in values if item.status == status]
        return values[:limit]

    async def link_to_matter(
        self,
        *,
        candidate_id: UUID,
        matter_id: UUID,
        relation_type: CandidateMatterRelation,
        confirmed_by: str,
    ) -> None:
        self.links.append((candidate_id, matter_id, relation_type, confirmed_by))


class FakeMatters:
    def __init__(self, store: dict[UUID, LegalMatter]) -> None:
        self.store = store

    async def add(self, matter: LegalMatter) -> None:
        self.store[matter.id] = matter

    async def get(self, matter_id: UUID) -> LegalMatter | None:
        return self.store.get(matter_id)

    async def get_for_update(self, matter_id: UUID) -> LegalMatter | None:
        return self.store.get(matter_id)

    async def list(self, *, owner_id: str | None, limit: int) -> Sequence[LegalMatter]:
        values = list(self.store.values())
        if owner_id is not None:
            values = [item for item in values if item.owner_id == owner_id]
        return values[:limit]


class FakeWorkItems:
    def __init__(self, store: dict[UUID, WorkItem]) -> None:
        self.store = store

    async def add(self, work_item: WorkItem) -> None:
        self.store[work_item.id] = work_item

    async def add_many(self, work_items: Sequence[WorkItem]) -> None:
        self.store.update({item.id: item for item in work_items})

    async def get(self, work_item_id: UUID) -> WorkItem | None:
        return self.store.get(work_item_id)

    async def list_by_matter(self, matter_id: UUID) -> Sequence[WorkItem]:
        return sorted(
            (item for item in self.store.values() if item.matter_id == matter_id),
            key=lambda item: item.sequence_order,
        )


class FakeAuditEvents:
    def __init__(self, store: list[AuditEvent]) -> None:
        self.store = store

    async def add(self, event: AuditEvent) -> None:
        self.store.append(event)


class FakeOutboxEvents:
    def __init__(self, store: list[OutboxEvent]) -> None:
        self.store = store

    async def add(self, event: OutboxEvent) -> None:
        self.store.append(event)


class FakeIdempotency:
    def __init__(self, store: dict[tuple[str, str], IdempotencyRecord]) -> None:
        self.store = store

    async def get(self, *, operation: str, key: str) -> IdempotencyRecord | None:
        return self.store.get((operation, key))

    async def add(self, record: IdempotencyRecord) -> None:
        self.store[(record.operation, record.idempotency_key)] = record


class FakeUnitOfWork:
    def __init__(self, state: FakeState) -> None:
        self.context_snapshots = FakeContextSnapshots(state.snapshots)
        self.candidates = FakeCandidates(state.candidates, state.links)
        self.matters = FakeMatters(state.matters)
        self.work_items = FakeWorkItems(state.work_items)
        self.audit_events = FakeAuditEvents(state.audit_events)
        self.outbox_events = FakeOutboxEvents(state.outbox_events)
        self.idempotency = FakeIdempotency(state.idempotency)
        self.committed = False

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        return None


class FakeState:
    def __init__(self) -> None:
        self.snapshots: dict[UUID, ContextSnapshot] = {}
        self.candidates: dict[UUID, MessageCandidate] = {}
        self.matters: dict[UUID, LegalMatter] = {}
        self.work_items: dict[UUID, WorkItem] = {}
        self.links: list[tuple[UUID, UUID, CandidateMatterRelation, str]] = []
        self.audit_events: list[AuditEvent] = []
        self.outbox_events: list[OutboxEvent] = []
        self.idempotency: dict[tuple[str, str], IdempotencyRecord] = {}

    def factory(self) -> FakeUnitOfWork:
        return FakeUnitOfWork(self)


def make_candidate(*, version: int = 1) -> MessageCandidate:
    return MessageCandidate(
        id=uuid4(),
        context_snapshot_id=uuid4(),
        status=CandidateStatus.PENDING_CONFIRMATION,
        legal_relevance=LegalRelevance.RELEVANT,
        message_role=MessageRole.NEW_REQUEST,
        recommended_action=RecommendedAction.CREATE_MATTER,
        confidence=0.92,
        title_proposal="审核品牌合作协议",
        version=version,
    )


def make_command(candidate: MessageCandidate) -> ConfirmCandidateCreateMatterCommand:
    return ConfirmCandidateCreateMatterCommand(
        candidate_id=candidate.id,
        candidate_version=candidate.version,
        actor_id="legal-user-1",
        correlation_id="corr-1",
        idempotency_key="idem-1",
        title="审核品牌合作协议",
        primary_category=MatterCategory.CONTRACT,
        secondary_categories=[MatterCategory.COPY_REVIEW],
        owner_id="legal-user-1",
        requester_ids=["business-user-1"],
        legal_risk=LegalRisk.MEDIUM,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.CONFIDENTIAL,
        summary="业务希望今日完成合作协议审核。",
        objective="形成修改意见并回复业务。",
        initial_work_items=[
            InitialWorkItemInput(
                title="核查合同主体和版本",
                owner_id="legal-user-1",
                priority=Priority.HIGH,
                priority_source=PrioritySource.LEGAL_CONFIRMED,
                next_action="确认签约主体及最终版本。",
                priority_reasons=["今日需要完成审核"],
                estimated_minutes=20,
            ),
            InitialWorkItemInput(
                title="审查核心权利义务",
                owner_id="legal-user-1",
                priority=Priority.HIGH,
                priority_source=PrioritySource.AGENT_SUGGESTED,
                next_action="调用合同Agent并形成风险清单。",
                priority_reasons=["影响项目上线"],
                ai_suggested_priority=Priority.HIGH,
                estimated_minutes=45,
            ),
        ],
    )


def make_create_candidate_command(
    *, idempotency_key: str = "candidate-idem-1", title: str = "审核品牌合作协议"
) -> CreateCandidateCommand:
    return CreateCandidateCommand(
        source_type="feishu_group_message",
        source_ids=["chat-1"],
        message_ids=["message-1"],
        file_ids=["file-1"],
        relevant_matter_ids=[],
        participant_ids=["business-user-1", "legal-user-1"],
        permission_snapshot={"chatId": "chat-1", "visibleTo": ["legal-user-1"]},
        generated_at=datetime(2026, 8, 1, 9, 30, tzinfo=UTC),
        content_hash="a" * 64,
        actor_id="manager-agent",
        correlation_id="corr-candidate-1",
        idempotency_key=idempotency_key,
        status=CandidateStatus.PENDING_CONFIRMATION,
        legal_relevance=LegalRelevance.RELEVANT,
        message_role=MessageRole.NEW_REQUEST,
        recommended_action=RecommendedAction.CREATE_MATTER,
        confidence=0.91,
        title_proposal=title,
        category_proposals=[{"category": "contract", "confidence": 0.88}],
        evidence_refs=["feishu:message-1"],
    )


@pytest.mark.asyncio
async def test_create_candidate_is_audited_outboxed_and_idempotent() -> None:
    state = FakeState()
    handler = CreateCandidateHandler(state.factory)
    command = make_create_candidate_command()

    first = await handler.execute(command)
    second = await handler.execute(command)

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert second.candidate_id == first.candidate_id
    assert len(state.snapshots) == 1
    assert len(state.candidates) == 1
    assert state.audit_events[0].event_type == "message_candidate_created"
    assert state.outbox_events[0].event_type == "MessageCandidateCreated"
    assert state.outbox_events[0].correlation_id == "corr-candidate-1"


@pytest.mark.asyncio
async def test_different_business_requests_reuse_identical_context_snapshot() -> None:
    state = FakeState()
    handler = CreateCandidateHandler(state.factory)

    first = await handler.execute(make_create_candidate_command(idempotency_key="first"))
    second = await handler.execute(make_create_candidate_command(idempotency_key="second"))

    assert first.candidate_id != second.candidate_id
    assert len(state.snapshots) == 1
    assert len(state.candidates) == 2
    assert {
        candidate.context_snapshot_id for candidate in state.candidates.values()
    } == set(state.snapshots)


@pytest.mark.asyncio
async def test_idempotency_key_cannot_be_reused_for_different_candidate_request() -> None:
    state = FakeState()
    handler = CreateCandidateHandler(state.factory)

    await handler.execute(make_create_candidate_command())

    with pytest.raises(IdempotencyConflictError):
        await handler.execute(make_create_candidate_command(title="审核另一份协议"))


@pytest.mark.asyncio
async def test_new_candidate_rejects_non_pending_status() -> None:
    state = FakeState()
    command = replace(
        make_create_candidate_command(),
        status=CandidateStatus.CONFIRMED,
        idempotency_key="candidate-invalid-status",
    )

    with pytest.raises(DomainValidationError):
        await CreateCandidateHandler(state.factory).execute(command)


@pytest.mark.asyncio
async def test_confirm_candidate_requires_at_least_one_initial_work_item() -> None:
    state = FakeState()
    candidate = make_candidate()
    state.candidates[candidate.id] = candidate
    command = replace(make_command(candidate), initial_work_items=[])

    with pytest.raises(DomainValidationError):
        await ConfirmCandidateCreateMatterHandler(state.factory).execute(command)


@pytest.mark.asyncio
async def test_confirm_candidate_creates_matter_and_work_items_atomically() -> None:
    state = FakeState()
    candidate = make_candidate()
    state.candidates[candidate.id] = candidate

    result = await ConfirmCandidateCreateMatterHandler(state.factory).execute(
        make_command(candidate)
    )

    assert result.idempotent_replay is False
    assert result.matter_id in state.matters
    assert len(result.work_item_ids) == 2
    assert all(item_id in state.work_items for item_id in result.work_item_ids)
    assert state.candidates[candidate.id].status == CandidateStatus.CONFIRMED
    assert state.links == [
        (candidate.id, result.matter_id, CandidateMatterRelation.CREATED, "legal-user-1")
    ]
    assert state.audit_events[0].event_type == "candidate_confirmed_matter_created"
    assert state.outbox_events[0].event_type == "LegalMatterCreated"
    assert state.outbox_events[0].correlation_id == "corr-1"


@pytest.mark.asyncio
async def test_candidate_can_be_linked_to_existing_matter_idempotently() -> None:
    state = FakeState()
    candidate = make_candidate()
    matter = LegalMatter.create(
        title="既有事项",
        primary_category=MatterCategory.CONTRACT,
        owner_id="legal-user-1",
        legal_risk=LegalRisk.MEDIUM,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.INTERNAL,
        secondary_categories=[],
        requester_ids=[],
        summary=None,
        objective=None,
    )
    state.candidates[candidate.id] = candidate
    state.matters[matter.id] = matter
    command = ResolveCandidateCommand(
        candidate_id=candidate.id,
        candidate_version=candidate.version,
        action=CandidateResolutionAction.LINK_EXISTING,
        matter_id=matter.id,
        actor_id="legal-user-1",
        correlation_id="corr-resolve",
        idempotency_key="idem-resolve",
    )

    first = await ResolveCandidateHandler(state.factory).execute(command)
    replay = await ResolveCandidateHandler(state.factory).execute(command)

    assert first.status == CandidateStatus.LINKED
    assert replay.idempotent_replay is True
    assert state.links == [
        (candidate.id, matter.id, CandidateMatterRelation.LINKED, "legal-user-1")
    ]


@pytest.mark.asyncio
async def test_candidate_update_requires_a_matter_update_proposal() -> None:
    state = FakeState()
    candidate = make_candidate()
    matter = LegalMatter.create(
        title="既有事项",
        primary_category=MatterCategory.CONTRACT,
        owner_id="legal-user-1",
        legal_risk=LegalRisk.MEDIUM,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.INTERNAL,
        secondary_categories=[],
        requester_ids=[],
        summary=None,
        objective=None,
    )
    state.candidates[candidate.id] = candidate
    state.matters[matter.id] = matter

    with pytest.raises(DomainValidationError):
        await ResolveCandidateHandler(state.factory).execute(
            ResolveCandidateCommand(
                candidate_id=candidate.id,
                candidate_version=candidate.version,
                action=CandidateResolutionAction.UPDATE_EXISTING,
                matter_id=matter.id,
                actor_id="legal-user-1",
                correlation_id="corr-direct-update",
                idempotency_key="idem-direct-update",
            )
        )

    assert candidate.status == CandidateStatus.PENDING_CONFIRMATION
    assert matter.version == 1


@pytest.mark.asyncio
async def test_candidate_can_be_marked_information_only_without_matter() -> None:
    state = FakeState()
    candidate = make_candidate()
    state.candidates[candidate.id] = candidate

    result = await ResolveCandidateHandler(state.factory).execute(
        ResolveCandidateCommand(
            candidate_id=candidate.id,
            candidate_version=candidate.version,
            action=CandidateResolutionAction.INFORMATION_ONLY,
            matter_id=None,
            actor_id="legal-user-1",
            correlation_id="corr-info",
            idempotency_key="idem-info",
        )
    )

    assert result.status == CandidateStatus.INFORMATION_ONLY
    assert state.links == []


@pytest.mark.asyncio
async def test_same_idempotency_key_returns_original_result() -> None:
    state = FakeState()
    candidate = make_candidate()
    state.candidates[candidate.id] = candidate
    handler = ConfirmCandidateCreateMatterHandler(state.factory)
    command = make_command(candidate)

    first = await handler.execute(command)
    second = await handler.execute(command)

    assert second.idempotent_replay is True
    assert second.matter_id == first.matter_id
    assert second.work_item_ids == first.work_item_ids
    assert len(state.matters) == 1
    assert len(state.work_items) == 2


@pytest.mark.asyncio
async def test_stale_candidate_version_is_rejected() -> None:
    state = FakeState()
    candidate = make_candidate(version=2)
    state.candidates[candidate.id] = candidate
    command = make_command(candidate)
    stale_command = replace(command, candidate_version=1)

    with pytest.raises(EntityVersionConflictError):
        await ConfirmCandidateCreateMatterHandler(state.factory).execute(stale_command)


@pytest.mark.asyncio
async def test_add_work_item_is_idempotent() -> None:
    state = FakeState()
    matter = LegalMatter.create(
        title="主播解约事项",
        primary_category=MatterCategory.DISPUTE,
        secondary_categories=[MatterCategory.CONTRACT],
        owner_id="legal-user-1",
        legal_risk=LegalRisk.HIGH,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.CONFIDENTIAL,
        requester_ids=["hr-user-1"],
        summary=None,
        objective=None,
    )
    state.matters[matter.id] = matter
    command = AddWorkItemCommand(
        matter_id=matter.id,
        actor_id="legal-user-1",
        correlation_id="corr-2",
        idempotency_key="work-item-idem-1",
        title="核查解除条款",
        owner_id="legal-user-1",
        priority=Priority.HIGH,
        priority_source=PrioritySource.LEGAL_CONFIRMED,
        next_action="读取最终签署版合同。",
        priority_reasons=["存在对外争议风险"],
    )
    handler = AddWorkItemHandler(state.factory)

    first = await handler.execute(command)
    second = await handler.execute(command)

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert second.work_item_id == first.work_item_id
    assert len(state.work_items) == 1
