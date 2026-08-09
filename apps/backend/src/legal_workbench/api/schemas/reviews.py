from datetime import datetime
from uuid import UUID

from pydantic import Field

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.domain.enums import (
    CommunicationChannel,
    CommunicationStatus,
    ReviewDecision,
    ReviewPackageStatus,
    ReviewPackageType,
)


class CreateReviewPackageRequest(ApiModel):
    matter_id: UUID
    work_item_id: UUID | None = None
    package_type: ReviewPackageType = ReviewPackageType.EXTERNAL_MESSAGE
    title: str = Field(min_length=1, max_length=500)
    background: str = Field(min_length=1)
    confirmed_facts: list[dict[str, object]] = Field(default_factory=list)
    unconfirmed_facts: list[dict[str, object]] = Field(default_factory=list)
    reasoning: str = Field(min_length=1)
    risks: list[dict[str, object]] = Field(default_factory=list)
    alternatives: list[dict[str, object]] = Field(default_factory=list)
    citations: list[dict[str, object]] = Field(default_factory=list)
    proposed_content: str = Field(min_length=1)
    target: dict[str, object]
    submit_for_review: bool = True


class SubmitReviewPackageRequest(ApiModel):
    package_version: int = Field(ge=1)


class ReviewPackageDecisionRequest(ApiModel):
    package_version: int = Field(ge=1)
    decision: ReviewDecision
    comments: str | None = None
    final_content: str | None = None
    change_summary: list[dict[str, object]] = Field(default_factory=list)
    reusable_as_example: bool = False


class ReviewPackageResponse(ApiModel):
    id: UUID
    matter_id: UUID
    work_item_id: UUID | None
    package_type: ReviewPackageType
    status: ReviewPackageStatus
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
    created_by: str
    submitted_at: datetime | None
    approved_content_hash: str | None
    grounding_payload: dict[str, object]
    version: int


class ReviewPackageCreatedResponse(ApiModel):
    review_package_id: UUID
    version: int
    idempotent_replay: bool


class ReviewRecordResponse(ApiModel):
    id: UUID
    review_package_id: UUID
    reviewer_id: str
    decision: ReviewDecision
    comments: str | None
    final_content: str | None
    final_content_hash: str | None
    change_summary: list[dict[str, object]]
    reusable_as_example: bool
    reviewed_at: datetime


class ReviewRecordedResponse(ApiModel):
    review_package_id: UUID
    review_record_id: UUID
    status: str
    idempotent_replay: bool


class QueueCommunicationResponse(ApiModel):
    communication_id: UUID
    status: str
    idempotent_replay: bool


class CommunicationResponse(ApiModel):
    id: UUID
    matter_id: UUID
    work_item_id: UUID | None
    review_package_id: UUID
    review_record_id: UUID
    channel: CommunicationChannel
    target: dict[str, object]
    content: str
    content_hash: str
    status: CommunicationStatus
    requested_by: str
    correlation_id: str
    external_message_id: str | None
    attempts: int
    last_error: str | None
    queued_at: datetime | None
    sent_at: datetime | None
    version: int
