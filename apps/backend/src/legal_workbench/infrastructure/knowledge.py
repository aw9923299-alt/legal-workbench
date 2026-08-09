from __future__ import annotations

from typing import Any

from sqlalchemy import Float, case, cast, func, or_, select

from legal_workbench.domain.knowledge import (
    KnowledgeSearchRequest,
    normalize_knowledge_text,
)
from legal_workbench.infrastructure.models import (
    KnowledgeChunkModel,
    KnowledgeDocumentModel,
)


def build_knowledge_search_statement(request: KnowledgeSearchRequest) -> Any:
    normalized_query = normalize_knowledge_text(request.query)
    analysis_date = request.historical_as_of or request.effective_date
    authority_statuses = (
        ["effective", "unknown", "repealed", "superseded"]
        if request.historical_as_of is not None
        else ["effective", "unknown"]
    )
    ts_query = func.websearch_to_tsquery("simple", normalized_query)
    full_text_score = func.ts_rank_cd(KnowledgeChunkModel.search_vector, ts_query)
    trigram_score = func.similarity(
        KnowledgeChunkModel.normalized_text, normalized_query
    )
    priority_score = cast(KnowledgeDocumentModel.source_priority, Float) / 100.0
    effective_score = case(
        (KnowledgeDocumentModel.effective_from.is_(None), 0.25),
        else_=0.5,
    )
    total_score = (
        full_text_score * 0.45
        + trigram_score * 0.30
        + priority_score * 0.20
        + effective_score * 0.05
    )
    return (
        select(
            KnowledgeChunkModel,
            KnowledgeDocumentModel,
            full_text_score.label("full_text_score"),
            trigram_score.label("trigram_score"),
            priority_score.label("priority_score"),
            effective_score.label("effective_score"),
            total_score.label("total_score"),
        )
        .join(
            KnowledgeDocumentModel,
            KnowledgeDocumentModel.id == KnowledgeChunkModel.knowledge_document_id,
        )
        .where(
            KnowledgeDocumentModel.status == "active",
            KnowledgeDocumentModel.enabled.is_(True),
            KnowledgeDocumentModel.authority_status.in_(authority_statuses),
            or_(
                KnowledgeDocumentModel.agent_types.contains([request.agent_type]),
                KnowledgeDocumentModel.agent_types.contains(["*"]),
            ),
            or_(
                KnowledgeDocumentModel.matter_types.contains([request.matter_type]),
                KnowledgeDocumentModel.matter_types.contains(["*"]),
            ),
            KnowledgeDocumentModel.jurisdiction.in_([request.jurisdiction, "ANY"]),
            KnowledgeDocumentModel.document_type.in_(request.document_types),
            KnowledgeDocumentModel.source_priority >= request.source_priority_min,
            or_(
                KnowledgeDocumentModel.effective_from.is_(None),
                KnowledgeDocumentModel.effective_from <= analysis_date,
            ),
            or_(
                KnowledgeDocumentModel.effective_to.is_(None),
                KnowledgeDocumentModel.effective_to >= analysis_date,
            ),
            or_(
                KnowledgeChunkModel.search_vector.op("@@")(ts_query),
                trigram_score >= 0.05,
            ),
        )
        .order_by(
            total_score.desc(),
            KnowledgeDocumentModel.source_priority.desc(),
            KnowledgeDocumentModel.effective_from.desc().nullslast(),
            KnowledgeDocumentModel.id,
            KnowledgeChunkModel.sequence,
        )
        .limit(min(request.limit * 5, 250))
    )
