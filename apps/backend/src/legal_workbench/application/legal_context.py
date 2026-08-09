from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from legal_workbench.application.knowledge import KnowledgeRetrievalService
from legal_workbench.domain.entities import ContextSnapshot, KnowledgeSearchRequest

SUPPORTED_KNOWLEDGE_DOCUMENT_TYPES = (
    "law",
    "administrative_regulation",
    "judicial_interpretation",
    "department_rule",
    "local_regulation",
    "local_government_rule",
    "normative_document",
    "guiding_case",
    "court_case",
    "regulatory_guidance",
    "contract",
    "company_policy",
    "contract_template",
    "legal_opinion",
    "internal_opinion",
    "regulation",
    "business_rule",
    "internal_precedent",
    "unknown",
)


@dataclass(frozen=True, slots=True)
class AuthorizedLegalContext:
    payload: dict[str, object]
    source_refs: frozenset[str]
    internal_precedent_refs: frozenset[str]
    source_authorities: dict[str, dict[str, object]] = field(default_factory=dict)


class LegalContextBuilder:
    def __init__(self, retrieval: KnowledgeRetrievalService) -> None:
        self._retrieval = retrieval

    def planning(self, snapshot: ContextSnapshot) -> AuthorizedLegalContext:
        refs = self._snapshot_refs(snapshot)
        return AuthorizedLegalContext(
            payload={"contextSnapshot": self._snapshot_payload(snapshot)},
            source_refs=frozenset(refs),
            internal_precedent_refs=frozenset(),
        )

    async def specialist(
        self,
        *,
        snapshot: ContextSnapshot,
        agent_type: str,
        matter_type: str,
        objective: str,
        jurisdiction: str,
        effective_date: date,
        correlation_id: str,
        agent_run_id: UUID | None,
        upstream_outputs: dict[str, object],
    ) -> AuthorizedLegalContext:
        results = await self._retrieval.search(
            KnowledgeSearchRequest(
                query=objective,
                agent_type=agent_type,
                matter_type=matter_type,
                jurisdiction=jurisdiction,
                document_types=SUPPORTED_KNOWLEDGE_DOCUMENT_TYPES,
                effective_date=effective_date,
                correlation_id=correlation_id,
                agent_run_id=agent_run_id,
            )
        )
        snapshot_refs = self._snapshot_refs(snapshot)
        knowledge_refs = {result.source_ref for result in results}
        precedents = {
            result.source_ref for result in results if result.internal_precedent
        }
        source_authorities: dict[str, dict[str, object]] = {
            result.source_ref: {
                "authorityType": result.document.authority_type.value,
                "authorityRole": (
                    result.document.authority_role.value
                    if result.document.authority_role is not None
                    else None
                ),
                "authorityStatus": result.document.authority_status.value,
                "metadataStatus": result.document.metadata_status.value,
                "jurisdiction": result.document.jurisdiction,
                "effectiveFrom": (
                    result.document.effective_from.isoformat()
                    if result.document.effective_from
                    else None
                ),
                "effectiveTo": (
                    result.document.effective_to.isoformat()
                    if result.document.effective_to
                    else None
                ),
            }
            for result in results
        }
        return AuthorizedLegalContext(
            payload={
                "contextSnapshot": self._snapshot_payload(snapshot),
                "retrievalResults": [
                    {
                        "sourceRef": result.source_ref,
                        "title": result.document.title,
                        "sourceType": result.document.source_type,
                        "documentType": result.document.document_type,
                        "jurisdiction": result.document.jurisdiction,
                        "effectiveFrom": (
                            result.document.effective_from.isoformat()
                            if result.document.effective_from
                            else None
                        ),
                        "effectiveTo": (
                            result.document.effective_to.isoformat()
                            if result.document.effective_to
                            else None
                        ),
                        "sourcePriority": result.document.source_priority,
                        "internalPrecedent": result.internal_precedent,
                        **source_authorities[result.source_ref],
                        "locator": result.chunk.locator,
                        "text": result.chunk.text,
                        "textHash": result.chunk.text_hash,
                        "score": result.score,
                    }
                    for result in results
                ],
                "upstreamOutputs": upstream_outputs,
            },
            source_refs=frozenset(snapshot_refs | knowledge_refs),
            internal_precedent_refs=frozenset(precedents),
            source_authorities=source_authorities,
        )

    @staticmethod
    def _snapshot_payload(snapshot: ContextSnapshot) -> dict[str, object]:
        return {
            "id": str(snapshot.id),
            "contentHash": snapshot.content_hash,
            "messageIds": snapshot.message_ids,
            "attachmentIds": snapshot.attachment_ids,
            "includedSegments": snapshot.included_segments,
            "content": snapshot.content,
            "truncated": snapshot.truncated,
        }

    @staticmethod
    def _snapshot_refs(snapshot: ContextSnapshot) -> set[str]:
        refs = {f"ctx:message:{message_id}" for message_id in snapshot.message_ids}
        refs.add(f"ctx:snapshot:{snapshot.id}")
        refs.update(
            f"ctx:segment:{value.get('contentHash')}"
            for value in snapshot.included_segments
            if value.get("contentHash")
        )
        return refs
