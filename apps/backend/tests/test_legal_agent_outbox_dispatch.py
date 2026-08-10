from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from legal_workbench.application.legal_agent_orchestrator import LegalAgentTrigger
from legal_workbench.infrastructure.outbox import OUTBOX_HANDLERS, ClaimedOutboxEvent
from legal_workbench.workers.tasks import _orchestrate_legal_agents


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


@pytest.mark.asyncio
async def test_legal_agent_worker_preserves_historical_analysis_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    triggers: list[LegalAgentTrigger] = []

    class FakeOrchestrator:
        async def execute(self, trigger: LegalAgentTrigger) -> object:
            triggers.append(trigger)
            return SimpleNamespace(
                plan_id=uuid4(),
                status=SimpleNamespace(value="completed"),
                planning_run_id=None,
                synthesis_run_id=None,
                artifact_id=None,
                review_package_id=None,
                idempotent_replay=False,
            )

    monkeypatch.setattr(
        "legal_workbench.workers.tasks._build_legal_agent_orchestrator",
        FakeOrchestrator,
    )
    await _orchestrate_legal_agents(
        {
            "matterId": str(uuid4()),
            "contextSnapshotId": str(uuid4()),
            "objective": "按历史时点分析",
            "idempotencyKey": "historical-worker-fixture",
            "historicalAsOf": "2024-01-15",
        },
        "historical-worker-correlation",
    )

    assert len(triggers) == 1
    assert triggers[0].historical_as_of is not None
    assert triggers[0].historical_as_of.isoformat() == "2024-01-15"
