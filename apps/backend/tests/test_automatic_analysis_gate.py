from __future__ import annotations

from types import TracebackType
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.automatic_analysis_gate import AutomaticAnalysisGate
from legal_workbench.domain.entities import FeishuMessage, OutboxEvent
from legal_workbench.infrastructure.outbox import OUTBOX_HANDLERS, ClaimedOutboxEvent


class _FeishuRepository:
    def __init__(self, message: FeishuMessage) -> None:
        self.message = message

    async def get_message_by_id(self, message_id: UUID) -> FeishuMessage | None:
        return self.message if self.message.id == message_id else None


class _OutboxRepository:
    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []

    async def exists_pending(self, *, event_type: str, aggregate_id: UUID) -> bool:
        return any(
            event.event_type == event_type and event.aggregate_id == aggregate_id
            for event in self.events
        )

    async def add(self, event: OutboxEvent) -> None:
        self.events.append(event)


class _UnitOfWork:
    def __init__(self, message: FeishuMessage) -> None:
        self.feishu = _FeishuRepository(message)
        self.outbox_events = _OutboxRepository()
        self.locks: list[tuple[str, str]] = []

    async def __aenter__(self) -> _UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        self.locks.append((operation, key))


def _message(disposition: str) -> FeishuMessage:
    return FeishuMessage(
        id=uuid4(),
        event_id=uuid4(),
        tenant_key="tenant-test",
        message_id="om-policy-test",
        chat_id="oc-policy-test",
        thread_id=None,
        root_id=None,
        parent_id=None,
        sender_id="ou-test",
        sender_type="user",
        message_type="file",
        content={},
        mentions=[],
        create_time=None,
        update_time=None,
        raw_message={},
        analysis_disposition=disposition,
    )


@pytest.mark.asyncio
async def test_store_only_message_cannot_enqueue_automatic_analysis() -> None:
    message = _message("store_only")
    uow = _UnitOfWork(message)

    decision = await AutomaticAnalysisGate().request_if_allowed(
        uow,  # type: ignore[arg-type]
        message.id,
        actor_id="document-extraction-worker",
        actor_source="integration",
        correlation_id="attachment-analysis:test",
    )

    assert decision.requested is False
    assert decision.reason == "message_disposition_store_only"
    assert uow.outbox_events.events == []


@pytest.mark.asyncio
async def test_analyze_message_enqueues_one_automatic_analysis() -> None:
    message = _message("analyze")
    uow = _UnitOfWork(message)
    gate = AutomaticAnalysisGate()

    first = await gate.request_if_allowed(
        uow,  # type: ignore[arg-type]
        message.id,
        actor_id="document-extraction-worker",
        actor_source="integration",
        correlation_id="attachment-analysis:test",
    )
    second = await gate.request_if_allowed(
        uow,  # type: ignore[arg-type]
        message.id,
        actor_id="document-extraction-worker",
        actor_source="integration",
        correlation_id="attachment-analysis:test",
    )

    assert first.requested is True
    assert first.reason == "analysis_requested"
    assert second.requested is False
    assert second.reason == "analysis_already_pending"
    assert [event.event_type for event in uow.outbox_events.events] == [
        "FeishuMessageAnalysisRequested"
    ]
    assert uow.outbox_events.events[0].payload["actorSource"] == "integration"


@pytest.mark.asyncio
async def test_legacy_message_received_event_never_dispatches_analysis_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[str] = []
    monkeypatch.setattr(
        "legal_workbench.infrastructure.outbox.celery_app.send_task",
        lambda name, *args, **kwargs: dispatched.append(name),
    )
    event = ClaimedOutboxEvent(
        id=uuid4(),
        event_type="FeishuMessageReceived",
        aggregate_type="feishu_message",
        aggregate_id=uuid4(),
        payload={},
        correlation_id="legacy-store-only",
        attempts=0,
    )

    await OUTBOX_HANDLERS[event.event_type](object(), event)  # type: ignore[arg-type]

    assert dispatched == []
