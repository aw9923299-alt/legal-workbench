from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

from legal_workbench.domain.common import utc_now
from legal_workbench.domain.errors import DomainValidationError


def normalize_knowledge_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


@dataclass(slots=True)
class KnowledgeDocument:
    id: UUID
    source_type: str
    source_id: str
    title: str
    document_type: str
    agent_types: list[str]
    matter_types: list[str]
    jurisdiction: str
    source_priority: int
    internal_precedent: bool
    confidentiality: str
    document_version_id: UUID | None = None
    matter_id: UUID | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    status: str = "active"
    approved_by: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    def __post_init__(self) -> None:
        if not self.source_type.strip() or not self.source_id.strip() or not self.title.strip():
            raise DomainValidationError("Knowledge source identity and title are required.")
        if not 0 <= self.source_priority <= 100:
            raise DomainValidationError("Knowledge source priority must be between 0 and 100.")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise DomainValidationError("Knowledge source effective dates are invalid.")


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    id: UUID
    knowledge_document_id: UUID
    sequence: int
    locator: str
    text: str
    normalized_text: str
    text_hash: str
    document_segment_id: UUID | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.sequence < 1 or not self.locator.strip() or not self.text.strip():
            raise DomainValidationError("Knowledge chunk sequence, locator and text are required.")
        if len(self.text_hash) != 64:
            raise DomainValidationError("Knowledge chunk content hash is invalid.")


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalLog:
    id: UUID
    query_hash: str
    filters: dict[str, object]
    selected_chunk_ids: list[UUID]
    component_scores: dict[str, dict[str, float]]
    correlation_id: str
    agent_run_id: UUID | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if len(self.query_hash) != 64 or not self.correlation_id.strip():
            raise DomainValidationError("Knowledge retrieval audit metadata is invalid.")


@dataclass(frozen=True, slots=True)
class KnowledgeSearchRequest:
    query: str
    agent_type: str
    matter_type: str
    jurisdiction: str
    document_types: tuple[str, ...]
    effective_date: date
    correlation_id: str
    agent_run_id: UUID | None = None
    source_priority_min: int = 0
    limit: int = 8

    def __post_init__(self) -> None:
        if not self.query.strip() or not self.agent_type.strip() or not self.matter_type.strip():
            raise DomainValidationError("Knowledge query and Agent/Matter filters are required.")
        if not self.jurisdiction.strip() or not self.document_types:
            raise DomainValidationError("Knowledge jurisdiction and document type are required.")
        if not 0 <= self.source_priority_min <= 100 or not 1 <= self.limit <= 50:
            raise DomainValidationError("Knowledge priority or result limit is invalid.")


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResult:
    document: KnowledgeDocument
    chunk: KnowledgeChunk
    source_ref: str
    score: float
    component_scores: dict[str, float]

    @property
    def internal_precedent(self) -> bool:
        return self.document.internal_precedent
