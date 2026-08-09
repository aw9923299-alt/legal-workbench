# ruff: noqa: RUF001

from __future__ import annotations

from datetime import UTC, date, datetime
from hashlib import sha256
from types import TracebackType
from uuid import uuid4

import pytest

from legal_workbench.application.knowledge import (
    KnowledgeRegistrationMetadata,
    KnowledgeRegistrationService,
    KnowledgeRetrievalService,
)
from legal_workbench.domain.entities import (
    DocumentSegment,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSearchBatch,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)


class FakeKnowledgeRepository:
    def __init__(self) -> None:
        self.documents: list[KnowledgeDocument] = []
        self.chunks: list[KnowledgeChunk] = []
        self.logs: list[object] = []
        self.results: list[KnowledgeSearchResult] = []

    async def find_document_by_source(
        self, *, source_type: str, source_id: str
    ) -> KnowledgeDocument | None:
        return next(
            (
                item
                for item in self.documents
                if item.source_type == source_type and item.source_id == source_id
            ),
            None,
        )

    async def add_document(self, document: KnowledgeDocument) -> None:
        self.documents.append(document)

    async def add_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        self.chunks.extend(chunks)

    async def search(
        self, request: KnowledgeSearchRequest
    ) -> KnowledgeSearchBatch:
        return KnowledgeSearchBatch(
            candidates=tuple(self.results),
            candidate_count=len(self.results),
        )

    async def add_retrieval_log(self, log: object) -> None:
        self.logs.append(log)


class FakeUow:
    def __init__(self, knowledge: FakeKnowledgeRepository) -> None:
        self.knowledge = knowledge
        self.flush_count = 0
        self.commit_count = 0

    async def __aenter__(self) -> FakeUow:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def flush(self) -> None:
        self.flush_count += 1

    async def commit(self) -> None:
        self.commit_count += 1


class FakeUowFactory:
    def __init__(self) -> None:
        self.knowledge = FakeKnowledgeRepository()
        self.instances: list[FakeUow] = []

    def __call__(self) -> FakeUow:
        value = FakeUow(self.knowledge)
        self.instances.append(value)
        return value


def _metadata() -> KnowledgeRegistrationMetadata:
    return KnowledgeRegistrationMetadata(
        title="非敏感合同模板",
        document_type="contract_template",
        agent_types=("contract_review",),
        matter_types=("contract",),
        jurisdiction="CN",
        source_priority=80,
        confidentiality="internal",
        effective_from=date(2026, 1, 1),
        approved_by="user:test",
    )


@pytest.mark.asyncio
async def test_registration_reuses_document_segments_without_parsing_again() -> None:
    factory = FakeUowFactory()
    segment = DocumentSegment(
        id=uuid4(),
        extraction_id=uuid4(),
        attachment_id=uuid4(),
        page_number=2,
        paragraph_number=3,
        start_offset=0,
        end_offset=len("责任上限条款。"),
        content="责任上限条款。",
        content_hash=sha256("责任上限条款。".encode()).hexdigest(),
        created_at=datetime.now(UTC),
    )

    document = await KnowledgeRegistrationService(factory).register_document_version(
        document_version_id=uuid4(),
        segments=[segment],
        metadata=_metadata(),
    )

    assert document.internal_precedent is False
    assert factory.knowledge.chunks[0].document_segment_id == segment.id
    assert factory.knowledge.chunks[0].locator == "第2页第3段"
    assert factory.knowledge.chunks[0].text == segment.content
    assert factory.instances[0].flush_count == 1
    assert factory.instances[0].commit_count == 1


@pytest.mark.asyncio
async def test_registration_splits_oversized_segments_before_retrieval() -> None:
    factory = FakeUowFactory()
    content = "通用管道超长段落。" * 80
    segment = DocumentSegment(
        id=uuid4(),
        extraction_id=uuid4(),
        attachment_id=uuid4(),
        page_number=1,
        paragraph_number=1,
        start_offset=0,
        end_offset=len(content),
        content=content,
        content_hash=sha256(content.encode()).hexdigest(),
        created_at=datetime.now(UTC),
    )

    await KnowledgeRegistrationService(
        factory,
        max_single_chunk_tokens=24,
    ).register_document_version(
        document_version_id=uuid4(),
        segments=[segment],
        metadata=_metadata(),
    )

    assert len(factory.knowledge.chunks) > 1
    assert "".join(value.text for value in factory.knowledge.chunks) == content
    assert all(value.estimated_token_count <= 24 for value in factory.knowledge.chunks)
    assert all(value.document_segment_id == segment.id for value in factory.knowledge.chunks)


@pytest.mark.asyncio
async def test_internal_precedent_is_labeled_and_retrieval_is_audited() -> None:
    factory = FakeUowFactory()
    service = KnowledgeRegistrationService(factory)
    precedent = await service.register_internal_precedent(
        matter_id=uuid4(),
        approved_review_id=uuid4(),
        title="已审核历史处理方案",
        approved_summary="先补充授权链，再决定上线。",
        metadata=_metadata(),
    )
    chunk = factory.knowledge.chunks[0]
    result = KnowledgeSearchResult(
        document=precedent,
        chunk=chunk,
        source_ref=f"knowledge:chunk:{chunk.id}",
        score=0.9,
        component_scores={"priority": 0.8},
    )
    factory.knowledge.results = [result]
    request = KnowledgeSearchRequest(
        query="授权链",
        agent_type="ip_copyright",
        matter_type="ip",
        jurisdiction="CN",
        document_types=("contract_template",),
        effective_date=date(2026, 8, 9),
        correlation_id="corr-knowledge",
    )

    results = await KnowledgeRetrievalService(factory).search(request)

    assert results[0].internal_precedent is True
    assert len(factory.knowledge.logs) == 1
    assert factory.instances[-1].commit_count == 1
