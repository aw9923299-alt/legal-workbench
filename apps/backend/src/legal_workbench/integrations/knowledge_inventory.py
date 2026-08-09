from __future__ import annotations

import argparse
import json
from pathlib import Path

from legal_workbench.application.material_inventory import MaterialInventoryService
from legal_workbench.application.token_budget import (
    DeterministicTokenEstimator,
    KnowledgeBudget,
)
from legal_workbench.config import get_settings
from legal_workbench.integrations.document_extractors import IsolatedExtractionProcessRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic local material inventory.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    settings = get_settings()
    source = Path(args.source).resolve(strict=True)
    inventory = MaterialInventoryService(
        IsolatedExtractionProcessRunner(
            attachment_root=source,
            work_root=Path(settings.document_extraction_work_root),
            max_file_bytes=settings.knowledge_import_max_file_bytes,
            timeout_seconds=settings.document_extraction_timeout_seconds,
            max_output_bytes=settings.document_extraction_max_output_bytes,
        ),
        DeterministicTokenEstimator(),
    ).build(
        source,
        retrieval_budget=KnowledgeBudget(
            max_chunks=settings.legal_knowledge_max_chunks,
            max_tokens=settings.legal_knowledge_max_tokens,
            max_single_chunk_tokens=settings.legal_knowledge_max_single_chunk_tokens,
        ),
    )
    payload = {
        "schemaVersion": "legal-material-inventory-v1",
        "fileCount": inventory.file_count,
        "extensionStats": {
            extension: {
                "fileCount": value.file_count,
                "diskSize": value.disk_size,
            }
            for extension, value in inventory.extension_stats.items()
        },
        "parseableFileCount": inventory.parseable_file_count,
        "unparseableFileCount": inventory.unparseable_file_count,
        "unsupportedFileCount": inventory.unsupported_file_count,
        "totalDiskSize": inventory.total_disk_size,
        "extractedCharacterCount": inventory.extracted_character_count,
        "estimatedTokenCount": inventory.estimated_token_count,
        "uniqueSha256TokenCount": inventory.unique_sha256_token_count,
        "duplicateTokenSavings": inventory.duplicate_token_savings,
        "categoryTokenCounts": inventory.category_token_counts,
        "tokenCounting": {
            "estimated": inventory.token_count_estimated,
            "method": inventory.token_estimator,
        },
        "agentRunComparison": {
            "optionAFullPromptTokens": inventory.option_a_tokens_per_agent_run,
            "optionBRetrievalTokens": inventory.option_b_tokens_per_agent_run,
            "tokensSavedPerRun": inventory.tokens_saved_per_agent_run,
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "fileCount": inventory.file_count,
                "output": str(output),
                "tokenCount": inventory.estimated_token_count,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
