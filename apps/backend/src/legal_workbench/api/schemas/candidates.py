from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.domain.enums import (
    BusinessImpact,
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


class ContextSnapshotInput(ApiModel):
    source_type: str = Field(min_length=1, max_length=40)
    source_ids: list[str] = Field(min_length=1)
    message_ids: list[str] = Field(min_length=1)
    file_ids: list[str] = Field(default_factory=list)
    relevant_matter_ids: list[str] = Field(default_factory=list)
    participant_ids: list[str] = Field(default_factory=list)
    permission_snapshot: dict[str, object] = Field(default_factory=dict)
    generated_at: datetime
    content_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class CreateCandidateRequest(ApiModel):
    context: ContextSnapshotInput
    status: CandidateStatus = CandidateStatus.PENDING_CONFIRMATION
    legal_relevance: LegalRelevance
    message_role: MessageRole
    recommended_action: RecommendedAction
    confidence: float = Field(ge=0, le=1)
    title_proposal: str | None = Field(default=None, max_length=500)
    category_proposals: list[dict[str, object]] = Field(default_factory=list)
    deadline_proposals: list[dict[str, object]] = Field(default_factory=list)
    related_matter_proposals: list[dict[str, object]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    agent_run_id: UUID | None = None

    @field_validator("status")
    @classmethod
    def validate_initial_status(cls, value: CandidateStatus) -> CandidateStatus:
        if value not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise ValueError("A new candidate must start in a pending status.")
        return value


class InitialWorkItemRequest(ApiModel):
    title: str = Field(min_length=1, max_length=500)
    owner_id: str = Field(min_length=1, max_length=160)
    priority: Priority
    priority_source: PrioritySource
    next_action: str = Field(min_length=1)
    priority_reasons: list[str] = Field(default_factory=list)
    ai_suggested_priority: Priority | None = None
    estimated_minutes: int | None = Field(default=None, gt=0)
    planned_complete_at: datetime | None = None


class ConfirmCreateMatterRequest(ApiModel):
    candidate_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    primary_category: MatterCategory
    secondary_categories: list[MatterCategory] = Field(default_factory=list)
    owner_id: str = Field(min_length=1, max_length=160)
    requester_ids: list[str] = Field(default_factory=list)
    legal_risk: LegalRisk
    business_impact: BusinessImpact
    confidentiality: Confidentiality = Confidentiality.INTERNAL
    summary: str | None = None
    objective: str | None = None
    initial_work_items: list[InitialWorkItemRequest] = Field(min_length=1, max_length=50)


class CandidateResponse(ApiModel):
    id: UUID
    context_snapshot_id: UUID
    status: CandidateStatus
    legal_relevance: LegalRelevance
    message_role: MessageRole
    recommended_action: RecommendedAction
    confidence: float
    title_proposal: str | None
    category_proposals: list[dict[str, object]]
    deadline_proposals: list[dict[str, object]]
    related_matter_proposals: list[dict[str, object]]
    evidence_refs: list[str]
    agent_run_id: UUID | None
    feishu_message_id: UUID | None
    requires_manual_review: bool
    analysis_payload: dict[str, object]
    confirmed_by: str | None
    confirmed_at: datetime | None
    version: int


class CandidateCreatedResponse(ApiModel):
    candidate_id: UUID
    version: int
    idempotent_replay: bool


class MatterCreatedResponse(ApiModel):
    matter_id: UUID
    matter_number: str
    work_item_ids: list[UUID]
    idempotent_replay: bool


class ResolveCandidateRequest(ApiModel):
    candidate_version: int = Field(ge=1)
    action: CandidateResolutionAction
    matter_id: UUID | None = None


class CandidateResolvedResponse(ApiModel):
    candidate_id: UUID
    status: CandidateStatus
    matter_id: UUID | None
    version: int
    idempotent_replay: bool
