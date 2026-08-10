from __future__ import annotations

import os
from datetime import UTC, date, datetime
from hashlib import sha256
from uuid import uuid4

import pytest

from legal_workbench.agents.definitions import build_legal_agent_definitions
from legal_workbench.domain.entities import (
    AgentExecutionPlan,
    AgentPlanStep,
    AgentRun,
    ContextSnapshot,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeRetrievalLog,
    LegalMatter,
)
from legal_workbench.domain.enums import (
    AgentExecutionPlanStatus,
    AgentPlanStepStatus,
    AgentRunRole,
    AgentRunStatus,
    BusinessImpact,
    Confidentiality,
    LegalRisk,
    MatterCategory,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_roundtrips_plan_lineage_and_knowledge_provenance() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"])
    uow_factory = SqlAlchemyUnitOfWorkFactory(async_sessionmaker(engine, expire_on_commit=False))
    now = datetime.now(UTC)
    matter = LegalMatter.create(
        title="非敏感合作合同与图片授权测试",
        primary_category=MatterCategory.CONTRACT,
        secondary_categories=[MatterCategory.INTELLECTUAL_PROPERTY],
        owner_id="user:integration",
        legal_risk=LegalRisk.MEDIUM,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.INTERNAL,
        requester_ids=[],
        summary="仅包含虚构测试事实。",
        objective="验证持久化审计链。",
    )
    snapshot = ContextSnapshot(
        id=uuid4(),
        source_type="legal_agent_integration",
        source_id=f"persistence-{uuid4().hex}",
        source_ids=[],
        message_ids=[],
        file_ids=[],
        relevant_matter_ids=[str(matter.id)],
        participant_ids=[],
        permission_snapshot={"scope": "integration-fixture"},
        generated_at=now,
        content_hash=sha256(b"legal-agent-integration").hexdigest(),
    )
    plan_id = uuid4()
    steps = [
        AgentPlanStep(
            id=uuid4(),
            execution_plan_id=plan_id,
            step_id="contract",
            sequence=1,
            agent_key="contract_review",
            objective="定位条款风险",
            depends_on=[],
            context_requirements=["contract_segments"],
        ),
        AgentPlanStep(
            id=uuid4(),
            execution_plan_id=plan_id,
            step_id="ip",
            sequence=2,
            agent_key="ip_copyright",
            objective="核验授权链",
            depends_on=["contract"],
            context_requirements=["license_documents"],
        ),
    ]
    plan = AgentExecutionPlan(
        id=plan_id,
        matter_id=matter.id,
        work_item_id=None,
        objective="审查合同及图片授权",
        status=AgentExecutionPlanStatus.PLANNED,
        task_types=["contract", "ip"],
        synthesis_strategy="按依赖综合",
        missing_information=[],
        requires_user_input=False,
        correlation_id=f"corr-{uuid4().hex}",
        idempotency_key=f"integration:{uuid4().hex}",
        created_by="user:integration",
        analysis_effective_date=date(2026, 8, 10),
        steps=steps,
    )
    definitions = build_legal_agent_definitions()
    planning = AgentRun(
        id=uuid4(),
        agent_definition_id=definitions["legal_butler"].id,
        context_snapshot_id=snapshot.id,
        status=AgentRunStatus.COMPLETED,
        objective=plan.objective,
        prompt_snapshot="non-sensitive butler planning fixture",
        working_directory="/isolated/legal-agent-fixture",
        attempt_number=1,
        max_attempts=2,
        correlation_id=plan.correlation_id,
        created_by="integration-test",
        matter_id=matter.id,
        execution_plan_id=plan.id,
        run_role=AgentRunRole.BUTLER_PLANNING,
    )
    specialist = AgentRun(
        id=uuid4(),
        agent_definition_id=definitions["contract_review"].id,
        context_snapshot_id=snapshot.id,
        status=AgentRunStatus.COMPLETED,
        objective=steps[0].objective,
        prompt_snapshot="non-sensitive contract fixture",
        working_directory="/isolated/legal-agent-fixture",
        attempt_number=1,
        max_attempts=2,
        correlation_id=plan.correlation_id,
        created_by="integration-test",
        matter_id=matter.id,
        execution_plan_id=plan.id,
        plan_step_id=steps[0].id,
        parent_run_id=planning.id,
        run_role=AgentRunRole.SPECIALIST,
    )
    knowledge = KnowledgeDocument(
        id=uuid4(),
        source_type="regulation",
        source_id=f"fixture-{uuid4().hex}",
        title="非敏感法规测试资料",
        document_type="regulation",
        agent_types=["contract_review"],
        matter_types=["contract"],
        jurisdiction="CN",
        effective_from=date(2021, 1, 1),
        source_priority=90,
        internal_precedent=False,
        confidentiality="internal",
        approved_by="user:integration",
    )
    chunk = KnowledgeChunk(
        id=uuid4(),
        knowledge_document_id=knowledge.id,
        sequence=1,
        locator="第一条",
        text="本段仅用于检索集成测试。",
        normalized_text="本段 仅用于 检索 集成测试",
        text_hash=sha256("本段仅用于检索集成测试。".encode()).hexdigest(),
    )

    try:
        async with uow_factory() as uow:
            await uow.matters.add(matter)
            await uow.context_snapshots.add(snapshot)
            for definition in definitions.values():
                if await uow.agent_definitions.get(definition.id) is None:
                    await uow.agent_definitions.add(definition)
            await uow.flush()
            await uow.agent_execution_plans.add(plan)
            await uow.flush()
            await uow.agent_runs.add(planning)
            await uow.agent_runs.add(specialist)
            await uow.flush()
            plan.planning_run_id = planning.id
            steps[0].latest_run_id = specialist.id
            steps[0].status = AgentPlanStepStatus.COMPLETED
            steps[0].attempt_count = 1
            await uow.agent_execution_plans.save(plan)
            await uow.agent_execution_plans.save_step(steps[0])
            await uow.knowledge.add_document(knowledge)
            await uow.flush()
            await uow.knowledge.add_chunks([chunk])
            await uow.knowledge.add_retrieval_log(
                KnowledgeRetrievalLog(
                    id=uuid4(),
                    query_hash=sha256(b"fixture query").hexdigest(),
                    filters={"agentType": "contract_review", "jurisdiction": "CN"},
                    selected_chunk_ids=[chunk.id],
                    component_scores={str(chunk.id): {"fts": 0.8, "priority": 0.9}},
                    correlation_id=plan.correlation_id,
                    agent_run_id=specialist.id,
                )
            )
            await uow.commit()

        async with uow_factory() as uow:
            stored_plan = await uow.agent_execution_plans.get(plan.id)
            children = list(await uow.agent_runs.list_children(planning.id))
            stored_knowledge = await uow.knowledge.get_document(knowledge.id)
            stored_chunks = list(await uow.knowledge.list_chunks(knowledge.id))

        assert stored_plan is not None
        assert stored_plan.analysis_effective_date == date(2026, 8, 10)
        assert stored_plan.planning_run_id == planning.id
        assert stored_plan.steps[0].latest_run_id == specialist.id
        assert stored_plan.steps[0].status == AgentPlanStepStatus.COMPLETED
        assert [(run.id, run.parent_run_id) for run in children] == [(specialist.id, planning.id)]
        assert stored_knowledge is not None
        assert stored_knowledge.internal_precedent is False
        assert stored_chunks == [chunk]
    finally:
        await engine.dispose()
