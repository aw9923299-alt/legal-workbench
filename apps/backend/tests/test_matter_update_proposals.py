from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.matter_updates import (
    CreateMatterUpdateProposalCommand,
    CreateMatterUpdateProposalHandler,
    ReviewMatterUpdateProposalCommand,
    ReviewMatterUpdateProposalHandler,
)
from legal_workbench.domain.entities import (
    AuditEvent,
    Deadline,
    IdempotencyRecord,
    LegalMatter,
    MatterUpdateProposal,
    MessageCandidate,
    OutboxEvent,
    ProposalFieldDecision,
    WorkItem,
)
from legal_workbench.domain.enums import (
    BusinessImpact,
    CandidateMatterRelation,
    CandidateStatus,
    Confidentiality,
    LegalRelevance,
    LegalRisk,
    MatterCategory,
    MatterUpdateProposalStatus,
    MessageRole,
    Priority,
    ProposalFieldDecisionType,
    RecommendedAction,
)
from legal_workbench.domain.errors import EntityVersionConflictError


class ObjectRepository:
    def __init__(self, store: dict[UUID, object]) -> None:
        self.store = store

    async def add(self, value: object) -> None:
        self.store[value.id] = value  # type: ignore[attr-defined]

    async def get(self, value_id: UUID) -> object | None:
        return self.store.get(value_id)

    async def get_for_update(self, value_id: UUID) -> object | None:
        return self.store.get(value_id)

    async def save(self, value: object) -> None:
        self.store[value.id] = value  # type: ignore[attr-defined]


class CandidateRepository(ObjectRepository):
    def __init__(
        self,
        store: dict[UUID, object],
        links: list[tuple[UUID, UUID, CandidateMatterRelation, str]],
    ) -> None:
        super().__init__(store)
        self.links = links

    async def link_to_matter(
        self,
        *,
        candidate_id: UUID,
        matter_id: UUID,
        relation_type: CandidateMatterRelation,
        confirmed_by: str,
    ) -> None:
        self.links.append((candidate_id, matter_id, relation_type, confirmed_by))


class WorkItemRepository(ObjectRepository):
    async def add_many(self, values: Sequence[WorkItem]) -> None:
        self.store.update({value.id: value for value in values})

    async def list_by_matter(self, matter_id: UUID) -> Sequence[WorkItem]:
        return [
            value
            for value in self.store.values()
            if isinstance(value, WorkItem) and value.matter_id == matter_id
        ]


class AppendRepository:
    def __init__(self, store: list[object]) -> None:
        self.store = store

    async def add(self, value: object) -> None:
        self.store.append(value)


class IdempotencyRepository:
    def __init__(self, store: dict[tuple[str, str], IdempotencyRecord]) -> None:
        self.store = store

    async def get(self, *, operation: str, key: str) -> IdempotencyRecord | None:
        return self.store.get((operation, key))

    async def add(self, value: IdempotencyRecord) -> None:
        self.store[(value.operation, value.idempotency_key)] = value


class FakeState:
    def __init__(self) -> None:
        self.candidates: dict[UUID, object] = {}
        self.matters: dict[UUID, object] = {}
        self.proposals: dict[UUID, object] = {}
        self.work_items: dict[UUID, object] = {}
        self.deadlines: list[object] = []
        self.audit_events: list[object] = []
        self.outbox_events: list[object] = []
        self.links: list[tuple[UUID, UUID, CandidateMatterRelation, str]] = []
        self.idempotency: dict[tuple[str, str], IdempotencyRecord] = {}

    def factory(self) -> FakeUnitOfWork:
        return FakeUnitOfWork(self)


class FakeUnitOfWork:
    def __init__(self, state: FakeState) -> None:
        self.candidates = CandidateRepository(state.candidates, state.links)
        self.matters = ObjectRepository(state.matters)
        self.matter_update_proposals = ObjectRepository(state.proposals)
        self.work_items = WorkItemRepository(state.work_items)
        self.deadlines = AppendRepository(state.deadlines)
        self.audit_events = AppendRepository(state.audit_events)
        self.outbox_events = AppendRepository(state.outbox_events)
        self.idempotency = IdempotencyRepository(state.idempotency)

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
        return None

    async def rollback(self) -> None:
        return None


def make_candidate_and_matter() -> tuple[MessageCandidate, LegalMatter]:
    candidate = MessageCandidate(
        id=uuid4(),
        context_snapshot_id=uuid4(),
        status=CandidateStatus.PENDING_CONFIRMATION,
        legal_relevance=LegalRelevance.RELEVANT,
        message_role=MessageRole.PROGRESS_UPDATE,
        recommended_action=RecommendedAction.UPDATE_MATTER,
        confidence=0.91,
        title_proposal="消息提取标题",
        category_proposals=[{"category": "dispute", "confidence": 0.82}],
        deadline_proposals=[{"dueAt": "2026-08-08T10:00:00+08:00", "confidence": 0.8}],
        analysis_payload={"suggestedNextAction": "核对补充材料"},
    )
    matter = LegalMatter.create(
        title="原事项标题",
        primary_category=MatterCategory.CONTRACT,
        owner_id="owner-original",
        legal_risk=LegalRisk.MEDIUM,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.INTERNAL,
        secondary_categories=[],
        requester_ids=[],
        summary=None,
        objective=None,
    )
    return candidate, matter


def proposed_changes(matter: LegalMatter) -> dict[str, dict[str, object]]:
    return {
        "title": {
            "currentValue": matter.title,
            "messageExtractedValue": "消息提取标题",
            "aiSuggestedValue": "AI 建议标题",
        },
        "owner": {
            "currentValue": matter.owner_id,
            "messageExtractedValue": None,
            "aiSuggestedValue": "owner-ai",
        },
        "priority": {
            "currentValue": matter.priority.value,
            "messageExtractedValue": "high",
            "aiSuggestedValue": "urgent",
        },
        "deadline": {
            "currentValue": None,
            "messageExtractedValue": "2026-08-08T10:00:00+08:00",
            "aiSuggestedValue": "2026-08-09T10:00:00+08:00",
        },
        "nextAction": {
            "currentValue": matter.next_action,
            "messageExtractedValue": "补材料",
            "aiSuggestedValue": "核对补充材料",
        },
        "newWorkItems": {
            "currentValue": [],
            "messageExtractedValue": [],
            "aiSuggestedValue": [
                {
                    "title": "核查补充材料",
                    "ownerId": "owner-original",
                    "priority": "high",
                    "nextAction": "逐项核对材料",
                }
            ],
        },
    }


async def create_proposal(
    state: FakeState, candidate: MessageCandidate, matter: LegalMatter
) -> MatterUpdateProposal:
    result = await CreateMatterUpdateProposalHandler(state.factory).execute(
        CreateMatterUpdateProposalCommand(
            candidate_id=candidate.id,
            candidate_version=candidate.version,
            matter_id=matter.id,
            proposed_changes=proposed_changes(matter),
            reason="消息包含事项进展和新期限。",
            actor_id="legal-user-1",
            correlation_id="corr-create-proposal",
            idempotency_key="idem-create-proposal",
        )
    )
    proposal = state.proposals[result.proposal_id]
    assert isinstance(proposal, MatterUpdateProposal)
    return proposal


@pytest.mark.asyncio
async def test_create_proposal_links_candidate_without_mutating_matter() -> None:
    state = FakeState()
    candidate, matter = make_candidate_and_matter()
    state.candidates[candidate.id] = candidate
    state.matters[matter.id] = matter

    proposal = await create_proposal(state, candidate, matter)

    assert proposal.status == MatterUpdateProposalStatus.PENDING
    assert matter.title == "原事项标题"
    assert matter.version == 1
    assert candidate.status == CandidateStatus.LINKED
    assert state.links == [
        (candidate.id, matter.id, CandidateMatterRelation.UPDATED, "legal-user-1")
    ]


@pytest.mark.asyncio
async def test_approval_rejects_stale_matter_version_and_keeps_proposal_pending() -> None:
    state = FakeState()
    candidate, matter = make_candidate_and_matter()
    state.candidates[candidate.id] = candidate
    state.matters[matter.id] = matter
    proposal = await create_proposal(state, candidate, matter)

    with pytest.raises(EntityVersionConflictError):
        await ReviewMatterUpdateProposalHandler(state.factory).execute(
            ReviewMatterUpdateProposalCommand(
                proposal_id=proposal.id,
                proposal_version=proposal.version,
                matter_version=proposal.base_matter_version + 1,
                decisions=[
                    ProposalFieldDecision(
                        field_name="title",
                        decision=ProposalFieldDecisionType.APPROVE,
                        final_value="法务最终标题",
                    )
                ],
                rejection_reason=None,
                actor_id="legal-reviewer",
                correlation_id="corr-stale",
                idempotency_key="idem-stale",
            )
        )

    assert proposal.status == MatterUpdateProposalStatus.PENDING
    assert matter.title == "原事项标题"


@pytest.mark.asyncio
async def test_partial_approval_applies_only_selected_fields_and_work_items() -> None:
    state = FakeState()
    candidate, matter = make_candidate_and_matter()
    state.candidates[candidate.id] = candidate
    state.matters[matter.id] = matter
    proposal = await create_proposal(state, candidate, matter)

    result = await ReviewMatterUpdateProposalHandler(state.factory).execute(
        ReviewMatterUpdateProposalCommand(
            proposal_id=proposal.id,
            proposal_version=proposal.version,
            matter_version=matter.version,
            decisions=[
                ProposalFieldDecision(
                    field_name="title",
                    decision=ProposalFieldDecisionType.APPROVE,
                    final_value="法务最终标题",
                ),
                ProposalFieldDecision(
                    field_name="owner",
                    decision=ProposalFieldDecisionType.REJECT,
                    final_value=None,
                ),
                ProposalFieldDecision(
                    field_name="priority",
                    decision=ProposalFieldDecisionType.REJECT,
                    final_value=None,
                ),
                ProposalFieldDecision(
                    field_name="deadline",
                    decision=ProposalFieldDecisionType.REJECT,
                    final_value=None,
                ),
                ProposalFieldDecision(
                    field_name="nextAction",
                    decision=ProposalFieldDecisionType.REJECT,
                    final_value=None,
                ),
                ProposalFieldDecision(
                    field_name="newWorkItems",
                    decision=ProposalFieldDecisionType.APPROVE,
                    final_value=[
                        {
                            "title": "人工确认的核查任务",
                            "ownerId": "legal-reviewer",
                            "priority": "high",
                            "nextAction": "核对原件",
                            "plannedCompleteAt": "2026-08-08T18:00:00+08:00",
                        }
                    ],
                ),
            ],
            rejection_reason=None,
            actor_id="legal-reviewer",
            correlation_id="corr-partial",
            idempotency_key="idem-partial",
        )
    )

    assert result.status == MatterUpdateProposalStatus.PARTIALLY_APPROVED
    assert matter.title == "法务最终标题"
    assert matter.owner_id == "owner-original"
    assert matter.version == 2
    work_items = list(state.work_items.values())
    assert len(work_items) == 1
    assert isinstance(work_items[0], WorkItem)
    assert work_items[0].priority == Priority.HIGH


@pytest.mark.asyncio
async def test_approved_deadline_creates_confirmed_deadline_and_updates_matter() -> None:
    state = FakeState()
    candidate, matter = make_candidate_and_matter()
    state.candidates[candidate.id] = candidate
    state.matters[matter.id] = matter
    proposal = await create_proposal(state, candidate, matter)

    await ReviewMatterUpdateProposalHandler(state.factory).execute(
        ReviewMatterUpdateProposalCommand(
            proposal_id=proposal.id,
            proposal_version=proposal.version,
            matter_version=matter.version,
            decisions=[
                ProposalFieldDecision(
                    field_name="deadline",
                    decision=ProposalFieldDecisionType.APPROVE,
                    final_value="2026-08-08T18:00:00+08:00",
                ),
                *[
                    ProposalFieldDecision(
                        field_name=field_name,
                        decision=ProposalFieldDecisionType.REJECT,
                        final_value=None,
                    )
                    for field_name in (
                        "title",
                        "owner",
                        "priority",
                        "nextAction",
                        "newWorkItems",
                    )
                ],
            ],
            rejection_reason=None,
            actor_id="legal-reviewer",
            correlation_id="corr-deadline",
            idempotency_key="idem-deadline",
        )
    )

    assert matter.target_deadline_at == datetime(
        2026, 8, 8, 18, 0, tzinfo=datetime.now(UTC).astimezone().tzinfo
    )
    assert len(state.deadlines) == 1
    assert isinstance(state.deadlines[0], Deadline)
    assert state.deadlines[0].confirmed_by == "legal-reviewer"


@pytest.mark.asyncio
async def test_rejection_does_not_change_matter() -> None:
    state = FakeState()
    candidate, matter = make_candidate_and_matter()
    state.candidates[candidate.id] = candidate
    state.matters[matter.id] = matter
    proposal = await create_proposal(state, candidate, matter)

    result = await ReviewMatterUpdateProposalHandler(state.factory).execute(
        ReviewMatterUpdateProposalCommand(
            proposal_id=proposal.id,
            proposal_version=proposal.version,
            matter_version=matter.version,
            decisions=[],
            rejection_reason="消息不足以变更正式事项。",
            actor_id="legal-reviewer",
            correlation_id="corr-reject",
            idempotency_key="idem-reject",
        )
    )

    assert result.status == MatterUpdateProposalStatus.REJECTED
    assert matter.version == 1
    assert state.work_items == {}
    assert state.deadlines == []
    assert isinstance(state.audit_events[-1], AuditEvent)
    assert isinstance(state.outbox_events[-1], OutboxEvent)
