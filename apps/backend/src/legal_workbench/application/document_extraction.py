from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from legal_workbench.application.automatic_analysis_gate import AutomaticAnalysisGate
from legal_workbench.application.ports import UnitOfWork, UnitOfWorkFactory
from legal_workbench.domain.entities import (
    DocumentExtraction,
    DocumentSegment,
    DocumentVersion,
    ExtractedDocument,
    MessageAttachment,
)
from legal_workbench.domain.enums import AttachmentDownloadStatus, DocumentExtractionStatus
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityNotFoundError,
    InvalidStateTransitionError,
)


class DocumentExtractor(Protocol):
    def extract(self, path: Path, mime_type: str) -> ExtractedDocument: ...


@dataclass(frozen=True, slots=True)
class PreparedDocumentExtraction:
    extraction_id: UUID
    attachment_id: UUID
    path: Path
    mime_type: str


@dataclass(frozen=True, slots=True)
class DocumentExtractionResult:
    extraction_id: UUID
    attachment_id: UUID
    status: DocumentExtractionStatus
    error_code: str | None = None


class DocumentExtractionService:
    """Persist extraction state without holding a transaction during parsing."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        extractor: DocumentExtractor,
        analysis_gate: AutomaticAnalysisGate | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._extractor = extractor
        self._analysis_gate = analysis_gate or AutomaticAnalysisGate()

    async def execute(self, attachment_id: UUID) -> DocumentExtractionResult:
        prepared = await self._prepare(attachment_id)
        if isinstance(prepared, DocumentExtractionResult):
            return prepared
        try:
            extracted = self._extractor.extract(prepared.path, prepared.mime_type)
        except Exception as exc:
            error_code = _safe_error_code(exc)
            await self._fail(prepared, error_code)
            return DocumentExtractionResult(
                extraction_id=prepared.extraction_id,
                attachment_id=attachment_id,
                status=DocumentExtractionStatus.FAILED,
                error_code=error_code,
            )

        if extracted.status == DocumentExtractionStatus.FAILED:
            error_code = extracted.error_code or "DOCUMENT_EXTRACTION_FAILED"
            await self._fail(prepared, error_code)
            return DocumentExtractionResult(
                extraction_id=prepared.extraction_id,
                attachment_id=attachment_id,
                status=DocumentExtractionStatus.FAILED,
                error_code=error_code,
            )

        await self._complete(prepared, extracted)
        return DocumentExtractionResult(
            extraction_id=prepared.extraction_id,
            attachment_id=attachment_id,
            status=extracted.status,
            error_code=extracted.error_code,
        )

    async def _prepare(
        self, attachment_id: UUID
    ) -> PreparedDocumentExtraction | DocumentExtractionResult:
        async with self._uow_factory() as uow:
            attachment = await uow.feishu.get_attachment_for_update(attachment_id)
            if attachment is None:
                raise EntityNotFoundError("Message attachment was not found.")
            if attachment.download_status != AttachmentDownloadStatus.DOWNLOADED:
                raise InvalidStateTransitionError("Only a downloaded attachment can be extracted.")
            if (
                attachment.sha256 is None
                or attachment.local_path is None
                or attachment.size is None
            ):
                raise DomainValidationError("Downloaded attachment metadata is incomplete.")
            mime_type = attachment.mime_type or "application/octet-stream"
            version = await uow.documents.find_version(
                attachment_id=attachment.id,
                content_sha256=attachment.sha256,
            )
            if version is None:
                version = DocumentVersion(
                    id=uuid4(),
                    attachment_id=attachment.id,
                    version=await uow.documents.next_version(attachment.id),
                    content_sha256=attachment.sha256,
                    file_name=attachment.file_name,
                    mime_type=mime_type,
                    size=attachment.size,
                    local_path=attachment.local_path,
                )
                await uow.documents.add_version(version)
                # The repositories intentionally map domain objects without ORM
                # relationships. Persist the parent row before adding an
                # extraction that references it so PostgreSQL FK ordering does
                # not depend on SQLAlchemy mapper discovery.
                await uow.flush()
            existing_extraction = await uow.documents.find_latest_extraction(version.id)
            if existing_extraction is not None and existing_extraction.status in {
                DocumentExtractionStatus.SUCCEEDED,
                DocumentExtractionStatus.BODY_UNAVAILABLE,
                DocumentExtractionStatus.FAILED,
            }:
                return DocumentExtractionResult(
                    extraction_id=existing_extraction.id,
                    attachment_id=attachment.id,
                    status=existing_extraction.status,
                    error_code=existing_extraction.error_code,
                )
            if existing_extraction is not None:
                return PreparedDocumentExtraction(
                    extraction_id=existing_extraction.id,
                    attachment_id=attachment.id,
                    path=Path(version.local_path),
                    mime_type=version.mime_type,
                )
            extraction = DocumentExtraction(
                id=uuid4(),
                document_version_id=version.id,
                status=DocumentExtractionStatus.EXTRACTING,
                extractor_version="pending",
            )
            await uow.documents.add_extraction(extraction)
            attachment.extraction_status = DocumentExtractionStatus.EXTRACTING
            attachment.extraction_error_code = None
            await uow.feishu.save_attachment(attachment)
            await uow.commit()
        return PreparedDocumentExtraction(
            extraction_id=extraction.id,
            attachment_id=attachment.id,
            path=Path(version.local_path),
            mime_type=version.mime_type,
        )

    async def _complete(
        self,
        prepared: PreparedDocumentExtraction,
        extracted: ExtractedDocument,
    ) -> None:
        async with self._uow_factory() as uow:
            extraction = await uow.documents.get_extraction_for_update(prepared.extraction_id)
            if extraction is None:
                raise EntityNotFoundError("Document extraction was not found.")
            version = await uow.documents.get_version(extraction.document_version_id)
            attachment = await uow.feishu.get_attachment_for_update(prepared.attachment_id)
            if version is None or attachment is None:
                raise EntityNotFoundError("Document extraction source was not found.")
            extraction.complete(extracted)
            segments = tuple(
                DocumentSegment.from_extracted(
                    extraction_id=extraction.id,
                    attachment_id=version.attachment_id,
                    segment=segment,
                )
                for segment in extracted.segments
            )
            if segments:
                await uow.documents.add_segments(segments)
            await uow.documents.save_extraction(extraction)
            attachment.extraction_status = extracted.status
            attachment.extractor_version = extracted.extractor_version
            attachment.page_count = extracted.page_count
            attachment.character_count = extracted.character_count
            attachment.extraction_error_code = extracted.error_code
            await uow.feishu.save_attachment(attachment)
            await self._request_analysis_if_ready(uow, attachment)
            await uow.commit()

    async def _fail(
        self,
        prepared: PreparedDocumentExtraction,
        error_code: str,
    ) -> None:
        async with self._uow_factory() as uow:
            extraction = await uow.documents.get_extraction_for_update(prepared.extraction_id)
            attachment = await uow.feishu.get_attachment_for_update(prepared.attachment_id)
            if extraction is None or attachment is None:
                raise EntityNotFoundError("Document extraction source was not found.")
            extraction.fail(error_code)
            await uow.documents.save_extraction(extraction)
            attachment.extraction_status = DocumentExtractionStatus.FAILED
            attachment.extraction_error_code = error_code
            await uow.feishu.save_attachment(attachment)
            await self._request_analysis_if_ready(uow, attachment)
            await uow.commit()

    async def _request_analysis_if_ready(
        self,
        uow: UnitOfWork,
        attachment: MessageAttachment,
    ) -> None:
        message_id = attachment.feishu_message_id
        await uow.lock_idempotency(
            operation="attachment_analysis_ready",
            key=str(message_id),
        )
        attachments = await uow.feishu.list_attachments(message_id)
        if not attachments or not all(_is_attachment_terminal(value) for value in attachments):
            return
        message = await uow.feishu.get_message_by_id(message_id)
        await self._analysis_gate.request_if_allowed(
            uow,
            message_id,
            actor_id="document-extraction-worker",
            actor_source="integration",
            correlation_id=f"attachment-analysis:{message_id}",
            force_new_run=bool(message is not None and message.version > 1),
        )


def _safe_error_code(exc: Exception) -> str:
    candidate = getattr(exc, "code", "DOCUMENT_EXTRACTION_FAILED")
    if not isinstance(candidate, str) or not candidate.isascii():
        return "DOCUMENT_EXTRACTION_FAILED"
    normalized = candidate.strip().upper()
    if not normalized or len(normalized) > 100:
        return "DOCUMENT_EXTRACTION_FAILED"
    return normalized


def _is_attachment_terminal(attachment: MessageAttachment) -> bool:
    if attachment.download_status in {
        AttachmentDownloadStatus.FAILED,
        AttachmentDownloadStatus.METADATA_ONLY,
    }:
        return True
    return attachment.download_status == AttachmentDownloadStatus.DOWNLOADED and (
        attachment.extraction_status
        in {
            DocumentExtractionStatus.SUCCEEDED,
            DocumentExtractionStatus.BODY_UNAVAILABLE,
            DocumentExtractionStatus.FAILED,
        }
    )
