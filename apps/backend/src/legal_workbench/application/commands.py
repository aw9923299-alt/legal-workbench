from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from legal_workbench.domain.enums import (
    BusinessImpact,
    CandidateResolutionAction,
    CandidateStatus,
    Confidentiality,
    DeadlineSource,
    DeadlineType,
    DependencyType,
    LegalRelevance,
    LegalRisk,
    MatterCategory,
    MessageRole,
    Priority,
    PrioritySource,
    RecommendedAction,
    ReviewDecision,
    ReviewPackageType,
)


@dataclass(frozen=True, slots=True)
class CreateCandidateCommand:
    source_type: str
    source_ids: list[str]
    message_ids: list[str]
    file_ids: list[str]
    relevant_matter_ids: list[str]
    participant_ids: list[str]
    permission_snapshot: dict[str, object]
    generated_at: datetime
    content_hash: str
    actor_id: str
    correlation_id: str
    idempotency_key: str
    status: CandidateStatus
    legal_relevance: LegalRelevance
    message_role: MessageRole
    recommended_action: RecommendedAction
    confidence: float
    title_proposal: str | None
    category_proposals: list[dict[str, object]] = field(default_factory=list)
    deadline_proposals: list[dict[str, object]] = field(default_factory=list)
    related_matter_proposals: list[dict[str, object]] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    agent_run_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InitialWorkItemInput:
    title: str
    owner_id: str
    priority: Priority
    priority_source: PrioritySource
    next_action: str
    priority_reasons: list[str] = field(default_factory=list)
    ai_suggested_priority: Priority | None = None
    estimated_minutes: int | None = None
    planned_complete_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ConfirmCandidateCreateMatterCommand:
    candidate_id: UUID
    candidate_version: int
    actor_id: str
    correlation_id: str
    idempotency_key: str
    title: str
    primary_category: MatterCategory
    secondary_categories: list[MatterCategory]
    owner_id: str
    requester_ids: list[str]
    legal_risk: LegalRisk
    business_impact: BusinessImpact
    confidentiality: Confidentiality
    summary: str | None
    objective: str | None
    initial_work_items: list[InitialWorkItemInput]


@dataclass(frozen=True, slots=True)
class ResolveCandidateCommand:
    candidate_id: UUID
    candidate_version: int
    action: CandidateResolutionAction
    matter_id: UUID | None
    actor_id: str
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class AddWorkItemCommand:
    matter_id: UUID
    actor_id: str
    correlation_id: str
    idempotency_key: str
    title: str
    owner_id: str
    priority: Priority
    priority_source: PrioritySource
    next_action: str
    priority_reasons: list[str]
    ai_suggested_priority: Priority | None = None
    estimated_minutes: int | None = None
    planned_complete_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ConfirmPriorityCommand:
    work_item_id: UUID
    work_item_version: int
    actor_id: str
    correlation_id: str
    idempotency_key: str
    confirmed_priority: Priority
    confirmed_complete_at: datetime | None
    reasons: list[str]
    override_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CreateDeadlineCommand:
    actor_id: str
    correlation_id: str
    idempotency_key: str
    deadline_type: DeadlineType
    source: DeadlineSource
    due_at: datetime
    timezone: str
    is_hard: bool
    matter_id: UUID | None = None
    work_item_id: UUID | None = None
    source_reference: str | None = None
    confidence: float | None = None
    reminder_policy: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CreateDependencyCommand:
    work_item_id: UUID
    actor_id: str
    correlation_id: str
    idempotency_key: str
    dependency_type: DependencyType
    depends_on_work_item_id: UUID | None = None
    external_party_id: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class CreateReviewPackageCommand:
    matter_id: UUID
    work_item_id: UUID | None
    actor_id: str
    correlation_id: str
    idempotency_key: str
    package_type: ReviewPackageType
    title: str
    background: str
    confirmed_facts: list[dict[str, object]]
    unconfirmed_facts: list[dict[str, object]]
    reasoning: str
    risks: list[dict[str, object]]
    alternatives: list[dict[str, object]]
    citations: list[dict[str, object]]
    proposed_content: str
    target: dict[str, object]
    submit_for_review: bool = True


@dataclass(frozen=True, slots=True)
class SubmitReviewPackageCommand:
    review_package_id: UUID
    package_version: int
    actor_id: str
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ReviewPackageCommand:
    review_package_id: UUID
    package_version: int
    actor_id: str
    correlation_id: str
    idempotency_key: str
    decision: ReviewDecision
    comments: str | None
    final_content: str | None
    change_summary: list[dict[str, object]]
    reusable_as_example: bool = False


@dataclass(frozen=True, slots=True)
class QueueCommunicationCommand:
    review_package_id: UUID
    actor_id: str
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class IngestFeishuEventCommand:
    actor_id: str
    correlation_id: str
    event_id: str
    event_type: str
    tenant_key: str | None
    app_id: str | None
    schema_version: str | None
    raw_payload: dict[str, object]
