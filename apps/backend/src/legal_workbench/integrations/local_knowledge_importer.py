from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from legal_workbench.application.local_knowledge_import import LocalKnowledgeImportService
from legal_workbench.config import get_settings
from legal_workbench.infrastructure.database import dispose_engine
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from legal_workbench.integrations.document_extractors import IsolatedExtractionProcessRunner


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    source = Path(args.source).resolve(strict=True)
    extractor = IsolatedExtractionProcessRunner(
        attachment_root=source,
        work_root=Path(settings.document_extraction_work_root),
        max_file_bytes=settings.knowledge_import_max_file_bytes,
        timeout_seconds=settings.document_extraction_timeout_seconds,
        max_output_bytes=settings.document_extraction_max_output_bytes,
    )
    service = LocalKnowledgeImportService(SqlAlchemyUnitOfWorkFactory(), extractor)
    try:
        scan = await service.execute(
            source=source,
            source_root_key=args.source_root_key,
            correlation_id=f"knowledge-import:{uuid4().hex}",
        )
    finally:
        await dispose_engine()
    print(
        json.dumps(
            {
                "scanId": str(scan.id),
                "sourceRootKey": scan.source_root_key,
                "status": scan.status.value,
                "discoveredCount": scan.discovered_count,
                "unchangedCount": scan.unchanged_count,
                "importedCount": scan.imported_count,
                "deduplicatedCount": scan.deduplicated_count,
                "unsupportedCount": scan.unsupported_count,
                "failedCount": scan.failed_count,
                "missingCount": scan.missing_count,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if scan.failed_count == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a read-only local legal source tree.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-root-key", default="codex_obs_legal")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
