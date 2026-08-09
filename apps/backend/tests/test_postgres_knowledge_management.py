from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from legal_workbench.domain.entities import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeRetrievalLog,
)
from legal_workbench.domain.enums import (
    AuthorityStatus,
    AuthorityType,
    KnowledgeMetadataStatus,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_knowledge_management_lists_details_and_corrects_metadata() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.api.auth import RequestActor
    from legal_workbench.api.dependencies import (
        get_actor_id,
        get_request_actor,
        get_uow_factory,
    )
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
    from legal_workbench.main import app

    engine = create_async_engine(os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"])
    factory = SqlAlchemyUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    document = KnowledgeDocument(
        id=uuid4(),
        source_type="local_document",
        source_id=str(uuid4()),
        title="待分类合作资料",
        document_type="unknown",
        agent_types=["contract_review"],
        matter_types=["contract"],
        jurisdiction="CN",
        source_priority=50,
        internal_precedent=False,
        confidentiality="internal",
        authority_type=AuthorityType.UNKNOWN,
        authority_role=None,
        authority_status=AuthorityStatus.UNKNOWN,
        metadata_status=KnowledgeMetadataStatus.PENDING_METADATA,
    )
    chunk = KnowledgeChunk(
        id=uuid4(),
        knowledge_document_id=document.id,
        sequence=1,
        locator="第1段",
        text="这是不含真实信息的合作条款 fixture。",
        normalized_text="这是不含真实信息的合作条款 fixture。",
        text_hash="a" * 64,
        estimated_token_count=12,
    )
    log = KnowledgeRetrievalLog(
        id=uuid4(),
        query_hash="b" * 64,
        filters={"matterType": "contract"},
        selected_chunk_ids=[chunk.id],
        component_scores={str(chunk.id): {"fullText": 0.8}},
        correlation_id="knowledge-management-fixture",
        candidate_count=3,
        selected_chunk_count=1,
        selected_token_count=12,
        excluded_by_token_budget_count=2,
        budget={"maxChunks": 1, "maxTokens": 20, "maxSingleChunkTokens": 20},
        created_at=datetime.now(UTC),
    )
    app.dependency_overrides[get_uow_factory] = lambda: factory
    app.dependency_overrides[get_request_actor] = lambda: RequestActor(
        actor_id="knowledge-test-user",
        identity_source="test",
    )
    app.dependency_overrides[get_actor_id] = lambda: "knowledge-test-user"
    headers = {"X-Actor-ID": "knowledge-test-user"}
    try:
        async with factory() as uow:
            await uow.knowledge.add_document(document)
            await uow.flush()
            await uow.knowledge.add_chunks([chunk])
            await uow.knowledge.add_retrieval_log(log)
            await uow.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers=headers,
        ) as client:
            listed = await client.get(
                "/api/v1/knowledge/documents?metadataStatus=pending_metadata"
            )
            assert listed.status_code == 200
            assert any(value["id"] == str(document.id) for value in listed.json())

            details = await client.get(
                f"/api/v1/knowledge/documents/{document.id}"
            )
            assert details.status_code == 200
            assert details.json()["chunks"][0]["text"] == chunk.text
            assert details.json()["retrievalLogs"][0]["queryHash"] == "b" * 64
            assert details.json()["document"]["sourceId"] == document.source_id

            payload = {
                "title": "示例合作合同",
                "authorityType": "contract",
                "authorityRole": "contractual_basis",
                "authorityStatus": "effective",
                "jurisdiction": "CN",
                "effectiveFrom": "2026-01-01",
                "effectiveTo": None,
                "issuer": "示例甲乙双方",
                "documentNumber": None,
                "enabled": True,
            }
            mutation_headers = {
                "If-Match": "1",
                "Idempotency-Key": f"knowledge-update-{uuid4().hex}",
            }
            updated = await client.patch(
                f"/api/v1/knowledge/documents/{document.id}/metadata",
                headers=mutation_headers,
                json=payload,
            )
            assert updated.status_code == 200
            assert updated.json() == {
                "documentId": str(document.id),
                "version": 2,
                "idempotentReplay": False,
            }

            replay = await client.patch(
                f"/api/v1/knowledge/documents/{document.id}/metadata",
                headers=mutation_headers,
                json=payload,
            )
            assert replay.status_code == 200
            assert replay.json()["idempotentReplay"] is True

            corrected = await client.get(
                f"/api/v1/knowledge/documents/{document.id}"
            )
            assert corrected.json()["document"]["authorityRole"] == "contractual_basis"
            assert corrected.json()["document"]["sourcePriority"] == 80
            assert corrected.json()["document"]["metadataStatus"] == "ready"
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
