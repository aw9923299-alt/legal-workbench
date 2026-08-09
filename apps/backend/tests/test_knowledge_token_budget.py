from __future__ import annotations

from datetime import date
from hashlib import sha256
from uuid import uuid4

import pytest

from legal_workbench.application.knowledge import KnowledgeRetrievalService
from legal_workbench.application.token_budget import KnowledgeBudget
from legal_workbench.domain.enums import (
    AuthorityRole,
    AuthorityStatus,
    AuthorityType,
    KnowledgeMetadataStatus,
)
from legal_workbench.domain.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)


def _document(authority_type: AuthorityType) -> KnowledgeDocument:
    roles = {
        AuthorityType.LAW: AuthorityRole.FORMAL_LEGAL_BASIS,
        AuthorityType.CONTRACT: AuthorityRole.CONTRACTUAL_BASIS,
        AuthorityType.COMPANY_POLICY: AuthorityRole.INTERNAL_BASIS,
    }
    return KnowledgeDocument(
        id=uuid4(),
        source_type="fixture",
        source_id=uuid4().hex,
        title=authority_type.value,
        document_type=authority_type.value,
        agent_types=["contract_review"],
        matter_types=["contract"],
        jurisdiction="CN",
        source_priority=100,
        internal_precedent=False,
        confidentiality="internal",
        authority_type=authority_type,
        authority_role=roles[authority_type],
        authority_status=AuthorityStatus.EFFECTIVE,
        metadata_status=KnowledgeMetadataStatus.READY,
    )


def _result(
    authority_type: AuthorityType,
    text: str,
    *,
    tokens: int,
    score: float,
    text_hash: str | None = None,
) -> KnowledgeSearchResult:
    document = _document(authority_type)
    chunk = KnowledgeChunk(
        id=uuid4(),
        knowledge_document_id=document.id,
        sequence=1,
        locator="第一段",
        text=text,
        normalized_text=text,
        text_hash=text_hash or sha256(text.encode()).hexdigest(),
        estimated_token_count=tokens,
    )
    return KnowledgeSearchResult(
        document=document,
        chunk=chunk,
        source_ref=f"knowledge:chunk:{chunk.id}",
        score=score,
        component_scores={"total": score},
    )


class _KnowledgeRepository:
    def __init__(self, results: list[KnowledgeSearchResult]) -> None:
        self.results = results
        self.logs = []

    async def search(self, request: KnowledgeSearchRequest):
        return list(self.results)

    async def add_retrieval_log(self, log) -> None:
        self.logs.append(log)


class _Uow:
    def __init__(self, repository: _KnowledgeRepository) -> None:
        self.knowledge = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def commit(self) -> None:
        return None


class _Factory:
    def __init__(self, results: list[KnowledgeSearchResult]) -> None:
        self.knowledge = _KnowledgeRepository(results)

    def __call__(self):
        return _Uow(self.knowledge)


@pytest.mark.asyncio
async def test_retrieval_deduplicates_authority_first_and_enforces_all_budgets() -> None:
    law_hash = sha256(b"same-law").hexdigest()
    results = [
        _result(AuthorityType.COMPANY_POLICY, "policy", tokens=4, score=0.99),
        _result(AuthorityType.LAW, "law", tokens=3, score=0.80, text_hash=law_hash),
        _result(AuthorityType.LAW, "law duplicate", tokens=3, score=0.70, text_hash=law_hash),
        _result(AuthorityType.CONTRACT, "contract", tokens=2, score=0.60),
        _result(AuthorityType.LAW, "too large", tokens=10, score=0.50),
    ]
    factory = _Factory(results)
    request = KnowledgeSearchRequest(
        query="合同责任",
        agent_type="contract_review",
        matter_type="contract",
        jurisdiction="CN",
        document_types=("law", "contract", "company_policy"),
        effective_date=date(2026, 8, 9),
        correlation_id="budget-audit",
    )

    selected = await KnowledgeRetrievalService(factory).search(
        request,
        budget=KnowledgeBudget(max_chunks=2, max_tokens=6, max_single_chunk_tokens=4),
    )

    assert [value.document.authority_type for value in selected] == [
        AuthorityType.LAW,
        AuthorityType.CONTRACT,
    ]
    log = factory.knowledge.logs[0]
    assert log.candidate_count == 5
    assert log.selected_chunk_count == 2
    assert log.selected_token_count == 5
    assert log.excluded_by_token_budget_count == 2
    assert log.excluded_duplicate_count == 1
    assert log.budget == {
        "maxChunks": 2,
        "maxTokens": 6,
        "maxSingleChunkTokens": 4,
    }


def test_budget_rejects_non_positive_limits() -> None:
    with pytest.raises(ValueError):
        KnowledgeBudget(max_chunks=0, max_tokens=100, max_single_chunk_tokens=10)
