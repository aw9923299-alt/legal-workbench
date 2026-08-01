from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from legal_workbench.agents.codex_cli import CodexCliRuntime
from legal_workbench.agents.definitions import build_message_judgement_definition
from legal_workbench.agents.runtime import (
    AgentExecutionContext,
    AgentRuntimeError,
)
from legal_workbench.domain.entities import AgentRun, ContextSnapshot
from legal_workbench.domain.enums import AgentRunStatus


def valid_output() -> dict[str, object]:
    return {
        "legalRelevance": "relevant",
        "messageRole": "new_request",
        "actionability": "create_candidate",
        "suggestedTitle": "审核供应商合同",
        "categoryCandidates": [
            {"category": "contract", "confidence": 0.9, "reason": "明确要求审核合同"}
        ],
        "deadlineCandidates": [],
        "confirmedFacts": [{"statement": "请求审核合同", "sourceMessageId": "om_current"}],
        "inferredFacts": [],
        "missingInformation": [],
        "reasons": ["消息包含法务行动要求"],
        "confidence": 0.9,
    }


def make_fake_cli(tmp_path: Path, *, output: str | None, sleep: float = 0) -> list[str]:
    script = tmp_path / f"fake-codex-{uuid4().hex}.py"
    output_literal = repr(output)
    script.write_text(
        "import pathlib, sys, time\n"
        "prompt = sys.stdin.read()\n"
        "if 'om_current' not in prompt or '<authorized_context_json>' not in prompt:\n"
        "    sys.exit(9)\n"
        f"time.sleep({sleep!r})\n"
        f"payload = {output_literal}\n"
        "if payload is not None:\n"
        "    target = pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1])\n"
        "    target.write_text(payload, encoding='utf-8')\n"
        "print('fake runtime stdout')\n",
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def make_context() -> AgentExecutionContext:
    snapshot = ContextSnapshot(
        id=uuid4(),
        source_type="feishu_message",
        source_id="message-db-id",
        source_ids=["om_current"],
        message_ids=["om_current"],
        file_ids=[],
        relevant_matter_ids=[],
        participant_ids=["ou_sender"],
        permission_snapshot={"allowedMessageIds": ["om_current"]},
        generated_at=datetime(2026, 8, 1, tzinfo=UTC),
        content_hash="a" * 64,
        content={
            "messages": [
                {
                    "messageId": "om_current",
                    "senderId": "ou_sender",
                    "messageType": "text",
                    "content": {"text": "请审核合同"},
                    "untrustedInput": True,
                }
            ],
            "truncated": False,
        },
    )
    return AgentExecutionContext(snapshot=snapshot)


def make_run(tmp_path: Path, context: AgentExecutionContext) -> AgentRun:
    definition = build_message_judgement_definition()
    return AgentRun(
        id=uuid4(),
        agent_definition_id=definition.id,
        feishu_message_id=uuid4(),
        context_snapshot_id=context.snapshot.id,
        status=AgentRunStatus.QUEUED,
        objective="Analyse one authorized Feishu message.",
        prompt_snapshot=definition.prompt_template,
        working_directory=str(tmp_path / "unused"),
        attempt_number=1,
        max_attempts=3,
        correlation_id="corr-runtime",
        created_by="system",
    )


def test_runtime_environment_never_inherits_external_codex_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external_codex_home = tmp_path / "external-codex-home"
    monkeypatch.setenv("CODEX_HOME", str(external_codex_home))
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    run_dir = tmp_path / "run"

    environment = CodexCliRuntime._environment(run_dir)

    assert environment["HOME"] == str(run_dir / "empty_home")
    assert environment["CODEX_HOME"] == str(run_dir / "empty_home")
    assert environment["CODEX_HOME"] != str(external_codex_home)
    assert environment["OPENAI_API_KEY"] == "test-api-key"


@pytest.mark.asyncio
async def test_runtime_creates_auditable_files_and_validates_output(tmp_path: Path) -> None:
    context = make_context()
    run = make_run(tmp_path, context)
    runtime = CodexCliRuntime(
        runs_root=tmp_path / "runs",
        command=make_fake_cli(tmp_path, output=json.dumps(valid_output())),
        stdout_limit_bytes=1024,
        stderr_limit_bytes=1024,
        heartbeat_interval_seconds=0.01,
        termination_grace_seconds=0.05,
    )

    execution = await runtime.execute(build_message_judgement_definition(), run, context)

    run_dir = tmp_path / "runs" / str(run.id)
    assert execution.output.suggested_title == "审核供应商合同"
    assert execution.raw_stdout == "fake runtime stdout\n"
    assert {
        "input.json",
        "prompt.md",
        "output.schema.json",
        "output.json",
        "stdout.log",
        "stderr.log",
        "metadata.json",
        "allowed_sources",
        "empty_home",
    } <= {path.name for path in run_dir.iterdir()}
    assert "OPENAI_API_KEY" not in (run_dir / "metadata.json").read_text()
    prompt = (run_dir / "prompt.md").read_text()
    assert "<authorized_context_json>" in prompt
    assert "om_current" in prompt
    assert "请审核合同" in prompt


@pytest.mark.asyncio
async def test_runtime_rejects_definition_with_mismatched_input_schema(tmp_path: Path) -> None:
    context = make_context()
    run = make_run(tmp_path, context)
    definition = build_message_judgement_definition()
    definition.input_schema = {"type": "object", "additionalProperties": True}
    runtime = CodexCliRuntime(
        runs_root=tmp_path / "runs",
        command=make_fake_cli(tmp_path, output=json.dumps(valid_output())),
    )

    with pytest.raises(AgentRuntimeError) as caught:
        await runtime.execute(definition, run, context)

    assert caught.value.code == "AGENT_DEFINITION_DISABLED"
    assert caught.value.retryable is False


@pytest.mark.asyncio
async def test_runtime_timeout_terminates_process(tmp_path: Path) -> None:
    context = make_context()
    definition = build_message_judgement_definition(timeout_seconds=1)
    run = make_run(tmp_path, context)
    runtime = CodexCliRuntime(
        runs_root=tmp_path / "runs",
        command=make_fake_cli(tmp_path, output=json.dumps(valid_output()), sleep=2),
        heartbeat_interval_seconds=0.01,
        termination_grace_seconds=0.05,
    )

    with pytest.raises(AgentRuntimeError) as caught:
        await runtime.execute(definition, run, context)

    assert caught.value.code == "AGENT_RUNTIME_TIMEOUT"
    assert caught.value.retryable is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output", "failure_code"),
    [
        (None, "AGENT_OUTPUT_MISSING"),
        ("not-json", "AGENT_OUTPUT_INVALID_JSON"),
        (json.dumps({"legalRelevance": "relevant"}), "AGENT_OUTPUT_SCHEMA_INVALID"),
    ],
)
async def test_runtime_rejects_invalid_output(
    tmp_path: Path, output: str | None, failure_code: str
) -> None:
    context = make_context()
    run = make_run(tmp_path, context)
    runtime = CodexCliRuntime(
        runs_root=tmp_path / "runs",
        command=make_fake_cli(tmp_path, output=output),
        heartbeat_interval_seconds=0.01,
    )

    with pytest.raises(AgentRuntimeError) as caught:
        await runtime.execute(build_message_judgement_definition(), run, context)

    assert caught.value.code == failure_code


@pytest.mark.asyncio
async def test_runtime_retry_preserves_previous_attempt_directory(tmp_path: Path) -> None:
    context = make_context()
    run = make_run(tmp_path, context)
    run.attempt_number = 2
    base_directory = tmp_path / "runs" / str(run.id)
    base_directory.mkdir(parents=True)
    (base_directory / "attempt-001.marker").write_text("preserved", encoding="utf-8")
    runtime = CodexCliRuntime(
        runs_root=tmp_path / "runs",
        command=make_fake_cli(tmp_path, output=json.dumps(valid_output())),
        heartbeat_interval_seconds=0.01,
    )

    execution = await runtime.execute(build_message_judgement_definition(), run, context)

    assert (base_directory / "attempt-001.marker").read_text() == "preserved"
    assert execution.output_path == base_directory / "attempts" / "002" / "output.json"
