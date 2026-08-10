from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from legal_workbench.application.token_budget import (
    DeterministicTokenEstimator,
    KnowledgeBudget,
)
from legal_workbench.domain.documents import ExtractedDocument
from legal_workbench.domain.enums import DocumentExtractionStatus
from legal_workbench.integrations.local_knowledge_files import scan_local_knowledge_files


class InventoryDocumentExtractor(Protocol):
    def extract(self, path: Path, mime_type: str) -> ExtractedDocument: ...


@dataclass(frozen=True, slots=True)
class MaterialExtensionStat:
    file_count: int
    disk_size: int


@dataclass(frozen=True, slots=True)
class MaterialInventory:
    file_count: int
    extension_stats: dict[str, MaterialExtensionStat]
    parseable_file_count: int
    unparseable_file_count: int
    unsupported_file_count: int
    total_disk_size: int
    extracted_character_count: int
    estimated_token_count: int
    unique_sha256_token_count: int
    duplicate_token_savings: int
    category_token_counts: dict[str, int]
    token_estimator: str
    token_count_estimated: bool
    option_a_tokens_per_agent_run: int
    option_b_tokens_per_agent_run: int
    tokens_saved_per_agent_run: int


class MaterialInventoryService:
    def __init__(
        self,
        extractor: InventoryDocumentExtractor,
        estimator: DeterministicTokenEstimator,
    ) -> None:
        self._extractor = extractor
        self._estimator = estimator

    def build(
        self,
        source: Path,
        *,
        retrieval_budget: KnowledgeBudget,
    ) -> MaterialInventory:
        scan = scan_local_knowledge_files(source)
        extension_counts: dict[str, list[int]] = {}
        for candidate in scan.files:
            key = candidate.extension or "[no-extension]"
            values = extension_counts.setdefault(key, [0, 0])
            values[0] += 1
            values[1] += candidate.size

        parseable = 0
        unparseable = len(scan.failures)
        unsupported = 0
        characters = 0
        raw_tokens = 0
        unique_tokens = 0
        category_tokens: dict[str, int] = {}
        extracted_by_sha: dict[str, tuple[bool, int, int]] = {}
        for candidate in scan.files:
            if not candidate.supported:
                unsupported += 1
                continue
            extracted_summary = extracted_by_sha.get(candidate.content_sha256)
            if extracted_summary is None:
                try:
                    extracted = self._extractor.extract(
                        candidate.absolute_path,
                        candidate.mime_type,
                    )
                except Exception:
                    extracted_summary = (False, 0, 0)
                else:
                    text = "".join(segment.content for segment in extracted.segments)
                    success = (
                        extracted.status == DocumentExtractionStatus.SUCCEEDED
                        and bool(text)
                    )
                    extracted_summary = (
                        success,
                        extracted.character_count if success else 0,
                        self._estimator.estimate(text).tokens if success else 0,
                    )
                extracted_by_sha[candidate.content_sha256] = extracted_summary
                if extracted_summary[0]:
                    unique_tokens += extracted_summary[2]
            success, character_count, token_count = extracted_summary
            if not success:
                unparseable += 1
                continue
            parseable += 1
            characters += character_count
            raw_tokens += token_count
            category = _material_category(candidate.relative_path)
            category_tokens[category] = category_tokens.get(category, 0) + token_count

        option_b = min(unique_tokens, retrieval_budget.max_tokens)
        return MaterialInventory(
            file_count=len(scan.files) + len(scan.failures),
            extension_stats={
                extension: MaterialExtensionStat(file_count=values[0], disk_size=values[1])
                for extension, values in sorted(extension_counts.items())
            },
            parseable_file_count=parseable,
            unparseable_file_count=unparseable,
            unsupported_file_count=unsupported,
            total_disk_size=sum(candidate.size for candidate in scan.files),
            extracted_character_count=characters,
            estimated_token_count=raw_tokens,
            unique_sha256_token_count=unique_tokens,
            duplicate_token_savings=raw_tokens - unique_tokens,
            category_token_counts=dict(sorted(category_tokens.items())),
            token_estimator=self._estimator.method,
            token_count_estimated=True,
            option_a_tokens_per_agent_run=raw_tokens,
            option_b_tokens_per_agent_run=option_b,
            tokens_saved_per_agent_run=raw_tokens - option_b,
        )


def _material_category(relative_path: str) -> str:
    parts = PurePosixPath(relative_path).parts
    return parts[0] if len(parts) > 1 else "[root]"
