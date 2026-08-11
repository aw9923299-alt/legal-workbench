from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from legal_workbench.agents.message_judgement import MessageJudgementResult
from legal_workbench.agents.runtime import AgentExecutionResult
from legal_workbench.application.context_snapshots import ContextSnapshotBuilder
from legal_workbench.application.matter_continuity import MatterContinuityResolver
from legal_workbench.application.message_analysis import (
    AnalyseFeishuMessageCommand,
    AnalyseFeishuMessageHandler,
)
from legal_workbench.domain.entities import (
    ContextSnapshot,
    FeishuMessage,
    FeishuRawEvent,
    LegalMatter,
    MessageCandidate,
)
from legal_workbench.domain.enums import (
    BusinessImpact,
    CandidateMatterRelation,
    CandidateResolutionAction,
    CandidateStatus,
    Confidentiality,
    FeishuEventStatus,
    FeishuMessageStatus,
    LegalRelevance,
    LegalRisk,
    MatterCategory,
    MessageRole,
    RecommendedAction,
)


class FakeExistingMatterRuntime:
    def __init__(self, source_message_id: str) -> None:
        self._source_message_id = source_message_id

    async def execute(self, definition, run, context):  # type: ignore[no-untyped-def]
        del definition, context
        return AgentExecutionResult(
            output=MessageJudgementResult.model_validate(
                {
                    "legalRelevance": "relevant",
                    "messageRole": "existing_matter_update",
                    "actionability": "link_candidate",
                    "suggestedTitle": "补充既有合同事项材料",
                    "categoryCandidates": [
                        {
                            "category": "contract",
                            "confidence": 0.95,
                            "reason": "消息明确补充既有合同事项",
                        }
                    ],
                    "deadlineCandidates": [],
                    "confirmedFacts": [
                        {
                            "statement": "业务补充了合同事项材料",
                            "sourceMessageId": self._source_message_id,
                        }
                    ],
                    "inferredFacts": [],
                    "missingInformation": [],
                    "reasons": ["属于既有合同事项的后续消息"],
                    "confidence": 0.94,
                }
            ),
            raw_stdout="fake continuity postgres runtime",
            raw_stderr="",
            output_path=Path(run.working_directory) / "output.json",
        )


def _event(tenant: str) -> FeishuRawEvent:
    return FeishuRawEvent(
        id=uuid4(),
        event_id=f"evt-continuity-{uuid4().hex}",
        event_type="im.message.receive_v1",
        tenant_key=tenant,
        app_id="integration-test",
        schema_version="2.0",
        raw_payload={"test": "matter-continuity"},
        payload_hash=uuid4().hex.ljust(64, "0")[:64],
        status=FeishuEventStatus.RECEIVED,
    )


def _message(
    event: FeishuRawEvent,
    external_id: str,
    *,
    chat_id: str,
    thread_id: str,
    text: str,
) -> FeishuMessage:
    return FeishuMessage(
        id=uuid4(),
        event_id=event.id,
        tenant_key=event.tenant_key,
        message_id=external_id,
        chat_id=chat_id,
        thread_id=thread_id,
        root_id=None,
        parent_id=None,
        sender_id="ou_business",
        sender_type="user",
        message_type="text",
        content={"text": text},
        mentions=[],
        create_time=datetime.now(UTC),
        update_time=None,
        raw_message={"message_id": external_id},
        status=FeishuMessageStatus.RECEIVED,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_canonical_message_analysis_persists_confirmed_thread_matter_proposal(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    uow_factory = SqlAlchemyUnitOfWorkFactory(async_sessionmaker(engine, expire_on_commit=False))
    tenant = f"tenant-continuity-{uuid4().hex}"
    chat_id = f"oc_{uuid4().hex}"
    thread_id = f"omt_{uuid4().hex}"
    prior_event = _event(tenant)
    current_event = _event(tenant)
    prior_message = _message(
        prior_event,
        f"om_prior_{uuid4().hex}",
        chat_id=chat_id,
        thread_id=thread_id,
        text="此前请法务审核这份合作合同",
    )
    current_external_id = f"om_current_{uuid4().hex}"
    current_message = _message(
        current_event,
        current_external_id,
        chat_id=chat_id,
        thread_id=thread_id,
        text="补充一下刚才合同的付款材料",
    )
    matter = LegalMatter.create(
        title="合作合同审核",
        primary_category=MatterCategory.CONTRACT,
        secondary_categories=[],
        owner_id="local-legal-user",
        legal_risk=LegalRisk.MEDIUM,
        business_impact=BusinessImpact.GENERAL,
        confidentiality=Confidentiality.INTERNAL,
        requester_ids=[],
        summary="业务此前发起的合作合同审核。",
        objective="完成合同审核并回复业务。",
    )
    prior_snapshot = ContextSnapshot(
        id=uuid4(),
        source_type="feishu_message",
        source_id=str(prior_message.id),
        source_ids=[prior_message.message_id],
        message_ids=[prior_message.message_id],
        file_ids=[],
        relevant_matter_ids=[],
        participant_ids=["ou_business"],
        permission_snapshot={},
        generated_at=datetime.now(UTC),
        content_hash="c" * 64,
    )
    prior_candidate = MessageCandidate.create(
        context_snapshot_id=prior_snapshot.id,
        status=CandidateStatus.PENDING_CONFIRMATION,
        legal_relevance=LegalRelevance.RELEVANT,
        message_role=MessageRole.NEW_REQUEST,
        recommended_action=RecommendedAction.CREATE_MATTER,
        confidence=0.95,
        title_proposal="合作合同审核",
        category_proposals=[],
        deadline_proposals=[],
        related_matter_proposals=[],
        evidence_refs=[prior_message.message_id],
        agent_run_id=None,
    )
    prior_candidate.feishu_message_id = prior_message.id
    prior_candidate.resolve(
        action=CandidateResolutionAction.LINK_EXISTING,
        actor_id="local-legal-user",
        expected_version=prior_candidate.version,
    )

    try:
        async with uow_factory() as uow:
            await uow.feishu.add_event(prior_event)
            await uow.feishu.add_event(current_event)
            await uow.feishu.add_message(prior_message)
            await uow.feishu.add_message(current_message)
            await uow.context_snapshots.add(prior_snapshot)
            await uow.matters.add(matter)
            await uow.candidates.add(prior_candidate)
            await uow.flush()
            await uow.candidates.link_to_matter(
                candidate_id=prior_candidate.id,
                matter_id=matter.id,
                relation_type=CandidateMatterRelation.LINKED,
                confirmed_by="local-legal-user",
            )
            await uow.commit()

        result = await AnalyseFeishuMessageHandler(
            uow_factory,
            FakeExistingMatterRuntime(current_external_id),
            ContextSnapshotBuilder(
                uow_factory,
                max_messages=10,
                max_text_characters=5000,
                matter_continuity_resolver=MatterContinuityResolver(),
            ),
            runs_root=tmp_path,
            manual_review_threshold=0.75,
        ).execute(
            AnalyseFeishuMessageCommand(
                message_id=current_message.id,
                actor_id="integration-test",
                actor_source="test",
                correlation_id=f"corr-{uuid4().hex}",
            )
        )

        async with uow_factory() as uow:
            stored_message = await uow.feishu.get_message_by_id(current_message.id)
            assert stored_message is not None and stored_message.context_snapshot_id is not None
            snapshot = await uow.context_snapshots.get(stored_message.context_snapshot_id)
            candidate = await uow.candidates.get_active_for_message(current_message.id)

        assert result.candidate_id is not None
        assert snapshot is not None
        assert snapshot.relevant_matter_ids == [str(matter.id)]
        assert candidate is not None
        assert candidate.related_matter_proposals == [
            {
                "matterId": str(matter.id),
                "matterNumber": matter.matter_number,
                "title": matter.title,
                "confidence": 0.95,
                "signals": ["same_thread_confirmed_link"],
                "evidenceRefs": [f"message:{prior_message.message_id}"],
            }
        ]

        async with engine.connect() as connection:
            audit_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM audit_events "
                    "WHERE aggregate_id = :message_id "
                    "AND event_type = 'matter_continuity_candidates_materialized'"
                ),
                {"message_id": current_message.id},
            )
        assert audit_count == 1
    finally:
        await engine.dispose()
