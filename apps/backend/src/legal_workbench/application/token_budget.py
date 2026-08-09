from __future__ import annotations

from dataclasses import dataclass

from legal_workbench.domain.enums import AuthorityRole
from legal_workbench.domain.knowledge import KnowledgeSearchResult


@dataclass(frozen=True, slots=True)
class TokenEstimate:
    tokens: int
    estimated: bool
    method: str


class DeterministicTokenEstimator:
    """Stable local fallback when no exact model tokenizer is installed."""

    method = "utf8-bytes-ceil-div-4-v1"

    def estimate(self, text: str) -> TokenEstimate:
        byte_count = len(text.encode("utf-8"))
        return TokenEstimate(
            tokens=(byte_count + 3) // 4,
            estimated=True,
            method=self.method,
        )


@dataclass(frozen=True, slots=True)
class BudgetedTextSlice:
    start_offset: int
    end_offset: int
    text: str
    estimated_token_count: int


def split_text_for_token_budget(
    text: str,
    *,
    max_tokens: int,
    estimator: DeterministicTokenEstimator,
) -> tuple[BudgetedTextSlice, ...]:
    """Split deterministically without changing or reordering the source text."""

    if max_tokens < 1:
        raise ValueError("Chunk token limit must be positive.")
    if not text:
        return ()
    max_bytes = max_tokens * 4
    values: list[BudgetedTextSlice] = []
    start = 0
    while start < len(text):
        byte_count = 0
        hard_end = start
        while hard_end < len(text):
            next_bytes = len(text[hard_end].encode("utf-8"))
            if hard_end > start and byte_count + next_bytes > max_bytes:
                break
            byte_count += next_bytes
            hard_end += 1
            if byte_count >= max_bytes:
                break
        end = _preferred_split_end(text, start=start, hard_end=hard_end)
        if end <= start:
            end = hard_end
        piece = text[start:end]
        estimate = estimator.estimate(piece).tokens
        while estimate > max_tokens and end > start + 1:
            end -= 1
            piece = text[start:end]
            estimate = estimator.estimate(piece).tokens
        if piece.strip():
            values.append(
                BudgetedTextSlice(
                    start_offset=start,
                    end_offset=end,
                    text=piece,
                    estimated_token_count=estimate,
                )
            )
        start = end
    return tuple(values)


def _preferred_split_end(text: str, *, start: int, hard_end: int) -> int:
    if hard_end >= len(text):
        return hard_end
    minimum = start + max((hard_end - start) // 2, 1)
    for marker in ("\n\n", "\n", "。", "！", "？", "；", ". ", "; "):  # noqa: RUF001
        position = text.rfind(marker, minimum, hard_end)
        if position >= minimum:
            return position + len(marker)
    return hard_end


@dataclass(frozen=True, slots=True)
class KnowledgeBudget:
    max_chunks: int
    max_tokens: int
    max_single_chunk_tokens: int

    def __post_init__(self) -> None:
        if (
            self.max_chunks < 1
            or self.max_tokens < 1
            or self.max_single_chunk_tokens < 1
            or self.max_single_chunk_tokens > self.max_tokens
        ):
            raise ValueError("Knowledge token budget limits must be positive and consistent.")

    def as_audit_dict(self) -> dict[str, int]:
        return {
            "maxChunks": self.max_chunks,
            "maxTokens": self.max_tokens,
            "maxSingleChunkTokens": self.max_single_chunk_tokens,
        }


PROVISIONAL_DEFAULT_KNOWLEDGE_BUDGET = KnowledgeBudget(
    max_chunks=8,
    max_tokens=12_000,
    max_single_chunk_tokens=3_000,
)


@dataclass(frozen=True, slots=True)
class KnowledgeSelection:
    selected: tuple[KnowledgeSearchResult, ...]
    selected_token_count: int
    excluded_by_token_budget_count: int
    excluded_duplicate_count: int


AUTHORITY_RANK: dict[AuthorityRole | None, int] = {
    AuthorityRole.FORMAL_LEGAL_BASIS: 5,
    AuthorityRole.CONTRACTUAL_BASIS: 4,
    AuthorityRole.PERSUASIVE_AUTHORITY: 3,
    AuthorityRole.INTERNAL_BASIS: 2,
    AuthorityRole.STRATEGY_REFERENCE: 1,
    None: 0,
}


def select_budgeted_knowledge(
    candidates: list[KnowledgeSearchResult],
    *,
    budget: KnowledgeBudget,
    estimator: DeterministicTokenEstimator,
) -> KnowledgeSelection:
    deduplicated: list[tuple[int, KnowledgeSearchResult]] = []
    seen_hashes: set[str] = set()
    excluded_duplicates = 0
    for index, candidate in enumerate(candidates):
        if candidate.chunk.text_hash in seen_hashes:
            excluded_duplicates += 1
            continue
        seen_hashes.add(candidate.chunk.text_hash)
        deduplicated.append((index, candidate))
    ranked = sorted(
        deduplicated,
        key=lambda value: (
            -AUTHORITY_RANK[value[1].document.authority_role],
            -value[1].score,
            value[0],
            str(value[1].chunk.id),
        ),
    )

    selected: list[KnowledgeSearchResult] = []
    selected_tokens = 0
    excluded_by_budget = 0
    for _index, candidate in ranked:
        tokens = candidate.chunk.estimated_token_count
        if tokens <= 0:
            tokens = estimator.estimate(candidate.chunk.text).tokens
        if (
            tokens > budget.max_single_chunk_tokens
            or len(selected) >= budget.max_chunks
            or selected_tokens + tokens > budget.max_tokens
        ):
            excluded_by_budget += 1
            continue
        selected.append(candidate)
        selected_tokens += tokens
    return KnowledgeSelection(
        selected=tuple(selected),
        selected_token_count=selected_tokens,
        excluded_by_token_budget_count=excluded_by_budget,
        excluded_duplicate_count=excluded_duplicates,
    )
