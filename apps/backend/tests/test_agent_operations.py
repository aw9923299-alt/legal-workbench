from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.agent_operations import (
    CancelAgentRunCommand,
    CancelAgentRunHandler,
)
from legal_workbench.domain.entities import AgentRun, FeishuMessage
from legal_workbench.domain.enums import AgentRunStatus, FeishuMessageStatus


def _message() -> FeishuMessage:
    now = datetime.now(UTC)
    return FeishuMessage(
        id=uuid4(),
        event_id=uuid4(),
        tenant_key="tenant",
        message_id="om_cancel",
        chat_id="oc_chat",
        thread_id=None,
        root_id=None,
        parent_id=None,
        sender_id="ou_sender",
        sender_type="user",
        message_type="text",
        content={"text": "cancel"},
        mentions=[],
        create_time=now,
        update_time=None,
        raw_message={},
        status=FeishuMessageStatus.ANALYSING,
    )


def _run(message: FeishuMessage) -> AgentRun:
    run = AgentRun(
        id=uuid4(),
        agent_definition_id=uuid4(),
        context_snapshot_id=uuid4(),
        status=AgentRunStatus.QUEUED,
        objective="judge",
        prompt_snapshot="prompt",
        working_directory="/tmp/run",
        attempt_number=1,
        max_attempts=3,
        correlation_id="corr-run",
        created_by="system",
        feishu_message_id=message.id,
    )
    run.transition_to(AgentRunStatus.PREPARING)
    run.transition_to(AgentRunStatus.RUNNING)
    run.drain_status_changes()
    return run


class _Repo:
    def __init__(self, value):  # type: ignore[no-untyped-def]
        self.value = value

    async def get_for_update(self, _: UUID):  # type: ignore[no-untyped-def]
        return self.value

    async def get_message_for_update(self, _: UUID):  # type: ignore[no-untyped-def]
        return self.value

    async def save(self, value) -> None:  # type: ignore[no-untyped-def]
        self.value = value

    async def save_message(self, value) -> None:  # type: ignore[no-untyped-def]
        self.value = value


class _Idempotency:
    async def get(self, *, operation: str, key: str):  # type: ignore[no-untyped-def]
        return None

    async def add(self, record) -> None:  # type: ignore[no-untyped-def]
        self.record = record


class _Events:
    def __init__(self) -> None:
        self.values = []

    async def add(self, value) -> None:  # type: ignore[no-untyped-def]
        self.values.append(value)


class _Uow:
    def __init__(self, run: AgentRun, message: FeishuMessage) -> None:
        self.agent_runs = _Repo(run)
        self.feishu = _Repo(message)
        self.idempotency = _Idempotency()
        self.audit_events = _Events()
        self.commits = 0

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_cancel_agent_run_uses_domain_transition_and_audit() -> None:
    message = _message()
    run = _run(message)
    uow = _Uow(run, message)

    result = await CancelAgentRunHandler(lambda: uow).execute(
        CancelAgentRunCommand(
            run_id=run.id,
            actor_id="legal-user",
            actor_source="local_session",
            correlation_id="corr-cancel",
            idempotency_key="idem-cancel",
        )
    )

    assert result.status == AgentRunStatus.CANCELLED
    assert run.status == AgentRunStatus.CANCELLED
    assert message.status == FeishuMessageStatus.ANALYSIS_FAILED
    assert message.failure_code == "AGENT_RUNTIME_CANCELLED"
    assert uow.audit_events.values[0].event_type == "agent_run_cancelled"
    assert uow.commits == 1
