from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from legal_workbench.domain.common import (
    text_hash,
    utc_now,
)
from legal_workbench.domain.enums import (
    DocumentExtractionStatus,
    LocalDocumentSourceStatus,
    LocalKnowledgeScanStatus,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    InvalidStateTransitionError,
)


@dataclass(frozen=True, slots=True)
class ExtractedSegment:
    page_number: int | None
    paragraph_number: int
    start_offset: int
    end_offset: int
    content: str
    content_hash: str

    def __post_init__(self) -> None:
        if self.paragraph_number < 1:
            raise DomainValidationError("Document paragraph number must be positive.")
        if self.page_number is not None and self.page_number < 1:
            raise DomainValidationError("Document page number must be positive.")
        if self.start_offset < 0 or self.end_offset < self.start_offset:
            raise DomainValidationError("Document segment offsets are invalid.")
        if self.end_offset - self.start_offset != len(self.content):
            raise DomainValidationError("Document segment offsets do not match its content.")
        if text_hash(self.content) != self.content_hash:
            raise DomainValidationError("Document segment content hash is invalid.")


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    status: DocumentExtractionStatus
    segments: tuple[ExtractedSegment, ...]
    page_count: int | None
    character_count: int
    extractor_version: str = "document-text-v1"
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    id: UUID
    attachment_id: UUID | None
    version: int
    content_sha256: str
    file_name: str
    mime_type: str
    size: int
    local_path: str
    feishu_document_id: UUID | None = None
    local_source_id: UUID | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.version < 1 or self.size < 0:
            raise DomainValidationError("Document version metadata is invalid.")
        if len(self.content_sha256) != 64:
            raise DomainValidationError("Document version SHA-256 is invalid.")
        source_count = sum(
            source_id is not None
            for source_id in (self.attachment_id, self.feishu_document_id, self.local_source_id)
        )
        if source_count != 1:
            raise DomainValidationError("Document version must have exactly one source.")


@dataclass(slots=True)
class DocumentExtraction:
    id: UUID
    document_version_id: UUID
    status: DocumentExtractionStatus
    extractor_version: str
    page_count: int | None = None
    character_count: int = 0
    error_code: str | None = None
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)

    def complete(
        self,
        result: ExtractedDocument,
        *,
        now: datetime | None = None,
    ) -> None:
        if self.status != DocumentExtractionStatus.EXTRACTING:
            raise InvalidStateTransitionError("Only an extracting document can complete.")
        if result.status not in {
            DocumentExtractionStatus.SUCCEEDED,
            DocumentExtractionStatus.BODY_UNAVAILABLE,
        }:
            raise DomainValidationError("Document completion result is not successful.")
        self.status = result.status
        self.extractor_version = result.extractor_version
        self.page_count = result.page_count
        self.character_count = result.character_count
        self.error_code = result.error_code
        self.finished_at = now or utc_now()

    def fail(self, error_code: str, *, now: datetime | None = None) -> None:
        if self.status != DocumentExtractionStatus.EXTRACTING:
            raise InvalidStateTransitionError("Only an extracting document can fail.")
        self.status = DocumentExtractionStatus.FAILED
        self.error_code = error_code
        self.finished_at = now or utc_now()


@dataclass(frozen=True, slots=True)
class DocumentSegment:
    id: UUID
    extraction_id: UUID
    attachment_id: UUID | None
    page_number: int | None
    paragraph_number: int
    start_offset: int
    end_offset: int
    content: str
    content_hash: str
    feishu_document_id: UUID | None = None
    local_source_id: UUID | None = None
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def from_extracted(
        cls,
        *,
        extraction_id: UUID,
        attachment_id: UUID | None,
        segment: ExtractedSegment,
        feishu_document_id: UUID | None = None,
        local_source_id: UUID | None = None,
    ) -> DocumentSegment:
        return cls(
            id=uuid4(),
            extraction_id=extraction_id,
            attachment_id=attachment_id,
            page_number=segment.page_number,
            paragraph_number=segment.paragraph_number,
            start_offset=segment.start_offset,
            end_offset=segment.end_offset,
            content=segment.content,
            content_hash=segment.content_hash,
            feishu_document_id=feishu_document_id,
            local_source_id=local_source_id,
        )


@dataclass(slots=True)
class LocalDocumentSource:
    id: UUID
    source_root_key: str
    relative_path: str
    display_name: str
    status: LocalDocumentSourceStatus = LocalDocumentSourceStatus.ACTIVE
    last_seen_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    def __post_init__(self) -> None:
        path = PurePosixPath(self.relative_path)
        if (
            not self.source_root_key.strip()
            or not self.relative_path.strip()
            or not self.display_name.strip()
            or path.is_absolute()
            or ".." in path.parts
        ):
            raise DomainValidationError("Local document relative path and identity are invalid.")
        if self.version < 1:
            raise DomainValidationError("Local document source version is invalid.")

    def mark_seen(self, *, now: datetime | None = None) -> None:
        timestamp = now or utc_now()
        self.status = LocalDocumentSourceStatus.ACTIVE
        self.last_seen_at = timestamp
        self.updated_at = timestamp
        self.version += 1

    def mark_missing(self, *, now: datetime | None = None) -> None:
        if self.status == LocalDocumentSourceStatus.DISABLED:
            return
        self.status = LocalDocumentSourceStatus.MISSING
        self.updated_at = now or utc_now()
        self.version += 1


@dataclass(frozen=True, slots=True)
class LocalDocumentObservation:
    id: UUID
    local_source_id: UUID
    scan_id: UUID
    content_sha256: str
    size: int
    modified_at_ns: int
    document_version_id: UUID | None = None
    observed_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if len(self.content_sha256) != 64 or self.size < 0 or self.modified_at_ns < 0:
            raise DomainValidationError("Local document observation metadata is invalid.")


@dataclass(slots=True)
class LocalKnowledgeScan:
    id: UUID
    source_root_key: str
    correlation_id: str
    status: LocalKnowledgeScanStatus = LocalKnowledgeScanStatus.RUNNING
    discovered_count: int = 0
    unchanged_count: int = 0
    imported_count: int = 0
    deduplicated_count: int = 0
    failed_count: int = 0
    unsupported_count: int = 0
    missing_count: int = 0
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        counts = (
            self.discovered_count,
            self.unchanged_count,
            self.imported_count,
            self.deduplicated_count,
            self.failed_count,
            self.unsupported_count,
            self.missing_count,
        )
        if not self.source_root_key.strip() or not self.correlation_id.strip() or any(
            count < 0 for count in counts
        ):
            raise DomainValidationError("Local knowledge scan metadata is invalid.")

    def finish(self, *, now: datetime | None = None) -> None:
        self.status = (
            LocalKnowledgeScanStatus.COMPLETED
            if self.failed_count == 0
            else LocalKnowledgeScanStatus.PARTIAL
        )
        self.finished_at = now or utc_now()


@dataclass(slots=True)
class FeishuDocument:
    id: UUID
    authorization_id: UUID
    document_token: str
    document_type: str
    title: str | None
    source_url: str
    last_content_hash: str | None = None
    last_synced_at: datetime | None = None
    last_error_code: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.document_token.strip() or self.document_type not in {"docx", "wiki"}:
            raise DomainValidationError("Feishu document identity is invalid.")


@dataclass(slots=True)
class FeishuDocumentSubscription:
    id: UUID
    authorization_id: UUID
    folder_token: str
    recursive: bool
    active: bool = True
    version: int = 1
    last_synced_at: datetime | None = None
    last_error_code: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.folder_token.strip():
            raise DomainValidationError("A Feishu folder token is required.")
