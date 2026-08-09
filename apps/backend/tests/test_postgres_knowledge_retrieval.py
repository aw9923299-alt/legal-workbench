from __future__ import annotations

import os
from datetime import date
from hashlib import sha256
from uuid import uuid4

import pytest

from legal_workbench.application.knowledge import KnowledgeRetrievalService
from legal_workbench.domain.entities import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSearchRequest,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_retrieval_filters_and_ranks_authorized_knowledge() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import delete, func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.models import (
        KnowledgeDocumentModel,
        KnowledgeRetrievalLogModel,
    )
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    factory = SqlAlchemyUnitOfWorkFactory(session_factory)
    source_suffix = uuid4().hex
    retrieval_marker = f"retrieval{source_suffix}"

    def document(
        name: str,
        *,
        priority: int,
        agent_types: list[str] | None = None,
        jurisdiction: str = "CN",
        effective_to: date | None = None,
        internal_precedent: bool = False,
        document_type: str = "regulation",
    ) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=uuid4(),
            source_type="fixture",
            source_id=f"{source_suffix}:{name}",
            title=name,
            document_type=document_type,
            agent_types=agent_types or ["contract_review"],
            matter_types=["contract"],
            jurisdiction=jurisdiction,
            effective_from=date(2021, 1, 1),
            effective_to=effective_to,
            source_priority=priority,
            internal_precedent=internal_precedent,
            confidentiality="internal",
        )

    authoritative = document("高优先级法规", priority=95)
    lower = document("一般法规", priority=55)
    precedent = document(
        "内部已审核意见",
        priority=80,
        internal_precedent=True,
        document_type="internal_opinion",
    )
    wrong_agent = document("错误 Agent", priority=100, agent_types=["labor_employment"])
    wrong_jurisdiction = document("错误法域", priority=100, jurisdiction="US")
    expired = document("已失效法规", priority=100, effective_to=date(2025, 1, 1))
    documents = [
        authoritative,
        lower,
        precedent,
        wrong_agent,
        wrong_jurisdiction,
        expired,
    ]
    chunks = [
        KnowledgeChunk(
            id=uuid4(),
            knowledge_document_id=value.id,
            sequence=1,
            locator="第一条",
            text=f"{retrieval_marker} 合同责任上限应结合交易结构确定。",
            normalized_text=f"{retrieval_marker} 合同责任上限应结合交易结构确定。",
            text_hash=sha256(
                f"{retrieval_marker}:合同责任上限应结合交易结构确定。:{value.id}".encode()
            ).hexdigest(),
        )
        for value in documents
    ]
    request = KnowledgeSearchRequest(
        query=retrieval_marker,
        agent_type="contract_review",
        matter_type="contract",
        jurisdiction="CN",
        document_types=("regulation", "internal_opinion"),
        effective_date=date(2026, 8, 9),
        source_priority_min=50,
        limit=10,
        correlation_id=f"retrieval-{source_suffix}",
    )

    try:
        async with factory() as uow:
            for value in documents:
                await uow.knowledge.add_document(value)
            await uow.flush()
            await uow.knowledge.add_chunks(chunks)
            await uow.commit()

        results = await KnowledgeRetrievalService(factory).search(request)

        assert [item.document.id for item in results] == [
            authoritative.id,
            precedent.id,
            lower.id,
        ]
        assert results[1].internal_precedent is True
        assert all(item.source_ref.startswith("knowledge:chunk:") for item in results)
        async with session_factory() as session:
            audit_count = await session.scalar(
                select(func.count(KnowledgeRetrievalLogModel.id)).where(
                    KnowledgeRetrievalLogModel.correlation_id == request.correlation_id
                )
            )
        assert audit_count == 1
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(KnowledgeRetrievalLogModel).where(
                    KnowledgeRetrievalLogModel.correlation_id
                    == request.correlation_id
                )
            )
            await session.execute(
                delete(KnowledgeDocumentModel).where(
                    KnowledgeDocumentModel.source_type == "fixture",
                    KnowledgeDocumentModel.source_id.like(f"{source_suffix}:%"),
                )
            )
        await engine.dispose()
