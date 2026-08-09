from __future__ import annotations

import json
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
    split_text_for_token_budget,
)
from legal_workbench.domain.entities import (
    AuditEvent,
    DocumentSegment,
    IdempotencyRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeRetrievalLog,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)
from legal_workbench.domain.enums import (
    AuthorityRole,
    AuthorityStatus,
    AuthorityType,
    KnowledgeMetadataStatus,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityNotFoundError,
    IdempotencyConflictError,
)
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
        *,
        max_single_chunk_tokens: int = (
            PROVISIONAL_DEFAULT_KNOWLEDGE_BUDGET.max_single_chunk_tokens
        ),
    ) -> None:
        self._uow_factory = uow_factory
        self._estimator = estimator or DeterministicTokenEstimator()
        if max_single_chunk_tokens < 1:
            raise ValueError("Knowledge single-Chunk token limit must be positive.")
        self._max_single_chunk_tokens = max_single_chunk_tokens

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
        chunks: list[KnowledgeChunk] = []
        for segment in segments:
            pieces = split_text_for_token_budget(
                segment.content,
                max_tokens=self._max_single_chunk_tokens,
                estimator=self._estimator,
            )
            for piece in pieces:
                locator = self._segment_locator(segment)
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
                        text_hash=sha256(piece.text.encode()).hexdigest(),
                        estimated_token_count=piece.estimated_token_count,
                        token_estimator=self._estimator.method,
                    )
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
        pieces = split_text_for_token_budget(
            content,
            max_tokens=self._max_single_chunk_tokens,
            estimator=self._estimator,
        )
        chunks = [
            KnowledgeChunk(
                id=uuid4(),
                knowledge_document_id=document.id,
                sequence=index,
                locator=(
                    "已审核处理方案摘要"
                    if len(pieces) == 1
                    else f"已审核处理方案摘要 chars:{piece.start_offset}-{piece.end_offset}"
                ),
                text=piece.text,
                normalized_text=normalize_knowledge_text(piece.text),
                text_hash=sha256(piece.text.encode()).hexdigest(),
                estimated_token_count=piece.estimated_token_count,
                token_estimator=self._estimator.method,
            )
            for index, piece in enumerate(pieces, start=1)
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


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentDetails:
    document: KnowledgeDocument
    chunks: tuple[KnowledgeChunk, ...]
    retrieval_logs: tuple[KnowledgeRetrievalLog, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeMetadataUpdate:
    title: str
    authority_type: AuthorityType
    authority_role: AuthorityRole | None
    authority_status: AuthorityStatus
    jurisdiction: str
    effective_from: date | None
    effective_to: date | None
    issuer: str | None
    document_number: str | None
    enabled: bool


@dataclass(frozen=True, slots=True)
class KnowledgeMetadataUpdateResult:
    document_id: UUID
    version: int
    idempotent_replay: bool = False


class KnowledgeManagementService:
    """Single-user metadata correction and read-only chunk/retrieval inspection."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    UPDATE_OPERATION = "update_knowledge_metadata"

    async def list_documents(
        self,
        *,
        authority_type: AuthorityType | None = None,
        metadata_status: KnowledgeMetadataStatus | None = None,
        enabled: bool | None = None,
        limit: int = 100,
    ) -> list[KnowledgeDocument]:
        async with self._uow_factory() as uow:
            return list(
                await uow.knowledge.list_documents(
                    authority_type=authority_type,
                    metadata_status=metadata_status,
                    enabled=enabled,
                    limit=limit,
                )
            )

    async def get_document(
        self,
        document_id: UUID,
        *,
        retrieval_log_limit: int = 50,
    ) -> KnowledgeDocumentDetails:
        async with self._uow_factory() as uow:
            document = await uow.knowledge.get_document(document_id)
            if document is None:
                raise EntityNotFoundError("Knowledge document was not found.")
            chunks = tuple(await uow.knowledge.list_chunks(document.id))
            retrieval_logs = tuple(
                await uow.knowledge.list_retrieval_logs(
                    document_id=document.id,
                    limit=retrieval_log_limit,
                )
            )
        return KnowledgeDocumentDetails(
            document=document,
            chunks=chunks,
            retrieval_logs=retrieval_logs,
        )

    async def update_metadata(
        self,
        *,
        document_id: UUID,
        expected_version: int,
        update: KnowledgeMetadataUpdate,
        actor_id: str,
        correlation_id: str,
        idempotency_key: str,
    ) -> KnowledgeMetadataUpdateResult:
        request_payload = {
            "documentId": str(document_id),
            "expectedVersion": expected_version,
            "title": update.title,
            "authorityType": update.authority_type.value,
            "authorityRole": (
                update.authority_role.value if update.authority_role else None
            ),
            "authorityStatus": update.authority_status.value,
            "jurisdiction": update.jurisdiction,
            "effectiveFrom": (
                update.effective_from.isoformat() if update.effective_from else None
            ),
            "effectiveTo": (
                update.effective_to.isoformat() if update.effective_to else None
            ),
            "issuer": update.issuer,
            "documentNumber": update.document_number,
            "enabled": update.enabled,
        }
        request_hash = sha256(
            json.dumps(request_payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation=self.UPDATE_OPERATION,
                key=idempotency_key,
            )
            replay = await uow.idempotency.get(
                operation=self.UPDATE_OPERATION,
                key=idempotency_key,
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was already used for another knowledge update."
                    )
                return KnowledgeMetadataUpdateResult(
                    document_id=UUID(str(replay.response_payload["documentId"])),
                    version=int(str(replay.response_payload["version"])),
                    idempotent_replay=True,
                )
            document = await uow.knowledge.get_document_for_update(document_id)
            if document is None:
                raise EntityNotFoundError("Knowledge document was not found.")
            before = {
                "authorityType": document.authority_type.value,
                "authorityRole": (
                    document.authority_role.value if document.authority_role else None
                ),
                "authorityStatus": document.authority_status.value,
                "metadataStatus": document.metadata_status.value,
                "jurisdiction": document.jurisdiction,
                "enabled": document.enabled,
                "version": document.version,
            }
            document.update_metadata(
                expected_version=expected_version,
                title=update.title,
                authority_type=update.authority_type,
                authority_role=update.authority_role,
                authority_status=update.authority_status,
                jurisdiction=update.jurisdiction,
                effective_from=update.effective_from,
                effective_to=update.effective_to,
                issuer=update.issuer,
                document_number=update.document_number,
                enabled=update.enabled,
            )
            await uow.knowledge.save_document(document)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="knowledge_document",
                    aggregate_id=document.id,
                    event_type="knowledge_metadata_corrected",
                    actor_id=actor_id,
                    actor_source="local_user",
                    payload={
                        "before": before,
                        "after": {
                            "authorityType": document.authority_type.value,
                            "authorityRole": (
                                document.authority_role.value
                                if document.authority_role
                                else None
                            ),
                            "authorityStatus": document.authority_status.value,
                            "metadataStatus": document.metadata_status.value,
                            "jurisdiction": document.jurisdiction,
                            "enabled": document.enabled,
                            "version": document.version,
                        },
                    },
                    correlation_id=correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.UPDATE_OPERATION,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_payload={
                        "documentId": str(document.id),
                        "version": document.version,
                    },
                )
            )
            await uow.commit()
        return KnowledgeMetadataUpdateResult(
            document_id=document.id,
            version=document.version,
        )
