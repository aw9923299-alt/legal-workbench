from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from legal_workbench.application.material_inventory import MaterialInventoryService
from legal_workbench.application.token_budget import (
    DeterministicTokenEstimator,
    KnowledgeBudget,
)
from legal_workbench.domain.documents import ExtractedDocument, ExtractedSegment
from legal_workbench.domain.enums import DocumentExtractionStatus


class _Extractor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, path: Path, mime_type: str) -> ExtractedDocument:
        self.calls.append(path.name)
        content = path.read_text(encoding="utf-8")
        return ExtractedDocument(
            status=DocumentExtractionStatus.SUCCEEDED,
            segments=(
                ExtractedSegment(
                    page_number=None,
                    paragraph_number=1,
                    start_offset=0,
                    end_offset=len(content),
                    content=content,
                    content_hash=sha256(content.encode()).hexdigest(),
                ),
            ),
            page_count=None,
            character_count=len(content),
        )


def test_inventory_is_local_deterministic_and_compares_full_prompt_to_retrieval(
    tmp_path: Path,
) -> None:
    source = tmp_path / "materials"
    (source / "法规").mkdir(parents=True)
    (source / "法规" / "a.txt").write_text("abcd", encoding="utf-8")
    (source / "法规" / "a-copy.md").write_text("abcd", encoding="utf-8")
    (source / "合同").mkdir()
    (source / "合同" / "b.txt").write_text("abcdefgh", encoding="utf-8")
    (source / "unsupported.xlsx").write_bytes(b"sheet")
    extractor = _Extractor()
    estimator = DeterministicTokenEstimator()

    inventory = MaterialInventoryService(extractor, estimator).build(
        source,
        retrieval_budget=KnowledgeBudget(
            max_chunks=2,
            max_tokens=2,
            max_single_chunk_tokens=2,
        ),
    )

    assert inventory.file_count == 4
    assert inventory.parseable_file_count == 3
    assert inventory.unsupported_file_count == 1
    assert inventory.unparseable_file_count == 0
    assert inventory.extracted_character_count == 16
    assert inventory.estimated_token_count == 4
    assert inventory.unique_sha256_token_count == 3
    assert inventory.duplicate_token_savings == 1
    assert inventory.token_count_estimated is True
    assert inventory.token_estimator == "utf8-bytes-ceil-div-4-v1"
    assert inventory.category_token_counts == {"合同": 2, "法规": 2}
    assert inventory.option_a_tokens_per_agent_run == 4
    assert inventory.option_b_tokens_per_agent_run == 2
    assert inventory.tokens_saved_per_agent_run == 2
    assert sorted(extractor.calls) == ["a-copy.md", "b.txt"]


def test_utf8_estimator_is_explicitly_estimated() -> None:
    estimate = DeterministicTokenEstimator().estimate("abcd中")

    assert estimate.tokens == 2
    assert estimate.estimated is True
    assert estimate.method == "utf8-bytes-ceil-div-4-v1"
