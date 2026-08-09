from __future__ import annotations

from typing import Any

from sqlalchemy import Float, case, cast, func, or_, select, true

from legal_workbench.domain.knowledge import (
    KnowledgeSearchRequest,
    normalize_knowledge_text,
)
from legal_workbench.infrastructure.models import (
    KnowledgeChunkModel,
    KnowledgeDocumentModel,
)


def build_knowledge_search_statement(request: KnowledgeSearchRequest) -> Any:
    components = _knowledge_search_components(request)
    matched_candidates = (
        select(
            KnowledgeChunkModel.text_hash.label("text_hash"),
            components["estimated_tokens"].label("estimated_tokens"),
        )
        .join(
            KnowledgeDocumentModel,
            KnowledgeDocumentModel.id == KnowledgeChunkModel.knowledge_document_id,
        )
        .where(*components["base_filters"])
        .subquery()
    )
    token_eligible = (
        matched_candidates.c.estimated_tokens <= request.max_candidate_tokens
        if request.max_candidate_tokens is not None
        else true()
    )
    candidate_count = func.count()
    token_eligible_count = func.count().filter(token_eligible)
    distinct_eligible_count = func.count(
        func.distinct(matched_candidates.c.text_hash)
    ).filter(token_eligible)
    diagnostics = (
        select(
            candidate_count.label("candidate_count"),
            (candidate_count - token_eligible_count).label(
                "excluded_by_token_budget_count"
            ),
            (token_eligible_count - distinct_eligible_count).label(
                "excluded_duplicate_count"
            ),
        )
        .select_from(matched_candidates)
        .subquery()
    )
    filters = list(components["base_filters"])
    if request.max_candidate_tokens is not None:
        filters.append(
            components["estimated_tokens"] <= request.max_candidate_tokens
        )
    ranked_candidates = (
        select(
            KnowledgeChunkModel.id.label("chunk_id"),
            func.row_number()
            .over(
                partition_by=KnowledgeChunkModel.text_hash,
                order_by=(
                    components["total_score"].desc(),
                    KnowledgeDocumentModel.source_priority.desc(),
                    KnowledgeDocumentModel.effective_from.desc().nullslast(),
                    KnowledgeDocumentModel.id,
                    KnowledgeChunkModel.sequence,
                ),
            )
            .label("duplicate_rank"),
        )
        .join(
            KnowledgeDocumentModel,
            KnowledgeDocumentModel.id == KnowledgeChunkModel.knowledge_document_id,
        )
        .where(*filters)
        .subquery()
    )
    deduplicated_candidates = (
        select(ranked_candidates.c.chunk_id)
        .where(ranked_candidates.c.duplicate_rank == 1)
        .subquery()
    )
    return (
        select(
            KnowledgeChunkModel,
            KnowledgeDocumentModel,
            components["full_text_score"].label("full_text_score"),
            components["trigram_score"].label("trigram_score"),
            components["priority_score"].label("priority_score"),
            components["effective_score"].label("effective_score"),
            components["total_score"].label("total_score"),
            diagnostics.c.candidate_count,
            diagnostics.c.excluded_by_token_budget_count,
            diagnostics.c.excluded_duplicate_count,
        )
        .select_from(diagnostics)
        .outerjoin(deduplicated_candidates, true())
        .outerjoin(
            KnowledgeChunkModel,
            KnowledgeChunkModel.id == deduplicated_candidates.c.chunk_id,
        )
        .outerjoin(
            KnowledgeDocumentModel,
            KnowledgeDocumentModel.id == KnowledgeChunkModel.knowledge_document_id,
        )
        .order_by(
            components["total_score"].desc(),
            KnowledgeDocumentModel.source_priority.desc(),
            KnowledgeDocumentModel.effective_from.desc().nullslast(),
            KnowledgeDocumentModel.id,
            KnowledgeChunkModel.sequence,
        )
        .limit(min(request.limit * 5, 250))
    )


def _knowledge_search_components(request: KnowledgeSearchRequest) -> dict[str, Any]:
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
    estimated_tokens = case(
        (
            KnowledgeChunkModel.estimated_token_count > 0,
            cast(KnowledgeChunkModel.estimated_token_count, Float),
        ),
        else_=func.ceil(func.octet_length(KnowledgeChunkModel.text) / 4.0),
    )
    base_filters = (
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
    return {
        "full_text_score": full_text_score,
        "trigram_score": trigram_score,
        "priority_score": priority_score,
        "effective_score": effective_score,
        "total_score": total_score,
        "estimated_tokens": estimated_tokens,
        "base_filters": base_filters,
    }
