from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import TracebackType
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from legal_workbench.application.document_extraction import DocumentExtractionService
from legal_workbench.domain.entities import (
    DocumentExtraction,
    DocumentSegment,
    DocumentVersion,
    MessageAttachment,
    OutboxEvent,
)
from legal_workbench.domain.enums import AttachmentDownloadStatus, DocumentExtractionStatus
from legal_workbench.integrations.document_extractors import (
    AttachmentPathPolicy,
    AttachmentTooLargeError,
    ExtractedDocument,
    ExtractedSegment,
    ExtractionProcessTimeoutError,
    StorageQuotaExceededError,
    StorageQuotaPolicy,
    UnsafeAttachmentPathError,
    extract_document,
    sanitize_attachment_filename,
)

FIXTURES = Path(__file__).parent / "fixtures" / "documents"


def _write_minimal_docx(path: Path) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
</Relationships>"""
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>第一段 DOCX 文本。</w:t></w:r></w:p>
    <w:p><w:r><w:t>第二段 DOCX 文本。</w:t></w:r></w:p>
    <w:sectPr/>
  </w:body>
</w:document>"""
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", relationships)
        package.writestr("word/document.xml", document)


def test_attachment_path_must_remain_below_root(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    root.mkdir()
    policy = AttachmentPathPolicy(root, max_file_bytes=1024)

    with pytest.raises(UnsafeAttachmentPathError):
        policy.authorize(root / ".." / "secret.txt")


def test_attachment_symlink_cannot_escape_root(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not authorized", encoding="utf-8")
    link = root / "link.txt"
    link.symlink_to(outside)

    with pytest.raises(UnsafeAttachmentPathError):
        AttachmentPathPolicy(root, max_file_bytes=1024).authorize(link)


def test_oversized_attachment_is_rejected_before_parsing(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    root.mkdir()
    document = root / "large.txt"
    document.write_bytes(b"12345")

    with pytest.raises(AttachmentTooLargeError):
        AttachmentPathPolicy(root, max_file_bytes=4).authorize(document)


def test_total_quota_counts_used_and_reserved_bytes() -> None:
    policy = StorageQuotaPolicy(total_bytes=10)

    with pytest.raises(StorageQuotaExceededError):
        policy.ensure_available(used_bytes=7, reserved_bytes=2, incoming_bytes=2)


def test_filename_is_reduced_to_safe_basename() -> None:
    assert sanitize_attachment_filename("../../合同<script>.docx") == "合同_script_.docx"


@pytest.mark.parametrize(
    ("fixture_name", "mime_type", "first_content"),
    [
        ("sample.txt", "text/plain", "第一段测试文本。"),
        ("sample.md", "text/markdown", "# 测试标题"),
    ],
)
def test_plain_text_formats_produce_deterministic_segments(
    fixture_name: str,
    mime_type: str,
    first_content: str,
) -> None:
    result = extract_document(FIXTURES / fixture_name, mime_type)

    assert result.status == DocumentExtractionStatus.SUCCEEDED
    assert result.segments[0].content == first_content
    assert result.segments[0].paragraph_number == 1
    assert result.segments[0].start_offset == 0
    assert result.segments[0].end_offset == len(first_content)
    assert len(result.segments[0].content_hash) == 64


def test_docx_reads_paragraph_text_without_running_macros(tmp_path: Path) -> None:
    document = tmp_path / "sample.docx"
    _write_minimal_docx(document)

    result = extract_document(
        document,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert result.status == DocumentExtractionStatus.SUCCEEDED
    assert [segment.content for segment in result.segments] == [
        "第一段 DOCX 文本。",
        "第二段 DOCX 文本。",
    ]


def test_blank_pdf_is_body_unavailable(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    document = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with document.open("wb") as stream:
        writer.write(stream)

    result = extract_document(document, "application/pdf")

    assert result.status == DocumentExtractionStatus.BODY_UNAVAILABLE
    assert result.page_count == 1
    assert result.segments == ()
    assert result.error_code == "DOCUMENT_BODY_UNAVAILABLE"


def test_macro_enabled_document_is_never_opened(tmp_path: Path) -> None:
    document = tmp_path / "unsafe.docm"
    document.write_bytes(b"not a trusted document")
    marker = tmp_path / "macro-ran"

    result = extract_document(
        document,
        "application/vnd.ms-word.document.macroenabled.12",
    )

    assert result.status == DocumentExtractionStatus.BODY_UNAVAILABLE
    assert result.error_code == "UNSUPPORTED_DOCUMENT_FORMAT"
    assert marker.exists() is False


class _AttachmentRepository:
    def __init__(self, state: _ExtractionState) -> None:
        self._state = state

    async def get_attachment_for_update(self, attachment_id: UUID) -> MessageAttachment | None:
        return self._state.attachments.get(attachment_id)

    async def save_attachment(self, attachment: MessageAttachment) -> None:
        self._state.attachments[attachment.id] = attachment

    async def list_attachments(self, message_id: UUID) -> tuple[MessageAttachment, ...]:
        return tuple(
            value
            for value in self._state.attachments.values()
            if value.feishu_message_id == message_id
        )

    async def get_message_by_id(self, message_id: UUID) -> None:
        del message_id
        return None


class _OutboxRepository:
    def __init__(self, state: _ExtractionState) -> None:
        self._state = state

    async def add(self, event: OutboxEvent) -> None:
        self._state.outbox_events.append(event)

    async def exists_pending(self, *, event_type: str, aggregate_id: UUID) -> bool:
        return any(
            value.event_type == event_type and value.aggregate_id == aggregate_id
            for value in self._state.outbox_events
        )


class _DocumentRepository:
    def __init__(self, state: _ExtractionState) -> None:
        self._state = state

    async def find_version(
        self, *, attachment_id: UUID, content_sha256: str
    ) -> DocumentVersion | None:
        return next(
            (
                value
                for value in self._state.versions.values()
                if value.attachment_id == attachment_id and value.content_sha256 == content_sha256
            ),
            None,
        )

    async def next_version(self, attachment_id: UUID) -> int:
        return (
            max(
                (
                    value.version
                    for value in self._state.versions.values()
                    if value.attachment_id == attachment_id
                ),
                default=0,
            )
            + 1
        )

    async def add_version(self, version: DocumentVersion) -> None:
        self._state.versions[version.id] = version

    async def add_extraction(self, extraction: DocumentExtraction) -> None:
        self._state.extractions[extraction.id] = extraction

    async def find_latest_extraction(
        self, document_version_id: UUID
    ) -> DocumentExtraction | None:
        return next(
            (
                value
                for value in reversed(tuple(self._state.extractions.values()))
                if value.document_version_id == document_version_id
            ),
            None,
        )

    async def get_extraction_for_update(self, extraction_id: UUID) -> DocumentExtraction | None:
        return self._state.extractions.get(extraction_id)

    async def get_version(self, version_id: UUID) -> DocumentVersion | None:
        return self._state.versions.get(version_id)

    async def save_extraction(self, extraction: DocumentExtraction) -> None:
        self._state.extractions[extraction.id] = extraction

    async def add_segments(self, segments: tuple[DocumentSegment, ...]) -> None:
        self._state.segments.extend(segments)


class _ExtractionUnitOfWork:
    def __init__(self, state: _ExtractionState) -> None:
        self._state = state
        self.feishu = _AttachmentRepository(state)
        self.documents = _DocumentRepository(state)
        self.outbox_events = _OutboxRepository(state)

    async def __aenter__(self) -> _ExtractionUnitOfWork:
        self._state.active_uows += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._state.active_uows -= 1

    async def commit(self) -> None:
        self._state.commits += 1

    async def flush(self) -> None:
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        del operation, key


class _ExtractionState:
    def __init__(self) -> None:
        self.attachments: dict[UUID, MessageAttachment] = {}
        self.versions: dict[UUID, DocumentVersion] = {}
        self.extractions: dict[UUID, DocumentExtraction] = {}
        self.segments: list[DocumentSegment] = []
        self.outbox_events: list[OutboxEvent] = []
        self.active_uows = 0
        self.commits = 0

    def factory(self) -> _ExtractionUnitOfWork:
        return _ExtractionUnitOfWork(self)


class _RecordingRunner:
    def __init__(
        self,
        state: _ExtractionState,
        result: ExtractedDocument | None = None,
        error: Exception | None = None,
    ) -> None:
        self._state = state
        self._result = result
        self._error = error
        self.calls = 0
        self.saw_open_transaction = False

    def extract(self, path: Path, mime_type: str) -> ExtractedDocument:
        del path, mime_type
        self.calls += 1
        self.saw_open_transaction = self._state.active_uows > 0
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _downloaded_attachment(path: Path) -> MessageAttachment:
    content = path.read_bytes()
    return MessageAttachment(
        id=uuid4(),
        feishu_message_id=uuid4(),
        message_version_id=uuid4(),
        file_key="file-test",
        file_name=path.name,
        mime_type="text/plain",
        size=len(content),
        download_status=AttachmentDownloadStatus.DOWNLOADED,
        sha256=sha256(content).hexdigest(),
        local_path=str(path),
    )


@pytest.mark.asyncio
async def test_extraction_process_runs_outside_database_transaction(
    tmp_path: Path,
) -> None:
    root = tmp_path / "attachments"
    root.mkdir()
    document = root / "sample.txt"
    document.write_text("第一段。", encoding="utf-8")
    state = _ExtractionState()
    attachment = _downloaded_attachment(document)
    state.attachments[attachment.id] = attachment
    runner = _RecordingRunner(
        state,
        ExtractedDocument(
            status=DocumentExtractionStatus.SUCCEEDED,
            segments=(
                ExtractedSegment(
                    page_number=None,
                    paragraph_number=1,
                    start_offset=0,
                    end_offset=4,
                    content="第一段。",
                    content_hash=sha256("第一段。".encode()).hexdigest(),
                ),
            ),
            page_count=None,
            character_count=4,
        ),
    )

    result = await DocumentExtractionService(state.factory, runner).execute(attachment.id)

    assert runner.saw_open_transaction is False
    assert result.status == DocumentExtractionStatus.SUCCEEDED
    assert attachment.extraction_status == DocumentExtractionStatus.SUCCEEDED
    assert len(state.versions) == 1
    assert len(state.extractions) == 1
    assert state.segments[0].attachment_id == attachment.id
    assert [value.event_type for value in state.outbox_events] == ["FeishuMessageAnalysisRequested"]
    assert state.commits == 2


@pytest.mark.asyncio
async def test_extraction_timeout_is_persisted_without_segments(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    root.mkdir()
    document = root / "sample.txt"
    document.write_text("第一段。", encoding="utf-8")
    state = _ExtractionState()
    attachment = _downloaded_attachment(document)
    state.attachments[attachment.id] = attachment
    runner = _RecordingRunner(
        state,
        error=ExtractionProcessTimeoutError("timed out"),
    )

    result = await DocumentExtractionService(state.factory, runner).execute(attachment.id)

    assert result.status == DocumentExtractionStatus.FAILED
    assert result.error_code == "DOCUMENT_EXTRACTION_TIMEOUT"
    assert attachment.extraction_status == DocumentExtractionStatus.FAILED
    assert state.segments == []


@pytest.mark.asyncio
async def test_terminal_extraction_delivery_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    root.mkdir()
    document = root / "sample.txt"
    document.write_text("第一段。", encoding="utf-8")
    state = _ExtractionState()
    attachment = _downloaded_attachment(document)
    state.attachments[attachment.id] = attachment
    runner = _RecordingRunner(
        state,
        ExtractedDocument(
            status=DocumentExtractionStatus.SUCCEEDED,
            segments=(
                ExtractedSegment(
                    page_number=None,
                    paragraph_number=1,
                    start_offset=0,
                    end_offset=4,
                    content="第一段。",
                    content_hash=sha256("第一段。".encode()).hexdigest(),
                ),
            ),
            page_count=None,
            character_count=4,
        ),
    )
    service = DocumentExtractionService(state.factory, runner)

    first = await service.execute(attachment.id)
    second = await service.execute(attachment.id)

    assert second.extraction_id == first.extraction_id
    assert second.status == DocumentExtractionStatus.SUCCEEDED
    assert runner.calls == 1
    assert len(state.extractions) == 1
    assert len(state.segments) == 1
