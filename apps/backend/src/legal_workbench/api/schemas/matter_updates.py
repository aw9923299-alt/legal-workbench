from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.domain.enums import (
    MatterUpdateProposalStatus,
    ProposalFieldDecisionType,
)

ProposalFieldName = Literal[
    "title",
    "category",
    "priority",
    "deadline",
    "owner",
    "currentStatus",
    "nextAction",
    "newWorkItems",
]

MatterUpdateProposalFieldNames: tuple[ProposalFieldName, ...] = (
    "title",
    "category",
    "priority",
    "deadline",
    "owner",
    "currentStatus",
    "nextAction",
    "newWorkItems",
)


class ProposedFieldValues(ApiModel):
    current_value: object | None
    message_extracted_value: object | None
    ai_suggested_value: object | None


class CreateMatterUpdateProposalRequest(ApiModel):
    candidate_version: int = Field(ge=1)
    matter_id: UUID
    proposed_changes: dict[str, ProposedFieldValues] = Field(min_length=1, max_length=8)
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("proposed_changes")
    @classmethod
    def validate_proposed_fields(
        cls, value: dict[str, ProposedFieldValues]
    ) -> dict[str, ProposedFieldValues]:
        allowed = set(MatterUpdateProposalFieldNames)
        unsupported = set(value) - allowed
        if unsupported:
            raise ValueError(f"Unsupported proposal fields: {sorted(unsupported)}")
        return value


class ProposalFieldDecisionRequest(ApiModel):
    field_name: ProposalFieldName
    decision: ProposalFieldDecisionType
    final_value: object | None = None


class ReviewMatterUpdateProposalRequest(ApiModel):
    proposal_version: int = Field(ge=1)
    matter_version: int = Field(ge=1)
    decisions: list[ProposalFieldDecisionRequest] = Field(max_length=8)
    rejection_reason: str | None = Field(default=None, max_length=4000)


class MatterUpdateProposalCreatedResponse(ApiModel):
    proposal_id: UUID
    candidate_id: UUID
    matter_id: UUID
    status: MatterUpdateProposalStatus
    version: int
    idempotent_replay: bool


class MatterUpdateProposalResponse(ApiModel):
    id: UUID
    candidate_id: UUID
    matter_id: UUID
    base_matter_version: int
    proposed_changes: dict[str, dict[str, object]]
    final_changes: dict[str, object]
    field_decisions: list[dict[str, object]]
    reason: str
    status: MatterUpdateProposalStatus
    created_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    version: int


class MatterUpdateProposalReviewedResponse(ApiModel):
    proposal_id: UUID
    matter_id: UUID
    status: MatterUpdateProposalStatus
    proposal_version: int
    matter_version: int
    work_item_ids: list[UUID]
    deadline_id: UUID | None
    idempotent_replay: bool
