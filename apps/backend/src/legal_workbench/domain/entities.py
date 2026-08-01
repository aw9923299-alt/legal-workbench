from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from legal_workbench.domain.enums import (
    BusinessImpact,
    CandidateStatus,
    Confidentiality,
    LegalRelevance,
    LegalRisk,
    MatterCategory,
    MatterLifecycleStatus,
    MatterWorkStatus,
    MessageRole,
    Priority,
    PrioritySource,
    RecommendedAction,
    WorkItemStatus,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityVersionConflictError,
    InvalidStateTransitionError,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class MessageCandidate:
    id: UUID
    context_snapshot_id: UUID
    status: CandidateStatus
    legal_relevance: LegalRelevance
    message_role: MessageRole
    recommended_action: RecommendedAction
    confidence: float
    title_proposal: str | None = None
    category_proposals: list[dict[str, object]] = field(default_factory=list)
    deadline_proposals: list[dict[str, object]] = field(default_factory=list)
    related_matter_proposals: list[dict[str, object]] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    agent_run_id: UUID | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise DomainValidationError(
                "Candidate confidence must be between 0 and 1.",
                details={"confidence": self.confidence},
            )

    @classmethod
    def create(
        cls,
        *,
        context_snapshot_id: UUID,
        status: CandidateStatus,
        legal_relevance: LegalRelevance,
        message_role: MessageRole,
        recommended_action: RecommendedAction,
        confidence: float,
        title_proposal: str | None,
        category_proposals: list[dict[str, object]],
        deadline_proposals: list[dict[str, object]],
        related_matter_proposals: list[dict[str, object]],
        evidence_refs: list[str],
        agent_run_id: UUID | None,
    ) -> MessageCandidate:
        if status not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise DomainValidationError(
                "A new message candidate must start in a pending status.",
                details={"status": status.value},
            )
        normalized_title = title_proposal.strip() if title_proposal else None
        return cls(
            id=uuid4(),
            context_snapshot_id=context_snapshot_id,
            status=status,
            legal_relevance=legal_relevance,
            message_role=message_role,
            recommended_action=recommended_action,
            confidence=confidence,
            title_proposal=normalized_title or None,
            category_proposals=category_proposals,
            deadline_proposals=deadline_proposals,
            related_matter_proposals=related_matter_proposals,
            evidence_refs=evidence_refs,
            agent_run_id=agent_run_id,
        )

    def confirm_create_matter(self, *, actor_id: str, expected_version: int) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError(
                "The message candidate was changed by another operation.",
                details={"expectedVersion": expected_version, "actualVersion": self.version},
            )
        if self.status not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise InvalidStateTransitionError(
                "Only a pending candidate can create a legal matter.",
                details={"candidateId": str(self.id), "status": self.status.value},
            )
        if self.legal_relevance not in {
            LegalRelevance.RELEVANT,
            LegalRelevance.POSSIBLY_RELEVANT,
        }:
            raise InvalidStateTransitionError(
                "A non-legal candidate cannot create a legal matter.",
                details={"legalRelevance": self.legal_relevance.value},
            )
        self.status = CandidateStatus.CONFIRMED
        self.confirmed_by = actor_id
        self.confirmed_at = utc_now()


@dataclass(slots=True)
class LegalMatter:
    id: UUID
    matter_number: str
    title: str
    primary_category: MatterCategory
    owner_id: str
    legal_risk: LegalRisk
    business_impact: BusinessImpact
    secondary_categories: list[MatterCategory] = field(default_factory=list)
    lifecycle_status: MatterLifecycleStatus = MatterLifecycleStatus.OPEN
    work_status: MatterWorkStatus = MatterWorkStatus.READY
    collaborator_ids: list[str] = field(default_factory=list)
    requester_ids: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    confidentiality: Confidentiality = Confidentiality.INTERNAL
    summary: str | None = None
    objective: str | None = None
    current_stage: str | None = None
    opened_at: datetime = field(default_factory=utc_now)
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    reopened_at: datetime | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        title: str,
        primary_category: MatterCategory,
        secondary_categories: list[MatterCategory],
        owner_id: str,
        legal_risk: LegalRisk,
        business_impact: BusinessImpact,
        confidentiality: Confidentiality,
        requester_ids: list[str],
        summary: str | None,
        objective: str | None,
    ) -> LegalMatter:
        normalized_title = title.strip()
        normalized_owner = owner_id.strip()
        if not normalized_title:
            raise DomainValidationError("Matter title is required.")
        if not normalized_owner:
            raise DomainValidationError("Matter owner is required.")
        matter_id = uuid4()
        date_part = utc_now().strftime("%Y%m%d")
        unique_secondary_categories = [
            category
            for category in dict.fromkeys(secondary_categories)
            if category != primary_category
        ]
        return cls(
            id=matter_id,
            matter_number=f"LW-{date_part}-{matter_id.hex[:8].upper()}",
            title=normalized_title,
            primary_category=primary_category,
            secondary_categories=unique_secondary_categories,
            owner_id=normalized_owner,
            legal_risk=legal_risk,
            business_impact=business_impact,
            confidentiality=confidentiality,
            requester_ids=list(dict.fromkeys(requester_ids)),
            summary=summary,
            objective=objective,
        )


@dataclass(slots=True)
class WorkItem:
    id: UUID
    matter_id: UUID
    title: str
    owner_id: str
    priority: Priority
    priority_source: PrioritySource
    next_action: str
    status: WorkItemStatus = WorkItemStatus.TODO
    collaborator_ids: list[str] = field(default_factory=list)
    ai_suggested_priority: Priority | None = None
    priority_reasons: list[str] = field(default_factory=list)
    override_reason: str | None = None
    estimated_minutes: int | None = None
    waiting_party_id: str | None = None
    waiting_reason: str | None = None
    waiting_since: datetime | None = None
    is_blocked: bool = False
    blocker_reason: str | None = None
    blocker_owner_id: str | None = None
    planned_start_at: datetime | None = None
    planned_complete_at: datetime | None = None
    completed_at: datetime | None = None
    sequence_order: int = 0
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        matter_id: UUID,
        title: str,
        owner_id: str,
        priority: Priority,
        priority_source: PrioritySource,
        next_action: str,
        priority_reasons: list[str],
        ai_suggested_priority: Priority | None = None,
        estimated_minutes: int | None = None,
        planned_complete_at: datetime | None = None,
        sequence_order: int = 0,
    ) -> WorkItem:
        normalized_title = title.strip()
        normalized_owner = owner_id.strip()
        normalized_next_action = next_action.strip()
        if not normalized_title:
            raise DomainValidationError("Work item title is required.")
        if not normalized_owner:
            raise DomainValidationError("Work item owner is required.")
        if not normalized_next_action:
            raise DomainValidationError("Work item next action is required.")
        if estimated_minutes is not None and estimated_minutes <= 0:
            raise DomainValidationError(
                "Estimated minutes must be positive.",
                details={"estimatedMinutes": estimated_minutes},
            )
        return cls(
            id=uuid4(),
            matter_id=matter_id,
            title=normalized_title,
            owner_id=normalized_owner,
            priority=priority,
            priority_source=priority_source,
            next_action=normalized_next_action,
            priority_reasons=priority_reasons,
            ai_suggested_priority=ai_suggested_priority,
            estimated_minutes=estimated_minutes,
            planned_complete_at=planned_complete_at,
            sequence_order=sequence_order,
        )


@dataclass(slots=True)
class ContextSnapshot:
    id: UUID
    source_type: str
    source_ids: list[str]
    message_ids: list[str]
    file_ids: list[str]
    relevant_matter_ids: list[str]
    participant_ids: list[str]
    permission_snapshot: dict[str, object]
    generated_at: datetime
    content_hash: str


@dataclass(slots=True)
class AuditEvent:
    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_type: str
    actor_id: str
    payload: dict[str, object]
    correlation_id: str
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class OutboxEvent:
    id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, object]
    correlation_id: str
    occurred_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class IdempotencyRecord:
    id: UUID
    operation: str
    idempotency_key: str
    request_hash: str
    response_payload: dict[str, object]
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
