from __future__ import annotations

from uuid import uuid4

import pytest

from legal_workbench.infrastructure.outbox import OUTBOX_HANDLERS, ClaimedOutboxEvent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "task_name"),
    [
        ("LegalButlerRequested", "legal_agents.orchestrate"),
        ("LegalAgentStepRerunRequested", "legal_agents.rerun_step"),
        ("LegalAgentRecoveryRequested", "legal_agents.recover"),
    ],
)
async def test_legal_agent_outbox_only_dispatches_registered_celery_task(
    monkeypatch: pytest.MonkeyPatch,
    event_type: str,
    task_name: str,
) -> None:
    sent: list[tuple[str, list[object], dict[str, str]]] = []

    def record_task(
        name: str,
        *,
        args: list[object],
        headers: dict[str, str],
    ) -> None:
        sent.append((name, args, headers))

    monkeypatch.setattr(
        "legal_workbench.infrastructure.outbox.celery_app.send_task", record_task
    )
    payload: dict[str, object] = {"fixture": True}
    event = ClaimedOutboxEvent(
        id=uuid4(),
        event_type=event_type,
        aggregate_type="legal_matter",
        aggregate_id=uuid4(),
        payload=payload,
        correlation_id="corr-legal-agent-fixture",
        attempts=0,
    )

    await OUTBOX_HANDLERS[event_type](object(), event)  # type: ignore[arg-type]

    assert sent == [
        (
            task_name,
            [payload, "corr-legal-agent-fixture"],
            {"correlation_id": "corr-legal-agent-fixture"},
        )
    ]
