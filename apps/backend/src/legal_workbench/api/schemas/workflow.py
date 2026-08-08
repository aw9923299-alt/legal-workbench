from datetime import datetime
from uuid import UUID

from pydantic import Field

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.domain.enums import (
    DeadlineSource,
    DeadlineStatus,
    DeadlineType,
    DependencyStatus,
    DependencyType,
    Priority,
    PriorityConfirmationStatus,
    WorkItemStatus,
)


class ConfirmPriorityRequest(ApiModel):
    work_item_version: int = Field(ge=1)
    confirmed_priority: Priority
    confirmed_complete_at: datetime | None = None
    reasons: list[str] = Field(default_factory=list)
    override_reason: str | None = None


class PriorityConfirmationResponse(ApiModel):
    id: UUID
    work_item_id: UUID
    proposed_priority: Priority
    confirmed_priority: Priority
    proposed_complete_at: datetime | None
    confirmed_complete_at: datetime | None
    reasons: list[str]
    override_reason: str | None
    confirmed_by: str
    confirmed_at: datetime
    status: PriorityConfirmationStatus
    version: int


class PriorityConfirmedResponse(ApiModel):
    work_item_id: UUID
    confirmation_id: UUID
    version: int
    idempotent_replay: bool


class CreateDeadlineRequest(ApiModel):
    deadline_type: DeadlineType
    source: DeadlineSource = DeadlineSource.LEGAL_CONFIRMED
    due_at: datetime
    timezone: str = Field(default="Asia/Singapore", min_length=1, max_length=64)
    is_hard: bool = False
    source_reference: str | None = Field(default=None, max_length=500)
    confidence: float | None = Field(default=None, ge=0, le=1)
    reminder_policy: dict[str, object] = Field(default_factory=dict)


class DeadlineResponse(ApiModel):
    id: UUID
    matter_id: UUID | None
    work_item_id: UUID | None
    deadline_type: DeadlineType
    source: DeadlineSource
    due_at: datetime
    timezone: str
    is_hard: bool
    status: DeadlineStatus
    source_reference: str | None
    confidence: float | None
    reminder_policy: dict[str, object]
    confirmed_by: str | None
    confirmed_at: datetime | None
    completed_at: datetime | None
    version: int


class DeadlineCreatedResponse(ApiModel):
    deadline_id: UUID
    idempotent_replay: bool


class CreateDependencyRequest(ApiModel):
    dependency_type: DependencyType
    depends_on_work_item_id: UUID | None = None
    external_party_id: str | None = Field(default=None, max_length=160)
    description: str | None = None


class DependencyResponse(ApiModel):
    id: UUID
    work_item_id: UUID
    depends_on_work_item_id: UUID | None
    dependency_type: DependencyType
    status: DependencyStatus
    external_party_id: str | None
    description: str | None
    satisfied_at: datetime | None
    satisfied_by: str | None
    waived_by: str | None
    waived_at: datetime | None
    version: int


class DependencyCreatedResponse(ApiModel):
    dependency_id: UUID
    work_item_version: int
    idempotent_replay: bool


class WorkItemActionRequest(ApiModel):
    reason: str | None = Field(default=None, max_length=4000)
    waiting_party_id: str | None = Field(default=None, max_length=160)
    blocker_owner_id: str | None = Field(default=None, max_length=160)


class ChangeWorkItemOwnerRequest(ApiModel):
    owner_id: str = Field(min_length=1, max_length=160)
    reason: str | None = Field(default=None, max_length=4000)


class ChangeWorkItemDeadlineRequest(ApiModel):
    deadline: datetime
    reason: str | None = Field(default=None, max_length=4000)


class ChangeWorkItemNextActionRequest(ApiModel):
    next_action: str = Field(min_length=1, max_length=4000)
    reason: str | None = Field(default=None, max_length=4000)


class WorkItemActionResponse(ApiModel):
    work_item_id: UUID
    status: WorkItemStatus
    version: int
    idempotent_replay: bool


class ResolveDependencyRequest(ApiModel):
    dependency_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=4000)


class DependencyResolvedResponse(ApiModel):
    work_item_id: UUID
    dependency_id: UUID
    work_item_version: int
    dependency_version: int
    status: DependencyStatus
    idempotent_replay: bool
