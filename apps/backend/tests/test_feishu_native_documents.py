from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from uuid import UUID

import pytest

from legal_workbench.application.feishu_documents import (
    FeishuDocumentSyncService,
    FeishuFolderSyncService,
    extract_feishu_document_links,
)
from legal_workbench.domain.entities import (
    DocumentExtraction,
    DocumentSegment,
    DocumentVersion,
    FeishuDocument,
)
from legal_workbench.infrastructure.database import Base

AUTHORIZATION_ID = UUID("00000000-0000-0000-0000-000000000401")


class DocumentRepository:
    def __init__(self) -> None:
        self.documents: dict[tuple[UUID, str], FeishuDocument] = {}
        self.versions: list[DocumentVersion] = []
        self.extractions: list[DocumentExtraction] = []
        self.segments: list[DocumentSegment] = []
        self.message_links: list[tuple[UUID, UUID, str]] = []

    async def find_feishu_document(
        self, *, authorization_id: UUID, document_token: str
    ) -> FeishuDocument | None:
        return self.documents.get((authorization_id, document_token))

    async def add_feishu_document(self, value: FeishuDocument) -> None:
        self.documents[(value.authorization_id, value.document_token)] = value

    async def save_feishu_document(self, value: FeishuDocument) -> None:
        self.documents[(value.authorization_id, value.document_token)] = value

    async def find_feishu_document_version(
        self, *, document_id: UUID, content_sha256: str
    ) -> DocumentVersion | None:
        return next(
            (
                value
                for value in self.versions
                if value.feishu_document_id == document_id
                and value.content_sha256 == content_sha256
            ),
            None,
        )

    async def next_feishu_document_version(self, document_id: UUID) -> int:
        values = [
            value.version
            for value in self.versions
            if value.feishu_document_id == document_id
        ]
        return max(values, default=0) + 1

    async def add_version(self, value: DocumentVersion) -> None:
        self.versions.append(value)

    async def add_extraction(self, value: DocumentExtraction) -> None:
        self.extractions.append(value)

    async def add_segments(self, values: Sequence[DocumentSegment]) -> None:
        self.segments.extend(values)

    async def add_feishu_message_document_link(
        self, *, message_id: UUID, document_id: UUID, source_url: str
    ) -> None:
        value = (message_id, document_id, source_url)
        if value not in self.message_links:
            self.message_links.append(value)


class UnitOfWork:
    def __init__(self, repository: DocumentRepository) -> None:
        self.documents = repository

    async def __aenter__(self) -> UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


class Client:
    async def get_document_markdown(
        self, *, authorization_id: UUID, document_id: str
    ) -> str:
        assert authorization_id == AUTHORIZATION_ID
        assert document_id == "doccnAbCdEf"
        return "# 合同审查\n\n请在今天完成。\n\n- 风险一\n- 风险二"

    async def list_folder_files(
        self,
        *,
        authorization_id: UUID,
        folder_token: str,
        page_token: str | None = None,
    ) -> tuple[tuple[dict[str, object], ...], str | None]:
        assert authorization_id == AUTHORIZATION_ID
        assert page_token is None
        if folder_token == "rootfolder":
            return (
                (
                    {
                        "token": "doccnAbCdEf",
                        "type": "docx",
                        "name": "合同审查",
                        "url": "https://acme.feishu.cn/docx/doccnAbCdEf",
                    },
                    {"token": "childfolder", "type": "folder", "name": "子目录"},
                ),
                None,
            )
        assert folder_token == "childfolder"
        return (
            (
                {
                    "token": "doccnAbCdEf",
                    "type": "docx",
                    "name": "合同审查",
                    "url": "https://acme.feishu.cn/docx/doccnAbCdEf",
                },
            ),
            None,
        )


def test_message_document_links_recognize_docx_and_wiki_without_false_positives() -> None:
    links = extract_feishu_document_links(
        "请看 https://acme.feishu.cn/docx/doccnAbCdEf 和 "
        "https://acme.feishu.cn/wiki/wikcn123456; 普通链接 https://example.com/docx/nope"
    )

    assert [(value.document_type, value.token) for value in links] == [
        ("docx", "doccnAbCdEf"),
        ("wiki", "wikcn123456"),
    ]


@pytest.mark.asyncio
async def test_markdown_sync_creates_idempotent_document_version_and_segments() -> None:
    repository = DocumentRepository()
    service = FeishuDocumentSyncService(
        lambda: UnitOfWork(repository),
        client=Client(),
    )

    first = await service.sync_document(
        authorization_id=AUTHORIZATION_ID,
        document_token="doccnAbCdEf",
        document_type="docx",
        title="合同审查",
        source_url="https://acme.feishu.cn/docx/doccnAbCdEf",
    )
    second = await service.sync_document(
        authorization_id=AUTHORIZATION_ID,
        document_token="doccnAbCdEf",
        document_type="docx",
        title="合同审查",
        source_url="https://acme.feishu.cn/docx/doccnAbCdEf",
    )

    assert first.created_version is True
    assert second.created_version is False
    assert len(repository.versions) == 1
    version = repository.versions[0]
    assert version.attachment_id is None
    assert version.feishu_document_id == first.document_id
    assert [segment.content for segment in repository.segments] == [
        "# 合同审查",
        "请在今天完成。",
        "- 风险一",
        "- 风险二",
    ]
    assert all(segment.attachment_id is None for segment in repository.segments)
    assert all(
        segment.feishu_document_id == first.document_id for segment in repository.segments
    )


@pytest.mark.asyncio
async def test_message_link_sync_creates_document_source_relation() -> None:
    repository = DocumentRepository()
    message_id = UUID("00000000-0000-0000-0000-000000000402")
    result = await FeishuDocumentSyncService(
        lambda: UnitOfWork(repository), client=Client()
    ).sync_document(
        authorization_id=AUTHORIZATION_ID,
        document_token="doccnAbCdEf",
        document_type="docx",
        title=None,
        source_url="https://acme.feishu.cn/docx/doccnAbCdEf",
        source_message_id=message_id,
    )

    assert repository.message_links == [
        (message_id, result.document_id, "https://acme.feishu.cn/docx/doccnAbCdEf")
    ]


@pytest.mark.asyncio
async def test_recursive_folder_sync_deduplicates_documents() -> None:
    repository = DocumentRepository()
    document_sync = FeishuDocumentSyncService(
        lambda: UnitOfWork(repository), client=Client()
    )
    result = await FeishuFolderSyncService(
        client=Client(), document_sync=document_sync
    ).sync_folder(
        authorization_id=AUTHORIZATION_ID,
        folder_token="rootfolder",
        recursive=True,
    )

    assert result.discovered_documents == 1
    assert result.created_versions == 1
    assert len(repository.documents) == 1


def test_document_schema_has_exactly_one_source_columns() -> None:
    documents = Base.metadata.tables["feishu_documents"]
    versions = Base.metadata.tables["document_versions"]
    segments = Base.metadata.tables["document_segments"]
    messages = Base.metadata.tables["feishu_messages"]

    assert {"authorization_id", "document_token", "document_type", "last_content_hash"} <= set(
        documents.c.keys()
    )
    assert "feishu_document_id" in versions.c
    assert versions.c.attachment_id.nullable is True
    assert "feishu_document_id" in segments.c
    assert segments.c.attachment_id.nullable is True
    assert "detected_document_links" in messages.c
