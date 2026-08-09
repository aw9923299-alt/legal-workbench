from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID, uuid4

from legal_workbench.application.ports import UnitOfWork, UnitOfWorkFactory
from legal_workbench.application.token_budget import (
    PROVISIONAL_DEFAULT_KNOWLEDGE_BUDGET,
    DeterministicTokenEstimator,
    split_text_for_token_budget,
)
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
    authority_priority_for_type,
    authority_role_for_type,
    normalize_knowledge_text,
)
from legal_workbench.integrations.local_knowledge_files import (
    LocalKnowledgeFile,
    LocalKnowledgeFileChangedError,
    fingerprint_local_knowledge_file,
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
    expected_sha256: str
    expected_size: int
    expected_modified_at_ns: int


class LocalKnowledgeImportService:
    """Incrementally persist a read-only local tree through Document and Knowledge."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        extractor: LocalDocumentExtractor,
        *,
        max_single_chunk_tokens: int = (
            PROVISIONAL_DEFAULT_KNOWLEDGE_BUDGET.max_single_chunk_tokens
        ),
    ) -> None:
        self._uow_factory = uow_factory
        self._extractor = extractor
        self._token_estimator = DeterministicTokenEstimator()
        if max_single_chunk_tokens < 1:
            raise ValueError("Knowledge single-Chunk token limit must be positive.")
        self._max_single_chunk_tokens = max_single_chunk_tokens

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
                and await self._version_is_searchable(uow, latest.document_version_id)
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
            if canonical is not None and await self._version_is_searchable(
                uow, canonical.id
            ):
                await uow.documents.add_local_observation(
                    self._observation(scan.id, source.id, candidate, canonical.id)
                )
                await uow.commit()
                return "deduplicated", None

            retry_version = None
            if (
                latest is not None
                and latest.content_sha256 == candidate.content_sha256
                and latest.document_version_id is not None
            ):
                retry_version = await uow.documents.get_version(
                    latest.document_version_id
                )
            if retry_version is None:
                retry_version = canonical

            if retry_version is not None:
                if retry_version.local_source_id is None:
                    raise RuntimeError("Local content hash resolved to a non-local version.")
                extraction = DocumentExtraction(
                    id=uuid4(),
                    document_version_id=retry_version.id,
                    status=DocumentExtractionStatus.EXTRACTING,
                    extractor_version="pending",
                )
                await uow.documents.add_extraction(extraction)
                await uow.documents.add_local_observation(
                    self._observation(
                        scan.id,
                        source.id,
                        candidate,
                        retry_version.id,
                    )
                )
                await uow.commit()
                return "extract", self._prepared(
                    candidate,
                    extraction_id=extraction.id,
                    document_version_id=retry_version.id,
                    local_source_id=retry_version.local_source_id,
                )

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
            self._prepared(
                candidate,
                extraction_id=extraction.id,
                document_version_id=version.id,
                local_source_id=source.id,
            ),
        )

    async def _extract_and_register(self, prepared: _PreparedLocalExtraction) -> bool:
        if not self._source_matches_prepared(prepared):
            await self._fail_extraction(
                prepared.extraction_id, "LOCAL_SOURCE_CHANGED_DURING_IMPORT"
            )
            return False
        try:
            extracted = self._extractor.extract(prepared.path, prepared.mime_type)
        except Exception as exc:
            await self._fail_extraction(prepared.extraction_id, _safe_error_code(exc))
            return False
        if not self._source_matches_prepared(prepared):
            await self._fail_extraction(
                prepared.extraction_id, "LOCAL_SOURCE_CHANGED_DURING_IMPORT"
            )
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
            source_priority=authority_priority_for_type(authority_type),
            internal_precedent=authority_type == AuthorityType.INTERNAL_PRECEDENT,
            confidentiality="internal",
            authority_type=authority_type,
            authority_role=authority_role,
            authority_status=AuthorityStatus.UNKNOWN,
            metadata_status=KnowledgeMetadataStatus.PENDING_METADATA,
        )
        chunks: list[KnowledgeChunk] = []
        for segment in segments:
            pieces = split_text_for_token_budget(
                segment.content,
                max_tokens=self._max_single_chunk_tokens,
                estimator=self._token_estimator,
            )
            for piece in pieces:
                locator = _segment_locator(segment)
                if len(pieces) > 1:
                    locator = (
                        f"{locator} chars:{segment.start_offset + piece.start_offset}-"
                        f"{segment.start_offset + piece.end_offset}"
                    )
                chunks.append(
                    KnowledgeChunk(
                        id=uuid4(),
                        knowledge_document_id=document.id,
                        document_segment_id=segment.id,
                        sequence=len(chunks) + 1,
                        locator=locator,
                        text=piece.text,
                        normalized_text=normalize_knowledge_text(piece.text),
                        text_hash=sha256(piece.text.encode("utf-8")).hexdigest(),
                        estimated_token_count=piece.estimated_token_count,
                        token_estimator=self._token_estimator.method,
                    )
                )
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

    async def _version_is_searchable(
        self,
        uow: UnitOfWork,
        document_version_id: UUID,
    ) -> bool:
        segments = await uow.documents.list_segments_for_version(document_version_id)
        if not segments:
            return False
        return (
            await uow.knowledge.find_document_by_source(
                source_type="document_version",
                source_id=str(document_version_id),
            )
            is not None
        )

    @staticmethod
    def _prepared(
        candidate: LocalKnowledgeFile,
        *,
        extraction_id: UUID,
        document_version_id: UUID,
        local_source_id: UUID,
    ) -> _PreparedLocalExtraction:
        return _PreparedLocalExtraction(
            extraction_id=extraction_id,
            document_version_id=document_version_id,
            local_source_id=local_source_id,
            path=candidate.absolute_path,
            mime_type=candidate.mime_type,
            relative_path=candidate.relative_path,
            display_name=candidate.display_name,
            expected_sha256=candidate.content_sha256,
            expected_size=candidate.size,
            expected_modified_at_ns=candidate.modified_at_ns,
        )

    @staticmethod
    def _source_matches_prepared(prepared: _PreparedLocalExtraction) -> bool:
        try:
            digest, size, modified_at_ns = fingerprint_local_knowledge_file(
                prepared.path
            )
        except (OSError, ValueError, LocalKnowledgeFileChangedError):
            return False
        return (
            digest == prepared.expected_sha256
            and size == prepared.expected_size
            and modified_at_ns == prepared.expected_modified_at_ns
        )

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


AUTHORITY_DIRECTORY_MARKERS: dict[str, AuthorityType] = {
    "法律": AuthorityType.LAW,
    "司法解释": AuthorityType.JUDICIAL_INTERPRETATION,
    "行政法规": AuthorityType.ADMINISTRATIVE_REGULATION,
    "部门规章": AuthorityType.DEPARTMENT_RULE,
    "地方性法规": AuthorityType.LOCAL_REGULATION,
    "地方政府规章": AuthorityType.LOCAL_GOVERNMENT_RULE,
    "规范性文件": AuthorityType.NORMATIVE_DOCUMENT,
    "指导案例": AuthorityType.GUIDING_CASE,
    "指导性案例": AuthorityType.GUIDING_CASE,
    "裁判文书": AuthorityType.COURT_CASE,
    "法院案例": AuthorityType.COURT_CASE,
    "监管指引": AuthorityType.REGULATORY_GUIDANCE,
    "监管指导": AuthorityType.REGULATORY_GUIDANCE,
    "合同": AuthorityType.CONTRACT,
    "协议": AuthorityType.CONTRACT,
    "公司制度": AuthorityType.COMPANY_POLICY,
    "规章制度": AuthorityType.COMPANY_POLICY,
    "业务规则": AuthorityType.BUSINESS_RULE,
    "业务制度": AuthorityType.BUSINESS_RULE,
    "法律意见": AuthorityType.LEGAL_OPINION,
    "法务意见": AuthorityType.LEGAL_OPINION,
    "内部先例": AuthorityType.INTERNAL_PRECEDENT,
    "历史处理": AuthorityType.INTERNAL_PRECEDENT,
}


def infer_authority_type(relative_path: str) -> AuthorityType:
    path = PurePosixPath(relative_path.replace("\\", "/"))
    matches = {
        AUTHORITY_DIRECTORY_MARKERS[part.strip()]
        for part in path.parts[:-1]
        if part.strip() in AUTHORITY_DIRECTORY_MARKERS
    }
    return matches.pop() if len(matches) == 1 else AuthorityType.UNKNOWN


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
