from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.local_knowledge_import import (
    LocalKnowledgeImportService,
    infer_authority_type,
)
from legal_workbench.domain.documents import (
    DocumentExtraction,
    DocumentSegment,
    DocumentVersion,
    ExtractedDocument,
    ExtractedSegment,
    LocalDocumentObservation,
    LocalDocumentSource,
    LocalKnowledgeScan,
)
from legal_workbench.domain.enums import (
    AuthorityStatus,
    AuthorityType,
    DocumentExtractionStatus,
    KnowledgeMetadataStatus,
    LocalDocumentSourceStatus,
)
from legal_workbench.domain.knowledge import KnowledgeChunk, KnowledgeDocument
from legal_workbench.integrations.local_knowledge_files import scan_local_knowledge_files


class _Extractor:
    def __init__(self, *, failing_names: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.failing_names = failing_names or set()

    def extract(self, path: Path, mime_type: str) -> ExtractedDocument:
        self.calls.append(path.name)
        if path.name in self.failing_names:
            raise ValueError("sensitive source body must not escape")
        content = path.read_text(encoding="utf-8")
        segment = ExtractedSegment(
            page_number=None,
            paragraph_number=1,
            start_offset=0,
            end_offset=len(content),
            content=content,
            content_hash=__import__("hashlib").sha256(content.encode()).hexdigest(),
        )
        return ExtractedDocument(
            status=DocumentExtractionStatus.SUCCEEDED,
            segments=(segment,),
            page_count=None,
            character_count=len(content),
        )


class _Documents:
    def __init__(self) -> None:
        self.scans: dict[UUID, LocalKnowledgeScan] = {}
        self.sources: dict[tuple[str, str], LocalDocumentSource] = {}
        self.observations: list[LocalDocumentObservation] = []
        self.versions: dict[UUID, DocumentVersion] = {}
        self.extractions: dict[UUID, DocumentExtraction] = {}
        self.segments: list[DocumentSegment] = []

    async def add_local_scan(self, scan: LocalKnowledgeScan) -> None:
        self.scans[scan.id] = scan

    async def save_local_scan(self, scan: LocalKnowledgeScan) -> None:
        self.scans[scan.id] = scan

    async def find_local_source(
        self, *, source_root_key: str, relative_path: str
    ) -> LocalDocumentSource | None:
        return self.sources.get((source_root_key, relative_path))

    async def list_local_sources(
        self, *, source_root_key: str
    ) -> Sequence[LocalDocumentSource]:
        return [value for (root, _), value in self.sources.items() if root == source_root_key]

    async def add_local_source(self, source: LocalDocumentSource) -> None:
        self.sources[(source.source_root_key, source.relative_path)] = source

    async def save_local_source(self, source: LocalDocumentSource) -> None:
        self.sources[(source.source_root_key, source.relative_path)] = source

    async def add_local_observation(self, observation: LocalDocumentObservation) -> None:
        self.observations.append(observation)

    async def find_latest_local_observation(
        self, local_source_id: UUID
    ) -> LocalDocumentObservation | None:
        values = [v for v in self.observations if v.local_source_id == local_source_id]
        return values[-1] if values else None

    async def find_any_local_version_by_sha256(
        self, content_sha256: str
    ) -> DocumentVersion | None:
        return next(
            (value for value in self.versions.values() if value.content_sha256 == content_sha256),
            None,
        )

    async def find_local_version(
        self, *, local_source_id: UUID, content_sha256: str
    ) -> DocumentVersion | None:
        return next(
            (
                value
                for value in self.versions.values()
                if value.local_source_id == local_source_id
                and value.content_sha256 == content_sha256
            ),
            None,
        )

    async def next_local_version(self, local_source_id: UUID) -> int:
        return 1 + max(
            (
                value.version
                for value in self.versions.values()
                if value.local_source_id == local_source_id
            ),
            default=0,
        )

    async def add_version(self, version: DocumentVersion) -> None:
        self.versions[version.id] = version

    async def add_extraction(self, extraction: DocumentExtraction) -> None:
        self.extractions[extraction.id] = extraction

    async def find_latest_extraction(
        self, document_version_id: UUID
    ) -> DocumentExtraction | None:
        values = [
            value
            for value in self.extractions.values()
            if value.document_version_id == document_version_id
        ]
        return values[-1] if values else None

    async def get_extraction_for_update(self, extraction_id: UUID) -> DocumentExtraction | None:
        return self.extractions.get(extraction_id)

    async def save_extraction(self, extraction: DocumentExtraction) -> None:
        self.extractions[extraction.id] = extraction

    async def get_version(self, version_id: UUID) -> DocumentVersion | None:
        return self.versions.get(version_id)

    async def add_segments(self, segments: Sequence[DocumentSegment]) -> None:
        self.segments.extend(segments)

    async def list_segments_for_version(
        self, document_version_id: UUID
    ) -> Sequence[DocumentSegment]:
        extraction_ids = {
            value.id
            for value in self.extractions.values()
            if value.document_version_id == document_version_id
            and value.status == DocumentExtractionStatus.SUCCEEDED
        }
        return [value for value in self.segments if value.extraction_id in extraction_ids]


class _Knowledge:
    def __init__(self) -> None:
        self.documents: list[KnowledgeDocument] = []
        self.chunks: list[KnowledgeChunk] = []

    async def find_document_by_source(
        self, *, source_type: str, source_id: str
    ) -> KnowledgeDocument | None:
        return next(
            (
                value
                for value in self.documents
                if value.source_type == source_type and value.source_id == source_id
            ),
            None,
        )

    async def add_document(self, document: KnowledgeDocument) -> None:
        self.documents.append(document)

    async def add_chunks(self, chunks: Sequence[KnowledgeChunk]) -> None:
        self.chunks.extend(chunks)


class _UnitOfWork:
    def __init__(self, documents: _Documents, knowledge: _Knowledge) -> None:
        self.documents = documents
        self.knowledge = knowledge

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


class _UnitOfWorkFactory:
    def __init__(self) -> None:
        self.documents = _Documents()
        self.knowledge = _Knowledge()

    def __call__(self) -> _UnitOfWork:
        return _UnitOfWork(self.documents, self.knowledge)


@pytest.mark.asyncio
async def test_incremental_import_deduplicates_versions_and_preserves_missing_history(
    tmp_path: Path,
) -> None:
    source = tmp_path / "materials"
    source.mkdir()
    first = source / "法律" / "中华人民共和国测试法.txt"
    first.parent.mkdir()
    first.write_text("same content", encoding="utf-8")
    duplicate = source / "copy.txt"
    duplicate.write_text("same content", encoding="utf-8")
    uow = _UnitOfWorkFactory()
    extractor = _Extractor()
    service = LocalKnowledgeImportService(uow, extractor)

    initial = await service.execute(
        source=source,
        source_root_key="codex_obs_legal",
        correlation_id="scan-1",
    )
    repeated = await service.execute(
        source=source,
        source_root_key="codex_obs_legal",
        correlation_id="scan-2",
    )
    first.write_text("changed content", encoding="utf-8")
    changed = await service.execute(
        source=source,
        source_root_key="codex_obs_legal",
        correlation_id="scan-3",
    )
    duplicate.unlink()
    missing = await service.execute(
        source=source,
        source_root_key="codex_obs_legal",
        correlation_id="scan-4",
    )

    assert (initial.imported_count, initial.deduplicated_count) == (1, 1)
    assert repeated.unchanged_count == 2
    assert changed.imported_count == 1
    assert extractor.calls == ["copy.txt", "中华人民共和国测试法.txt"]
    assert len(uow.documents.versions) == 2
    assert len(uow.knowledge.documents) == 2
    assert missing.missing_count == 1
    assert uow.documents.sources[("codex_obs_legal", "copy.txt")].status == (
        LocalDocumentSourceStatus.MISSING
    )
    assert len(uow.documents.observations) == 7


@pytest.mark.asyncio
async def test_parse_failure_isolated_and_source_body_is_not_returned(tmp_path: Path) -> None:
    source = tmp_path / "materials"
    source.mkdir()
    (source / "bad.txt").write_text("sensitive bad body", encoding="utf-8")
    (source / "good.txt").write_text("safe body", encoding="utf-8")
    (source / "unsupported.xlsx").write_bytes(b"sheet")
    uow = _UnitOfWorkFactory()
    service = LocalKnowledgeImportService(uow, _Extractor(failing_names={"bad.txt"}))

    result = await service.execute(
        source=source,
        source_root_key="codex_obs_legal",
        correlation_id="scan-partial",
    )

    assert result.failed_count == 1
    assert result.imported_count == 1
    assert result.unsupported_count == 1
    assert result.status.value == "partial"
    assert "sensitive bad body" not in repr(result)
    assert len(uow.knowledge.documents) == 1


@pytest.mark.asyncio
async def test_failed_and_interrupted_extractions_are_retried_without_new_version(
    tmp_path: Path,
) -> None:
    source = tmp_path / "materials"
    source.mkdir()
    document = source / "retry.txt"
    document.write_text("retryable content", encoding="utf-8")
    uow = _UnitOfWorkFactory()
    failing = LocalKnowledgeImportService(
        uow, _Extractor(failing_names={"retry.txt"})
    )

    failed = await failing.execute(
        source=source,
        source_root_key="codex_obs_legal",
        correlation_id="scan-failed",
    )
    recovered = await LocalKnowledgeImportService(uow, _Extractor()).execute(
        source=source,
        source_root_key="codex_obs_legal",
        correlation_id="scan-recovered",
    )

    assert failed.failed_count == 1
    assert recovered.imported_count == 1
    assert recovered.unchanged_count == 0
    assert len(uow.documents.versions) == 1
    assert len(uow.documents.extractions) == 2
    assert len(uow.knowledge.documents) == 1

    second = source / "interrupted.txt"
    second.write_text("interrupted content", encoding="utf-8")
    candidate = next(
        value
        for value in scan_local_knowledge_files(source).files
        if value.relative_path == "interrupted.txt"
    )
    interrupted_scan = LocalKnowledgeScan(
        id=uuid4(),
        source_root_key="codex_obs_legal",
        correlation_id="prepare-only",
    )
    async with uow() as unit:
        await unit.documents.add_local_scan(interrupted_scan)
    action, _prepared = await LocalKnowledgeImportService(uow, _Extractor())._prepare(
        interrupted_scan, candidate
    )
    assert action == "extract"

    after_crash = await LocalKnowledgeImportService(uow, _Extractor()).execute(
        source=source,
        source_root_key="codex_obs_legal",
        correlation_id="scan-after-crash",
    )

    assert after_crash.imported_count == 1
    interrupted_versions = [
        value
        for value in uow.documents.versions.values()
        if value.file_name == "interrupted.txt"
    ]
    assert len(interrupted_versions) == 1
    assert len(
        [
            value
            for value in uow.documents.extractions.values()
            if value.document_version_id == interrupted_versions[0].id
        ]
    ) == 2


@pytest.mark.asyncio
async def test_failed_canonical_content_is_not_treated_as_deduplicated(
    tmp_path: Path,
) -> None:
    source = tmp_path / "materials"
    source.mkdir()
    (source / "a-fails.txt").write_text("shared content", encoding="utf-8")
    (source / "b-recovers.txt").write_text("shared content", encoding="utf-8")
    uow = _UnitOfWorkFactory()

    result = await LocalKnowledgeImportService(
        uow,
        _Extractor(failing_names={"a-fails.txt"}),
    ).execute(
        source=source,
        source_root_key="codex_obs_legal",
        correlation_id="scan-dedup-retry",
    )

    assert result.failed_count == 1
    assert result.imported_count == 1
    assert result.deduplicated_count == 0
    assert len(uow.documents.versions) == 1
    assert len(uow.knowledge.documents) == 1


@pytest.mark.asyncio
async def test_import_rejects_file_changed_after_scan(tmp_path: Path) -> None:
    class _MutatingExtractor(_Extractor):
        def extract(self, path: Path, mime_type: str) -> ExtractedDocument:
            result = super().extract(path, mime_type)
            path.write_text("changed during import", encoding="utf-8")
            return result

    source = tmp_path / "materials"
    source.mkdir()
    (source / "race.txt").write_text("original content", encoding="utf-8")
    uow = _UnitOfWorkFactory()

    result = await LocalKnowledgeImportService(uow, _MutatingExtractor()).execute(
        source=source,
        source_root_key="codex_obs_legal",
        correlation_id="scan-race",
    )

    assert result.failed_count == 1
    assert not uow.knowledge.documents
    assert next(iter(uow.documents.extractions.values())).error_code == (
        "LOCAL_SOURCE_CHANGED_DURING_IMPORT"
    )


@pytest.mark.asyncio
async def test_import_splits_oversized_segments_with_traceable_locators(
    tmp_path: Path,
) -> None:
    source = tmp_path / "materials" / "法律"
    source.mkdir(parents=True)
    content = "超长法律段落。" * 100
    (source / "测试法.txt").write_text(content, encoding="utf-8")
    uow = _UnitOfWorkFactory()

    result = await LocalKnowledgeImportService(
        uow,
        _Extractor(),
        max_single_chunk_tokens=20,
    ).execute(
        source=source.parent,
        source_root_key="codex_obs_legal",
        correlation_id="scan-split",
    )

    assert result.imported_count == 1
    assert len(uow.knowledge.chunks) > 1
    assert all(value.estimated_token_count <= 20 for value in uow.knowledge.chunks)
    assert "".join(value.text for value in uow.knowledge.chunks) == content
    assert all("chars:" in value.locator for value in uow.knowledge.chunks)


def test_authority_inference_uses_unambiguous_directory_segments_only() -> None:
    assert infer_authority_type(
        "法律/中华人民共和国劳动合同法.txt"
    ) == AuthorityType.LAW
    assert infer_authority_type("公司制度/合同审批制度.md") == AuthorityType.COMPANY_POLICY
    assert infer_authority_type("法律/合同/冲突资料.txt") == AuthorityType.UNKNOWN


@pytest.mark.asyncio
async def test_inferred_authority_stays_pending_until_effectiveness_is_confirmed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "materials" / "法律"
    source.mkdir(parents=True)
    (source / "测试法.txt").write_text("法律正文", encoding="utf-8")
    uow = _UnitOfWorkFactory()

    await LocalKnowledgeImportService(uow, _Extractor()).execute(
        source=source.parent,
        source_root_key="codex_obs_legal",
        correlation_id="scan-authority-pending",
    )

    document = uow.knowledge.documents[0]
    assert document.authority_type == AuthorityType.LAW
    assert document.authority_status == AuthorityStatus.UNKNOWN
    assert document.metadata_status == KnowledgeMetadataStatus.PENDING_METADATA
