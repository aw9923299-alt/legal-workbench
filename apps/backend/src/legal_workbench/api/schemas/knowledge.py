from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.domain.enums import (
    AuthorityRole,
    AuthorityStatus,
    AuthorityType,
    KnowledgeMetadataStatus,
)


class KnowledgeDocumentResponse(ApiModel):
    id: UUID
    source_type: str
    source_id: str
    document_version_id: UUID | None
    matter_id: UUID | None
    title: str
    document_type: str
    agent_types: list[str]
    matter_types: list[str]
    jurisdiction: str
    effective_from: date | None
    effective_to: date | None
    status: str
    source_priority: int
    internal_precedent: bool
    confidentiality: str
    approved_by: str | None
    authority_type: AuthorityType
    authority_role: AuthorityRole | None
    authority_status: AuthorityStatus
    metadata_status: KnowledgeMetadataStatus
    issuer: str | None
    document_number: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime
    version: int


class KnowledgeChunkResponse(ApiModel):
    id: UUID
    knowledge_document_id: UUID
    document_segment_id: UUID | None
    sequence: int
    locator: str
    text: str
    text_hash: str
    estimated_token_count: int
    token_estimator: str
    token_count_estimated: bool
    created_at: datetime


class KnowledgeRetrievalLogResponse(ApiModel):
    id: UUID
    query_hash: str
    filters: dict[str, object]
    selected_chunk_ids: list[UUID]
    component_scores: dict[str, dict[str, float]]
    correlation_id: str
    agent_run_id: UUID | None
    candidate_count: int
    selected_chunk_count: int
    selected_token_count: int
    excluded_by_token_budget_count: int
    excluded_duplicate_count: int
    budget: dict[str, int]
    created_at: datetime


class KnowledgeDocumentDetailsResponse(ApiModel):
    document: KnowledgeDocumentResponse
    chunks: list[KnowledgeChunkResponse]
    retrieval_logs: list[KnowledgeRetrievalLogResponse]


class UpdateKnowledgeMetadataRequest(ApiModel):
    title: str = Field(min_length=1, max_length=500)
    authority_type: AuthorityType
    authority_role: AuthorityRole | None = None
    authority_status: AuthorityStatus
    jurisdiction: str = Field(min_length=1, max_length=80)
    effective_from: date | None = None
    effective_to: date | None = None
    issuer: str | None = Field(default=None, max_length=300)
    document_number: str | None = Field(default=None, max_length=160)
    enabled: bool


class KnowledgeMetadataUpdatedResponse(ApiModel):
    document_id: UUID
    version: int
    idempotent_replay: bool
