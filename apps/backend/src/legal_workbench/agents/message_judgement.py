from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from legal_workbench.domain.errors import DomainValidationError


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class StrictMessageModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class AgentDefinitionInput(StrictMessageModel):
    key: str = Field(min_length=1)
    version: str = Field(min_length=1)


class ContextSnapshotInput(StrictMessageModel):
    id: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    message_ids: list[str]
    participant_ids: list[str]
    attachment_ids: list[str]
    included_segments: list[dict[str, object]]
    excluded_segments: list[dict[str, object]]
    thread_metadata: dict[str, object]
    content: dict[str, object]
    builder_version: str
    selection_policy_version: str
    current_message_version: int = Field(ge=1)
    attachment_version_hash: str
    truncated: bool
    truncation_reason: str | None
    original_size: int = Field(ge=0)
    included_size: int = Field(ge=0)


class AgentConstraintsInput(StrictMessageModel):
    network_access: Literal[False]
    database_access: Literal[False]
    repository_access: Literal[False]
    shell_write_access: Literal[False]
    allowed_message_ids: list[str]
    allowed_attachment_ids: list[str]


class MessageJudgementInput(StrictMessageModel):
    run_id: str = Field(min_length=1)
    agent_definition: AgentDefinitionInput
    objective: str = Field(min_length=1)
    context_snapshot: ContextSnapshotInput
    constraints: AgentConstraintsInput


class JudgementLegalRelevance(StrEnum):
    RELEVANT = "relevant"
    POSSIBLY_RELEVANT = "possibly_relevant"
    IRRELEVANT = "irrelevant"


class JudgementMessageRole(StrEnum):
    NEW_REQUEST = "new_request"
    EXISTING_MATTER_UPDATE = "existing_matter_update"
    SUPPLEMENTAL_MATERIAL = "supplemental_material"
    DEADLINE_CHANGE = "deadline_change"
    DECISION_RECORD = "decision_record"
    COMPLETION_UPDATE = "completion_update"
    INFORMATION_ONLY = "information_only"


class JudgementActionability(StrEnum):
    CREATE_CANDIDATE = "create_candidate"
    LINK_CANDIDATE = "link_candidate"
    UPDATE_ONLY = "update_only"
    IGNORE = "ignore"


class JudgementCategory(StrEnum):
    CONTRACT = "contract"
    COPY_REVIEW = "copy_review"
    EMPLOYMENT = "employment"
    DISPUTE = "dispute"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    GENERAL = "general"


class JudgementDeadlineType(StrEnum):
    LEGAL = "legal"
    PLATFORM = "platform"
    CONTRACTUAL = "contractual"
    BUSINESS = "business"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class CategoryCandidate(StrictMessageModel):
    category: JudgementCategory
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class DeadlineCandidate(StrictMessageModel):
    raw_text: str = Field(min_length=1)
    resolved_at: datetime | None
    deadline_type: JudgementDeadlineType
    confidence: float = Field(ge=0, le=1)


class AttachmentFactCitation(StrictMessageModel):
    attachment_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    paragraph_number: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)


class ConfirmedFact(StrictMessageModel):
    statement: str = Field(min_length=1)
    source_message_id: str | None = Field(default=None, min_length=1)
    attachment_citation: AttachmentFactCitation | None = None

    @model_validator(mode="after")
    def require_exactly_one_evidence_source(self) -> ConfirmedFact:
        if (self.source_message_id is None) == (self.attachment_citation is None):
            raise ValueError(
                "A confirmed fact must reference exactly one evidence source."
            )
        return self


class InferredFact(StrictMessageModel):
    statement: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class MessageJudgementResult(StrictMessageModel):
    legal_relevance: JudgementLegalRelevance
    message_role: JudgementMessageRole
    actionability: JudgementActionability
    suggested_title: str = Field(min_length=1, max_length=500)
    category_candidates: list[CategoryCandidate] = Field(default_factory=list)
    deadline_candidates: list[DeadlineCandidate] = Field(default_factory=list)
    confirmed_facts: list[ConfirmedFact] = Field(default_factory=list)
    inferred_facts: list[InferredFact] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


def validate_confirmed_fact_sources(
    result: MessageJudgementResult,
    authorized_message_ids: set[str],
    authorized_attachment_citations: set[tuple[str, str, int | None, int, str]] | None = None,
) -> None:
    unauthorized = sorted(
        {
            fact.source_message_id
            for fact in result.confirmed_facts
            if fact.source_message_id is not None
            and fact.source_message_id not in authorized_message_ids
        }
    )
    if unauthorized:
        raise DomainValidationError(
            "Confirmed facts reference an unauthorized source message.",
            details={"sourceMessageIds": unauthorized},
        )
    allowed_citations = authorized_attachment_citations or set()
    unauthorized_attachments = sorted(
        {
            citation.attachment_id
            for fact in result.confirmed_facts
            if (citation := fact.attachment_citation) is not None
            and (
                citation.attachment_id,
                citation.file_name,
                citation.page_number,
                citation.paragraph_number,
                citation.content_hash,
            )
            not in allowed_citations
        }
    )
    if unauthorized_attachments:
        raise DomainValidationError(
            "Confirmed facts reference an unauthorized attachment segment.",
            details={"attachmentIds": unauthorized_attachments},
        )


def validate_message_judgement_business_rules(result: MessageJudgementResult) -> None:
    if (
        result.legal_relevance == JudgementLegalRelevance.IRRELEVANT
        and result.actionability != JudgementActionability.IGNORE
    ):
        raise DomainValidationError("An irrelevant message must use ignore actionability.")
    if (
        result.legal_relevance != JudgementLegalRelevance.IRRELEVANT
        and result.actionability == JudgementActionability.IGNORE
    ):
        raise DomainValidationError("A legal message cannot be ignored by the Agent.")


def should_create_candidate(result: MessageJudgementResult) -> bool:
    return (
        result.legal_relevance
        in {
            JudgementLegalRelevance.RELEVANT,
            JudgementLegalRelevance.POSSIBLY_RELEVANT,
        }
        and result.actionability != JudgementActionability.IGNORE
    )


def candidate_requires_manual_review(result: MessageJudgementResult, *, threshold: float) -> bool:
    return (
        result.confidence < threshold
        or result.legal_relevance == JudgementLegalRelevance.POSSIBLY_RELEVANT
    )
