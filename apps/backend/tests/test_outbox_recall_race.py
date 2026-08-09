from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest

from legal_workbench.application.message_analysis_eligibility import (
    MessageAnalysisEligibilityDecision,
)
from legal_workbench.infrastructure.outbox import ClaimedOutboxEvent, OutboxDispatcher


@dataclass
class _DispatchGuard:
    decision: MessageAnalysisEligibilityDecision
    calls: list[tuple[object, str, bool]]

    async def evaluate_and_audit(
        self,
        *,
        message_id: object,
        actor_id: str,
        actor_source: str,
        override_recalled: bool,
        correlation_id: str,
    ) -> MessageAnalysisEligibilityDecision:
        del actor_id, correlation_id
        self.calls.append((message_id, actor_source, override_recalled))
        return self.decision


@pytest.mark.asyncio
async def test_dispatcher_acknowledges_recalled_automatic_event_without_worker_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[str] = []
    monkeypatch.setattr(
        "legal_workbench.infrastructure.outbox.celery_app.send_task",
        lambda name, *args, **kwargs: dispatched.append(name),
    )
    guard = _DispatchGuard(
        decision=MessageAnalysisEligibilityDecision(
            allowed=False,
            reason="message_recalled",
            manual_override=False,
        ),
        calls=[],
    )
    dispatcher = object.__new__(OutboxDispatcher)
    dispatcher._analysis_dispatch_guard = guard
    message_id = uuid4()
    event = ClaimedOutboxEvent(
        id=uuid4(),
        event_type="FeishuMessageAnalysisRequested",
        aggregate_type="feishu_message",
        aggregate_id=message_id,
        payload={"actorId": "analysis-recovery", "actorSource": "system"},
        correlation_id="corr-recalled-outbox",
        attempts=0,
    )

    await dispatcher._dispatch(event)

    assert guard.calls == [(message_id, "system", False)]
    assert dispatched == []


@pytest.mark.asyncio
async def test_dispatcher_allows_explicit_user_override_for_recalled_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "legal_workbench.infrastructure.outbox.celery_app.send_task",
        lambda name, *args, **kwargs: dispatched.append((name, kwargs)),
    )
    guard = _DispatchGuard(
        decision=MessageAnalysisEligibilityDecision(
            allowed=True,
            reason="manual_override",
            manual_override=True,
        ),
        calls=[],
    )
    dispatcher = object.__new__(OutboxDispatcher)
    dispatcher._analysis_dispatch_guard = guard
    event = ClaimedOutboxEvent(
        id=uuid4(),
        event_type="FeishuMessageAnalysisRequested",
        aggregate_type="feishu_message",
        aggregate_id=uuid4(),
        payload={
            "actorId": "legal-reviewer",
            "actorSource": "user",
            "overrideRecalled": True,
        },
        correlation_id="corr-recalled-user-override",
        attempts=0,
    )

    await dispatcher._dispatch(event)

    assert guard.calls == [(event.aggregate_id, "user", True)]
    assert dispatched[0][0] == "feishu.process_message"
    assert dispatched[0][1]["kwargs"] == {
        "force_new_run": False,
        "recover_interrupted_run": False,
        "override_recalled": True,
    }
