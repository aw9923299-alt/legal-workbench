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
        historical_as_of: date | None,
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
                historical_as_of=historical_as_of,
                agent_run_id=agent_run_id,
            )
        )
        snapshot_refs = self._snapshot_refs(snapshot)
        knowledge_refs = {result.source_ref for result in results}
        precedents = {
            result.source_ref for result in results if result.internal_precedent
        }
        source_authorities = self._snapshot_source_metadata(snapshot)
        source_authorities.update({
            result.source_ref: {
                "title": result.document.title,
                "sourceType": "knowledge_document",
                "locator": result.chunk.locator,
                "contentHash": result.chunk.text_hash,
                "internalPrecedent": result.internal_precedent,
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
        })
        return AuthorizedLegalContext(
            payload={
                "contextSnapshot": self._snapshot_payload(snapshot),
                "analysisJurisdiction": jurisdiction,
                "analysisEffectiveDate": effective_date.isoformat(),
                "analysisHistoricalAsOf": (
                    historical_as_of.isoformat()
                    if historical_as_of is not None
                    else None
                ),
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

    @staticmethod
    def _snapshot_source_metadata(
        snapshot: ContextSnapshot,
    ) -> dict[str, dict[str, object]]:
        metadata: dict[str, dict[str, object]] = {
            f"ctx:snapshot:{snapshot.id}": {
                "title": "Authorized ContextSnapshot",
                "sourceType": "context_snapshot",
                "locator": None,
                "contentHash": snapshot.content_hash,
                "internalPrecedent": False,
            }
        }
        messages = snapshot.content.get("messages", [])
        message_metadata = {
            str(item.get("messageId")): item
            for item in messages
            if isinstance(item, dict) and item.get("messageId")
        } if isinstance(messages, list) else {}
        for message_id in dict.fromkeys(snapshot.message_ids):
            item = message_metadata.get(message_id, {})
            content_hash = str(item.get("contentHash") or snapshot.content_hash)
            metadata[f"ctx:message:{message_id}"] = {
                "title": f"Authorized Feishu message {message_id}",
                "sourceType": "feishu_message",
                "locator": None,
                "contentHash": content_hash,
                "internalPrecedent": False,
            }
        for segment in snapshot.included_segments:
            content_hash = str(segment.get("contentHash") or "")
            if not content_hash:
                continue
            locator_parts = [
                f"page:{segment['pageNumber']}"
                if segment.get("pageNumber") is not None
                else None,
                f"paragraph:{segment['paragraphNumber']}"
                if segment.get("paragraphNumber") is not None
                else None,
            ]
            metadata[f"ctx:segment:{content_hash}"] = {
                "title": str(
                    segment.get("fileName")
                    or segment.get("title")
                    or "Authorized document segment"
                ),
                "sourceType": "attachment",
                "locator": ",".join(
                    value for value in locator_parts if value is not None
                ) or None,
                "contentHash": content_hash,
                "internalPrecedent": False,
            }
        return metadata
