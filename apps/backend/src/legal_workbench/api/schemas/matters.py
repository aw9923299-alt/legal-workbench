from datetime import datetime
from uuid import UUID

from pydantic import Field

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.domain.enums import (
    BusinessImpact,
    Confidentiality,
    LegalRisk,
    MatterCategory,
    MatterLifecycleStatus,
    MatterWorkStatus,
    Priority,
    PrioritySource,
    WorkItemStatus,
)


class LegalMatterResponse(ApiModel):
    id: UUID
    matter_number: str
    title: str
    primary_category: MatterCategory
    secondary_categories: list[MatterCategory]
    lifecycle_status: MatterLifecycleStatus
    work_status: MatterWorkStatus
    owner_id: str
    collaborator_ids: list[str]
    requester_ids: list[str]
    entity_ids: list[str]
    legal_risk: LegalRisk
    business_impact: BusinessImpact
    priority: Priority
    priority_source: PrioritySource
    target_deadline_at: datetime | None
    next_action: str | None
    confidentiality: Confidentiality
    summary: str | None
    objective: str | None
    current_stage: str | None
    version: int
    opened_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None
    reopened_at: datetime | None


class CreateWorkItemRequest(ApiModel):
    title: str = Field(min_length=1, max_length=500)
    owner_id: str = Field(min_length=1, max_length=160)
    priority: Priority
    priority_source: PrioritySource
    next_action: str = Field(min_length=1)
    priority_reasons: list[str] = Field(default_factory=list)
    ai_suggested_priority: Priority | None = None
    estimated_minutes: int | None = Field(default=None, gt=0)
    planned_complete_at: datetime | None = None


class WorkItemResponse(ApiModel):
    id: UUID
    matter_id: UUID
    title: str
    status: WorkItemStatus
    owner_id: str
    collaborator_ids: list[str]
    priority: Priority
    priority_source: PrioritySource
    ai_suggested_priority: Priority | None
    priority_reasons: list[str]
    override_reason: str | None
    estimated_minutes: int | None
    next_action: str
    waiting_party_id: str | None
    waiting_reason: str | None
    waiting_since: datetime | None
    is_blocked: bool
    blocker_reason: str | None
    blocker_owner_id: str | None
    planned_start_at: datetime | None
    planned_complete_at: datetime | None
    completed_at: datetime | None
    priority_confirmed_by: str | None
    priority_confirmed_at: datetime | None
    sequence_order: int
    version: int


class WorkItemCreatedResponse(ApiModel):
    work_item_id: UUID
    matter_id: UUID
    idempotent_replay: bool
