from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from legal_workbench.agents.message_judgement import MessageJudgementResult
from legal_workbench.agents.runtime import AgentExecutionResult
from legal_workbench.application.context_snapshots import ContextSnapshotBuilder
from legal_workbench.application.message_analysis import (
    AnalyseFeishuMessageCommand,
    AnalyseFeishuMessageHandler,
)
from legal_workbench.domain.entities import FeishuMessage, FeishuRawEvent
from legal_workbench.domain.enums import FeishuEventStatus, FeishuMessageStatus


class FakeAgentRuntime:
    def __init__(self, source_message_id: str) -> None:
        self._source_message_id = source_message_id

    async def execute(self, definition, run, context):  # type: ignore[no-untyped-def]
        del definition, context
        run.input_payload = {"runtimeAttempt": run.attempt_number}
        run.working_directory = f"{run.working_directory}/actual-attempt"
        return AgentExecutionResult(
            output=MessageJudgementResult.model_validate(
                {
                    "legalRelevance": "relevant",
                    "messageRole": "new_request",
                    "actionability": "create_candidate",
                    "suggestedTitle": "审核数据库集成测试合同",
                    "categoryCandidates": [
                        {
                            "category": "contract",
                            "confidence": 0.91,
                            "reason": "明确提出审核请求",
                        }
                    ],
                    "deadlineCandidates": [],
                    "confirmedFacts": [
                        {
                            "statement": "请求审核合同",
                            "sourceMessageId": self._source_message_id,
                        }
                    ],
                    "inferredFacts": [],
                    "missingInformation": ["合同附件"],
                    "reasons": ["消息包含明确法务行动要求"],
                    "confidence": 0.7,
                }
            ),
            raw_stdout="fake postgres integration runtime",
            raw_stderr="",
            output_path=Path(run.working_directory) / "output.json",
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_feishu_message_to_snapshot_run_and_candidate_in_postgres(tmp_path) -> None:  # type: ignore[no-untyped-def]
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    uow_factory = SqlAlchemyUnitOfWorkFactory(async_sessionmaker(engine, expire_on_commit=False))
    event = FeishuRawEvent(
        id=uuid4(),
        event_id=f"evt-{uuid4().hex}",
        event_type="im.message.receive_v1",
        tenant_key="tenant-integration",
        app_id="cli-test",
        schema_version="2.0",
        raw_payload={"test": True},
        payload_hash="a" * 64,
        status=FeishuEventStatus.RECEIVED,
    )
    external_message_id = f"om_postgres_triage_{uuid4().hex}"
    message = FeishuMessage(
        id=uuid4(),
        event_id=event.id,
        tenant_key=event.tenant_key,
        message_id=external_message_id,
        chat_id=f"chat-{uuid4().hex}",
        thread_id=None,
        root_id=None,
        parent_id=None,
        sender_id="ou_business",
        sender_type="user",
        message_type="text",
        content={"text": "请法务审核合同"},
        mentions=[],
        create_time=datetime.now(UTC),
        update_time=None,
        raw_message={"message_id": external_message_id},
        status=FeishuMessageStatus.RECEIVED,
    )
    try:
        async with uow_factory() as uow:
            await uow.feishu.add_event(event)
            await uow.feishu.add_message(message)
            await uow.commit()

        result = await AnalyseFeishuMessageHandler(
            uow_factory,
            FakeAgentRuntime(external_message_id),
            ContextSnapshotBuilder(uow_factory, max_messages=10, max_text_characters=5000),
            runs_root=tmp_path,
            manual_review_threshold=0.75,
        ).execute(
            AnalyseFeishuMessageCommand(
                message_id=message.id,
                actor_id="integration-test",
                actor_source="test",
                correlation_id=f"corr-{uuid4().hex}",
            )
        )
        rerun = await AnalyseFeishuMessageHandler(
            uow_factory,
            FakeAgentRuntime(external_message_id),
            ContextSnapshotBuilder(uow_factory, max_messages=10, max_text_characters=5000),
            runs_root=tmp_path,
            manual_review_threshold=0.75,
        ).execute(
            AnalyseFeishuMessageCommand(
                message_id=message.id,
                actor_id="integration-test",
                actor_source="test",
                correlation_id=f"corr-{uuid4().hex}",
                force_new_run=True,
            )
        )

        async with uow_factory() as uow:
            stored_message = await uow.feishu.get_message_by_id(message.id)
            snapshot = await uow.context_snapshots.get(stored_message.context_snapshot_id)  # type: ignore[union-attr,arg-type]
            run = await uow.agent_runs.get(result.agent_run_id)
            status_events = await uow.agent_runs.list_status_events(result.agent_run_id)
            candidate = await uow.candidates.get_active_for_message(message.id)
            revisions = list(
                await uow.candidates.list_revisions(candidate.id) if candidate else []
            )

        assert stored_message is not None
        assert stored_message.status == FeishuMessageStatus.CANDIDATE_CREATED
        assert snapshot is not None
        assert run is not None and run.output_payload is not None
        assert run.input_payload == {"runtimeAttempt": 1}
        assert run.working_directory.endswith("/actual-attempt")
        assert candidate is not None and candidate.requires_manual_review is True
        assert candidate.confidence == 0.7
        assert [event.to_status.value for event in status_events] == [
            "queued",
            "preparing",
            "running",
            "validating",
            "completed",
        ]
        assert rerun.agent_run_id != result.agent_run_id
        assert len(revisions) == 2
        assert revisions[0].agent_run_id == rerun.agent_run_id
        assert revisions[0].superseded_at is None
        assert revisions[1].agent_run_id == run.id
        assert revisions[1].superseded_by == revisions[0].id
    finally:
        await engine.dispose()
