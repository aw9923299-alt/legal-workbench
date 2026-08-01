from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from legal_workbench.domain.enums import (
    BusinessImpact,
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
