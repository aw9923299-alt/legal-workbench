from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

from legal_workbench.domain.enums import DocumentExtractionStatus
from legal_workbench.infrastructure.outbox import OUTBOX_HANDLERS, ClaimedOutboxEvent
from legal_workbench.integrations.document_extractors import (
    ExtractionOutputTooLargeError,
    ExtractionProcessTimeoutError,
    IsolatedExtractionProcessRunner,
    safe_extraction_environment,
)


def test_child_environment_excludes_application_credentials() -> None:
    environment = safe_extraction_environment(
        {
            "PATH": "/usr/bin",
            "LANG": "zh_CN.UTF-8",
            "OPENAI_API_KEY": "must-not-pass",
            "LEGAL_WORKBENCH_DATABASE_URL": "must-not-pass",
            "LEGAL_WORKBENCH_REDIS_URL": "must-not-pass",
            "LEGAL_WORKBENCH_FEISHU_APP_SECRET": "must-not-pass",
            "CODEX_HOME": "must-not-pass",
        }
    )

    assert environment == {"LANG": "zh_CN.UTF-8", "PATH": "/usr/bin"}


def test_isolated_process_extracts_one_authorized_file(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    root.mkdir()
    document = root / "sample.txt"
    document.write_text("第一段。\n\n第二段。", encoding="utf-8")

    result = IsolatedExtractionProcessRunner(
        attachment_root=root,
        work_root=tmp_path / "work",
        max_file_bytes=1024,
        timeout_seconds=5,
        max_output_bytes=4096,
    ).extract(document, "text/plain")

    assert result.status == DocumentExtractionStatus.SUCCEEDED
    assert [value.content for value in result.segments] == ["第一段。", "第二段。"]


def test_isolated_process_timeout_is_explicit(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    root.mkdir()
    document = root / "sample.txt"
    document.write_text("safe", encoding="utf-8")
    sleeper = tmp_path / "sleep.py"
    sleeper.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")

    runner = IsolatedExtractionProcessRunner(
        attachment_root=root,
        work_root=tmp_path / "work",
        max_file_bytes=1024,
        timeout_seconds=0.05,
        max_output_bytes=4096,
        command=[sys.executable, str(sleeper)],
    )

    with pytest.raises(ExtractionProcessTimeoutError):
        runner.extract(document, "text/plain")


def test_isolated_process_rejects_oversized_result(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    root.mkdir()
    document = root / "sample.txt"
    document.write_text("safe", encoding="utf-8")
    writer = tmp_path / "large_output.py"
    writer.write_text(
        "import pathlib, sys\n"
        "target = pathlib.Path(sys.argv[sys.argv.index('--output') + 1])\n"
        "target.write_text('x' * 10000, encoding='utf-8')\n",
        encoding="utf-8",
    )

    runner = IsolatedExtractionProcessRunner(
        attachment_root=root,
        work_root=tmp_path / "work",
        max_file_bytes=1024,
        timeout_seconds=5,
        max_output_bytes=100,
        command=[sys.executable, str(writer)],
    )

    with pytest.raises(ExtractionOutputTooLargeError):
        runner.extract(document, "text/plain")


@pytest.mark.asyncio
async def test_document_extraction_outbox_dispatches_worker_task(monkeypatch) -> None:
    calls: list[tuple[str, list[str], dict[str, object]]] = []

    def record_task(
        name: str,
        *,
        args: list[str],
        headers: dict[str, object],
    ) -> None:
        calls.append((name, args, headers))

    monkeypatch.setattr("legal_workbench.infrastructure.outbox.celery_app.send_task", record_task)
    attachment_id = uuid4()
    event = ClaimedOutboxEvent(
        id=uuid4(),
        event_type="DocumentExtractionRequested",
        aggregate_type="message_attachment",
        aggregate_id=attachment_id,
        payload={"attachmentId": str(attachment_id)},
        correlation_id="document-extraction-test",
        attempts=0,
    )

    await OUTBOX_HANDLERS[event.event_type](object(), event)  # type: ignore[arg-type]

    assert calls == [
        (
            "document.extract",
            [str(attachment_id), "document-extraction-test"],
            {"correlation_id": "document-extraction-test"},
        )
    ]
