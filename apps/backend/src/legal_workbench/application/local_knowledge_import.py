from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID, uuid4

from legal_workbench.application.ports import UnitOfWork, UnitOfWorkFactory
from legal_workbench.domain.common import utc_now
from legal_workbench.domain.documents import (
    DocumentExtraction,
    DocumentSegment,
    DocumentVersion,
    ExtractedDocument,
    LocalDocumentObservation,
    LocalDocumentSource,
    LocalKnowledgeScan,
)
from legal_workbench.domain.enums import (
    AuthorityStatus,
    AuthorityType,
    DocumentExtractionStatus,
    KnowledgeMetadataStatus,
)
from legal_workbench.domain.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    authority_role_for_type,
    normalize_knowledge_text,
)
from legal_workbench.integrations.local_knowledge_files import (
    LocalKnowledgeFile,
    scan_local_knowledge_files,
)


class LocalDocumentExtractor(Protocol):
    def extract(self, path: Path, mime_type: str) -> ExtractedDocument: ...


@dataclass(frozen=True, slots=True)
class _PreparedLocalExtraction:
    extraction_id: UUID
    document_version_id: UUID
    local_source_id: UUID
    path: Path = field(repr=False)
    mime_type: str = field(repr=False)
    relative_path: str
    display_name: str


class LocalKnowledgeImportService:
    """Incrementally persist a read-only local tree through Document and Knowledge."""

    def __init__(self, uow_factory: UnitOfWorkFactory, extractor: LocalDocumentExtractor) -> None:
        self._uow_factory = uow_factory
        self._extractor = extractor

    async def execute(
        self,
        *,
        source: Path,
        source_root_key: str,
        correlation_id: str,
    ) -> LocalKnowledgeScan:
        file_scan = scan_local_knowledge_files(source)
        scan = LocalKnowledgeScan(
            id=uuid4(),
            source_root_key=source_root_key,
            correlation_id=correlation_id,
            discovered_count=len(file_scan.files) + len(file_scan.failures),
            failed_count=len(file_scan.failures),
        )
        async with self._uow_factory() as uow:
            await uow.documents.add_local_scan(scan)
            await uow.commit()

        seen_paths: set[str] = set()
        for candidate in file_scan.files:
            seen_paths.add(candidate.relative_path)
            try:
                action, prepared = await self._prepare(scan, candidate)
                if action == "unchanged":
                    scan.unchanged_count += 1
                    continue
                if action == "unsupported":
                    scan.unsupported_count += 1
                    continue
                if action == "deduplicated":
                    scan.deduplicated_count += 1
                    continue
                if prepared is None:
                    raise RuntimeError("Local extraction preparation returned no work.")
                if await self._extract_and_register(prepared):
                    scan.imported_count += 1
                else:
                    scan.failed_count += 1
            except Exception:
                scan.failed_count += 1

        await self._finish_scan(scan, seen_paths)
        return scan

    async def _prepare(
        self,
        scan: LocalKnowledgeScan,
        candidate: LocalKnowledgeFile,
    ) -> tuple[str, _PreparedLocalExtraction | None]:
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation="local_knowledge_source",
                key=f"{scan.source_root_key}:{candidate.relative_path}",
            )
            source = await uow.documents.find_local_source(
                source_root_key=scan.source_root_key,
                relative_path=candidate.relative_path,
            )
            if source is None:
                source = LocalDocumentSource(
                    id=uuid4(),
                    source_root_key=scan.source_root_key,
                    relative_path=candidate.relative_path,
                    display_name=candidate.display_name,
                    last_seen_at=utc_now(),
                )
                await uow.documents.add_local_source(source)
                await uow.flush()
            else:
                source.display_name = candidate.display_name
                source.mark_seen()
                await uow.documents.save_local_source(source)

            latest = await uow.documents.find_latest_local_observation(source.id)
            if (
                candidate.supported
                and latest is not None
                and latest.content_sha256 == candidate.content_sha256
                and latest.document_version_id is not None
            ):
                await uow.documents.add_local_observation(
                    self._observation(scan.id, source.id, candidate, latest.document_version_id)
                )
                await uow.commit()
                return "unchanged", None

            if not candidate.supported:
                await uow.documents.add_local_observation(
                    self._observation(scan.id, source.id, candidate, None)
                )
                await uow.commit()
                return "unsupported", None

            canonical = await uow.documents.find_any_local_version_by_sha256(
                candidate.content_sha256
            )
            if canonical is not None:
                await uow.documents.add_local_observation(
                    self._observation(scan.id, source.id, candidate, canonical.id)
                )
                await uow.commit()
                return "deduplicated", None

            version = DocumentVersion(
                id=uuid4(),
                attachment_id=None,
                feishu_document_id=None,
                local_source_id=source.id,
                version=await uow.documents.next_local_version(source.id),
                content_sha256=candidate.content_sha256,
                file_name=candidate.display_name,
                mime_type=candidate.mime_type,
                size=candidate.size,
                local_path=str(candidate.absolute_path),
            )
            await uow.documents.add_version(version)
            await uow.flush()
            extraction = DocumentExtraction(
                id=uuid4(),
                document_version_id=version.id,
                status=DocumentExtractionStatus.EXTRACTING,
                extractor_version="pending",
            )
            await uow.documents.add_extraction(extraction)
            await uow.documents.add_local_observation(
                self._observation(scan.id, source.id, candidate, version.id)
            )
            await uow.commit()
        return (
            "extract",
            _PreparedLocalExtraction(
                extraction_id=extraction.id,
                document_version_id=version.id,
                local_source_id=source.id,
                path=candidate.absolute_path,
                mime_type=candidate.mime_type,
                relative_path=candidate.relative_path,
                display_name=candidate.display_name,
            ),
        )

    async def _extract_and_register(self, prepared: _PreparedLocalExtraction) -> bool:
        try:
            extracted = self._extractor.extract(prepared.path, prepared.mime_type)
        except Exception as exc:
            await self._fail_extraction(prepared.extraction_id, _safe_error_code(exc))
            return False
        if extracted.status == DocumentExtractionStatus.FAILED:
            await self._fail_extraction(
                prepared.extraction_id,
                extracted.error_code or "DOCUMENT_EXTRACTION_FAILED",
            )
            return False

        async with self._uow_factory() as uow:
            extraction = await uow.documents.get_extraction_for_update(prepared.extraction_id)
            if extraction is None:
                return False
            extraction.complete(extracted)
            segments = [
                DocumentSegment.from_extracted(
                    extraction_id=extraction.id,
                    attachment_id=None,
                    local_source_id=prepared.local_source_id,
                    segment=value,
                )
                for value in extracted.segments
            ]
            if segments:
                await uow.documents.add_segments(segments)
            await uow.documents.save_extraction(extraction)
            if not segments or extracted.status != DocumentExtractionStatus.SUCCEEDED:
                await uow.commit()
                return False
            await self._register_knowledge(
                uow,
                prepared=prepared,
                segments=segments,
            )
            await uow.commit()
        return True

    async def _register_knowledge(
        self,
        uow: UnitOfWork,
        *,
        prepared: _PreparedLocalExtraction,
        segments: list[DocumentSegment],
    ) -> None:
        source_type = "document_version"
        source_id = str(prepared.document_version_id)
        existing = await uow.knowledge.find_document_by_source(
            source_type=source_type,
            source_id=source_id,
        )
        if existing is not None:
            return
        authority_type = infer_authority_type(prepared.relative_path)
        authority_role = authority_role_for_type(authority_type)
        known = authority_type != AuthorityType.UNKNOWN
        document = KnowledgeDocument(
            id=uuid4(),
            source_type=source_type,
            source_id=source_id,
            document_version_id=prepared.document_version_id,
            title=PurePosixPath(prepared.display_name).stem,
            document_type=authority_type.value if known else "unknown",
            agent_types=[
                "legal_consultation",
                "contract_review",
                "dispute_complaint",
                "ip_copyright",
                "labor_employment",
            ],
            matter_types=[
                "contract",
                "copy_review",
                "employment",
                "dispute",
                "intellectual_property",
                "platform_rules",
                "general_consultation",
            ],
            jurisdiction="CN" if known else "unknown",
            source_priority=_source_priority(authority_type),
            internal_precedent=authority_type == AuthorityType.INTERNAL_PRECEDENT,
            confidentiality="internal",
            authority_type=authority_type,
            authority_role=authority_role,
            authority_status=AuthorityStatus.EFFECTIVE if known else AuthorityStatus.UNKNOWN,
            metadata_status=(
                KnowledgeMetadataStatus.READY
                if known
                else KnowledgeMetadataStatus.PENDING_METADATA
            ),
        )
        chunks = [
            KnowledgeChunk(
                id=uuid4(),
                knowledge_document_id=document.id,
                document_segment_id=segment.id,
                sequence=index,
                locator=_segment_locator(segment),
                text=segment.content,
                normalized_text=normalize_knowledge_text(segment.content),
                text_hash=segment.content_hash,
            )
            for index, segment in enumerate(segments, start=1)
        ]
        await uow.knowledge.add_document(document)
        await uow.flush()
        await uow.knowledge.add_chunks(chunks)

    async def _fail_extraction(self, extraction_id: UUID, error_code: str) -> None:
        async with self._uow_factory() as uow:
            extraction = await uow.documents.get_extraction_for_update(extraction_id)
            if extraction is None:
                return
            extraction.fail(error_code)
            await uow.documents.save_extraction(extraction)
            await uow.commit()

    async def _finish_scan(self, scan: LocalKnowledgeScan, seen_paths: set[str]) -> None:
        async with self._uow_factory() as uow:
            sources = await uow.documents.list_local_sources(
                source_root_key=scan.source_root_key
            )
            for source in sources:
                if source.relative_path in seen_paths:
                    continue
                previous_status = source.status
                source.mark_missing()
                if source.status != previous_status:
                    scan.missing_count += 1
                    await uow.documents.save_local_source(source)
            scan.finish()
            await uow.documents.save_local_scan(scan)
            await uow.commit()

    @staticmethod
    def _observation(
        scan_id: UUID,
        local_source_id: UUID,
        candidate: LocalKnowledgeFile,
        document_version_id: UUID | None,
    ) -> LocalDocumentObservation:
        return LocalDocumentObservation(
            id=uuid4(),
            local_source_id=local_source_id,
            scan_id=scan_id,
            document_version_id=document_version_id,
            content_sha256=candidate.content_sha256,
            size=candidate.size,
            modified_at_ns=candidate.modified_at_ns,
        )


AUTHORITY_PATH_MARKERS: tuple[tuple[AuthorityType, tuple[str, ...]], ...] = (
    (AuthorityType.JUDICIAL_INTERPRETATION, ("司法解释",)),
    (AuthorityType.ADMINISTRATIVE_REGULATION, ("行政法规",)),
    (AuthorityType.DEPARTMENT_RULE, ("部门规章",)),
    (AuthorityType.LOCAL_REGULATION, ("地方性法规",)),
    (AuthorityType.LOCAL_GOVERNMENT_RULE, ("地方政府规章",)),
    (AuthorityType.NORMATIVE_DOCUMENT, ("规范性文件",)),
    (AuthorityType.GUIDING_CASE, ("指导案例", "指导性案例")),
    (AuthorityType.COURT_CASE, ("裁判文书", "法院案例")),
    (AuthorityType.REGULATORY_GUIDANCE, ("监管指引", "监管指导")),
    (AuthorityType.CONTRACT, ("合同", "协议")),
    (AuthorityType.COMPANY_POLICY, ("公司制度", "规章制度")),
    (AuthorityType.BUSINESS_RULE, ("业务规则", "业务制度")),
    (AuthorityType.LEGAL_OPINION, ("法律意见", "法务意见")),
    (AuthorityType.INTERNAL_PRECEDENT, ("内部先例", "历史处理")),
    (AuthorityType.LAW, ("法律/", "/法律/", "法律\\")),
)


def infer_authority_type(relative_path: str) -> AuthorityType:
    normalized = f"/{relative_path.replace('\\', '/')}"
    for authority_type, markers in AUTHORITY_PATH_MARKERS:
        if any(marker in normalized for marker in markers):
            return authority_type
    return AuthorityType.UNKNOWN


def _source_priority(authority_type: AuthorityType) -> int:
    if authority_type in {
        AuthorityType.LAW,
        AuthorityType.ADMINISTRATIVE_REGULATION,
        AuthorityType.JUDICIAL_INTERPRETATION,
        AuthorityType.DEPARTMENT_RULE,
        AuthorityType.LOCAL_REGULATION,
        AuthorityType.LOCAL_GOVERNMENT_RULE,
        AuthorityType.NORMATIVE_DOCUMENT,
    }:
        return 100
    if authority_type in {
        AuthorityType.GUIDING_CASE,
        AuthorityType.COURT_CASE,
        AuthorityType.REGULATORY_GUIDANCE,
        AuthorityType.CONTRACT,
    }:
        return 80
    if authority_type in {AuthorityType.COMPANY_POLICY, AuthorityType.BUSINESS_RULE}:
        return 60
    if authority_type in {AuthorityType.LEGAL_OPINION, AuthorityType.INTERNAL_PRECEDENT}:
        return 40
    return 20


def _segment_locator(segment: DocumentSegment) -> str:
    page = f"第{segment.page_number}页" if segment.page_number is not None else ""
    return f"{page}第{segment.paragraph_number}段"


def _safe_error_code(exc: Exception) -> str:
    candidate = getattr(exc, "code", "DOCUMENT_EXTRACTION_FAILED")
    if not isinstance(candidate, str) or not candidate.isascii():
        return "DOCUMENT_EXTRACTION_FAILED"
    normalized = candidate.strip().upper()
    if not normalized or len(normalized) > 100:
        return "DOCUMENT_EXTRACTION_FAILED"
    return normalized
