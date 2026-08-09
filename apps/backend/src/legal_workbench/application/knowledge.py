from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from uuid import UUID, uuid4

from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.application.token_budget import (
    PROVISIONAL_DEFAULT_KNOWLEDGE_BUDGET,
    DeterministicTokenEstimator,
    KnowledgeBudget,
    select_budgeted_knowledge,
)
from legal_workbench.domain.entities import (
    DocumentSegment,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeRetrievalLog,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)
from legal_workbench.domain.errors import DomainValidationError
from legal_workbench.domain.knowledge import normalize_knowledge_text


@dataclass(frozen=True, slots=True)
class KnowledgeRegistrationMetadata:
    title: str
    document_type: str
    agent_types: tuple[str, ...]
    matter_types: tuple[str, ...]
    jurisdiction: str
    source_priority: int
    confidentiality: str
    effective_from: date | None = None
    effective_to: date | None = None
    approved_by: str | None = None


class KnowledgeRegistrationService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        estimator: DeterministicTokenEstimator | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._estimator = estimator or DeterministicTokenEstimator()

    async def register_document_version(
        self,
        *,
        document_version_id: UUID,
        segments: Sequence[DocumentSegment],
        metadata: KnowledgeRegistrationMetadata,
    ) -> KnowledgeDocument:
        if not segments:
            raise DomainValidationError(
                "Knowledge registration requires extracted DocumentSegments."
            )
        document = KnowledgeDocument(
            id=uuid4(),
            source_type="document_version",
            source_id=str(document_version_id),
            document_version_id=document_version_id,
            title=metadata.title,
            document_type=metadata.document_type,
            agent_types=list(dict.fromkeys(metadata.agent_types)),
            matter_types=list(dict.fromkeys(metadata.matter_types)),
            jurisdiction=metadata.jurisdiction,
            effective_from=metadata.effective_from,
            effective_to=metadata.effective_to,
            source_priority=metadata.source_priority,
            internal_precedent=False,
            confidentiality=metadata.confidentiality,
            approved_by=metadata.approved_by,
        )
        chunks = [
            KnowledgeChunk(
                id=uuid4(),
                knowledge_document_id=document.id,
                document_segment_id=segment.id,
                sequence=index,
                locator=self._segment_locator(segment),
                text=segment.content,
                normalized_text=normalize_knowledge_text(segment.content),
                text_hash=segment.content_hash,
                estimated_token_count=self._estimator.estimate(segment.content).tokens,
                token_estimator=self._estimator.method,
            )
            for index, segment in enumerate(segments, start=1)
        ]
        async with self._uow_factory() as uow:
            existing = await uow.knowledge.find_document_by_source(
                source_type=document.source_type,
                source_id=document.source_id,
            )
            if existing is not None:
                return existing
            await uow.knowledge.add_document(document)
            await uow.flush()
            await uow.knowledge.add_chunks(chunks)
            await uow.commit()
        return document

    async def register_internal_precedent(
        self,
        *,
        matter_id: UUID,
        approved_review_id: UUID,
        title: str,
        approved_summary: str,
        metadata: KnowledgeRegistrationMetadata,
    ) -> KnowledgeDocument:
        if not approved_summary.strip():
            raise DomainValidationError("Approved precedent summary is required.")
        document = KnowledgeDocument(
            id=uuid4(),
            source_type="historical_matter",
            source_id=str(approved_review_id),
            matter_id=matter_id,
            title=title,
            document_type=metadata.document_type,
            agent_types=list(dict.fromkeys(metadata.agent_types)),
            matter_types=list(dict.fromkeys(metadata.matter_types)),
            jurisdiction=metadata.jurisdiction,
            effective_from=metadata.effective_from,
            effective_to=metadata.effective_to,
            source_priority=metadata.source_priority,
            internal_precedent=True,
            confidentiality=metadata.confidentiality,
            approved_by=metadata.approved_by,
        )
        content = approved_summary.strip()
        chunk = KnowledgeChunk(
            id=uuid4(),
            knowledge_document_id=document.id,
            sequence=1,
            locator="已审核处理方案摘要",
            text=content,
            normalized_text=normalize_knowledge_text(content),
            text_hash=sha256(content.encode()).hexdigest(),
            estimated_token_count=self._estimator.estimate(content).tokens,
            token_estimator=self._estimator.method,
        )
        async with self._uow_factory() as uow:
            existing = await uow.knowledge.find_document_by_source(
                source_type=document.source_type,
                source_id=document.source_id,
            )
            if existing is not None:
                return existing
            await uow.knowledge.add_document(document)
            await uow.flush()
            await uow.knowledge.add_chunks([chunk])
            await uow.commit()
        return document

    @staticmethod
    def _segment_locator(segment: DocumentSegment) -> str:
        page = f"第{segment.page_number}页" if segment.page_number is not None else ""
        return f"{page}第{segment.paragraph_number}段"


class KnowledgeRetrievalService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        default_budget: KnowledgeBudget = PROVISIONAL_DEFAULT_KNOWLEDGE_BUDGET,
        estimator: DeterministicTokenEstimator | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_budget = default_budget
        self._estimator = estimator or DeterministicTokenEstimator()

    async def search(
        self,
        request: KnowledgeSearchRequest,
        budget: KnowledgeBudget | None = None,
    ) -> list[KnowledgeSearchResult]:
        async with self._uow_factory() as uow:
            candidates = list(await uow.knowledge.search(request))
            effective_budget = budget or self._default_budget
            selection = select_budgeted_knowledge(
                candidates,
                budget=effective_budget,
                estimator=self._estimator,
            )
            results = list(selection.selected)
            await uow.knowledge.add_retrieval_log(
                KnowledgeRetrievalLog(
                    id=uuid4(),
                    query_hash=sha256(request.query.strip().encode()).hexdigest(),
                    filters={
                        "agentType": request.agent_type,
                        "matterType": request.matter_type,
                        "jurisdiction": request.jurisdiction,
                        "documentTypes": list(request.document_types),
                        "effectiveDate": request.effective_date.isoformat(),
                        "sourcePriorityMin": request.source_priority_min,
                    },
                    selected_chunk_ids=[result.chunk.id for result in results],
                    component_scores={
                        str(result.chunk.id): result.component_scores for result in candidates
                    },
                    correlation_id=request.correlation_id,
                    agent_run_id=request.agent_run_id,
                    candidate_count=len(candidates),
                    selected_chunk_count=len(results),
                    selected_token_count=selection.selected_token_count,
                    excluded_by_token_budget_count=(
                        selection.excluded_by_token_budget_count
                    ),
                    excluded_duplicate_count=selection.excluded_duplicate_count,
                    budget=effective_budget.as_audit_dict(),
                )
            )
            await uow.commit()
        return results
