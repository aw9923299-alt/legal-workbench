from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_proposal_review_persists_human_values_atomically() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.application.matter_updates import (
        CreateMatterUpdateProposalCommand,
        CreateMatterUpdateProposalHandler,
        ReviewMatterUpdateProposalCommand,
        ReviewMatterUpdateProposalHandler,
    )
    from legal_workbench.domain.entities import (
        ContextSnapshot,
        LegalMatter,
        MessageCandidate,
        ProposalFieldDecision,
    )
    from legal_workbench.domain.enums import (
        BusinessImpact,
        CandidateStatus,
        Confidentiality,
        LegalRelevance,
        LegalRisk,
        MatterCategory,
        MessageRole,
        Priority,
        ProposalFieldDecisionType,
        RecommendedAction,
    )
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    uow_factory = SqlAlchemyUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    unique = uuid4().hex
    snapshot = ContextSnapshot(
        id=uuid4(),
        source_type="proposal_integration",
        source_id=unique,
        source_ids=[unique],
        message_ids=[f"message-{unique}"],
        file_ids=[],
        relevant_matter_ids=[],
        participant_ids=["legal-reviewer"],
        permission_snapshot={"test": True},
        generated_at=datetime.now(UTC),
        content_hash=unique.ljust(64, "0"),
    )
    candidate = MessageCandidate(
        id=uuid4(),
        context_snapshot_id=snapshot.id,
        status=CandidateStatus.PENDING_CONFIRMATION,
        legal_relevance=LegalRelevance.RELEVANT,
        message_role=MessageRole.PROGRESS_UPDATE,
        recommended_action=RecommendedAction.UPDATE_MATTER,
        confidence=0.9,
        title_proposal="AI 标题",
        category_proposals=[{"category": "dispute", "confidence": 0.8}],
        deadline_proposals=[{"resolvedAt": "2026-08-10T18:00:00+08:00"}],
    )
    matter = LegalMatter.create(
        title=f"原事项-{unique}",
        primary_category=MatterCategory.CONTRACT,
        secondary_categories=[],
        owner_id="owner-original",
        legal_risk=LegalRisk.MEDIUM,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.INTERNAL,
        requester_ids=[],
        summary=None,
        objective=None,
    )

    try:
        async with uow_factory() as uow:
            await uow.context_snapshots.add(snapshot)
            await uow.flush()
            await uow.candidates.add(candidate)
            await uow.matters.add(matter)
            await uow.commit()

        create_result = await CreateMatterUpdateProposalHandler(uow_factory).execute(
            CreateMatterUpdateProposalCommand(
                candidate_id=candidate.id,
                candidate_version=candidate.version,
                matter_id=matter.id,
                proposed_changes={
                    field: {
                        "currentValue": None,
                        "messageExtractedValue": None,
                        "aiSuggestedValue": None,
                    }
                    for field in ("title", "priority", "deadline", "newWorkItems")
                },
                reason="PostgreSQL integration proposal",
                actor_id="legal-creator",
                correlation_id=f"create-{unique}",
                idempotency_key=f"create-{unique}",
            )
        )
        review_result = await ReviewMatterUpdateProposalHandler(uow_factory).execute(
            ReviewMatterUpdateProposalCommand(
                proposal_id=create_result.proposal_id,
                proposal_version=create_result.version,
                matter_version=matter.version,
                decisions=[
                    ProposalFieldDecision(
                        field_name="title",
                        decision=ProposalFieldDecisionType.APPROVE,
                        final_value="法务最终标题",
                    ),
                    ProposalFieldDecision(
                        field_name="priority",
                        decision=ProposalFieldDecisionType.APPROVE,
                        final_value="urgent",
                    ),
                    ProposalFieldDecision(
                        field_name="deadline",
                        decision=ProposalFieldDecisionType.APPROVE,
                        final_value="2026-08-12T18:00:00+08:00",
                    ),
                    ProposalFieldDecision(
                        field_name="newWorkItems",
                        decision=ProposalFieldDecisionType.APPROVE,
                        final_value=[
                            {
                                "title": "法务确认任务",
                                "ownerId": "legal-reviewer",
                                "priority": "high",
                                "nextAction": "核对全部材料",
                            }
                        ],
                    ),
                ],
                rejection_reason=None,
                actor_id="legal-reviewer",
                correlation_id=f"review-{unique}",
                idempotency_key=f"review-{unique}",
            )
        )

        async with engine.connect() as connection:
            persisted = (
                await connection.execute(
                    text(
                        "SELECT m.title, m.priority, m.version, p.status, p.reviewed_by, "
                        "(SELECT count(*) FROM work_items w WHERE w.matter_id = m.id), "
                        "(SELECT count(*) FROM deadlines d WHERE d.matter_id = m.id) "
                        "FROM legal_matters m JOIN matter_update_proposals p "
                        "ON p.matter_id = m.id WHERE p.id = :proposal_id"
                    ),
                    {"proposal_id": create_result.proposal_id},
                )
            ).one()

        assert review_result.work_item_ids
        assert review_result.deadline_id is not None
        assert persisted == (
            "法务最终标题",
            Priority.URGENT.value,
            2,
            "approved",
            "legal-reviewer",
            1,
            1,
        )
    finally:
        await engine.dispose()
