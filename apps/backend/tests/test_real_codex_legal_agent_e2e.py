# ruff: noqa: RUF001

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from legal_workbench.agents.codex_cli import CodexCliRuntime
from legal_workbench.application.knowledge import KnowledgeRetrievalService
from legal_workbench.application.legal_agent_orchestrator import (
    LegalAgentOrchestrator,
    LegalAgentTrigger,
)
from legal_workbench.application.legal_context import LegalContextBuilder
from legal_workbench.domain.entities import (
    ContextSnapshot,
    KnowledgeChunk,
    KnowledgeDocument,
    LegalMatter,
)
from legal_workbench.domain.enums import (
    AgentExecutionPlanStatus,
    AgentRunRole,
    BusinessImpact,
    Confidentiality,
    LegalRisk,
    MatterCategory,
)


def _snapshot(matter_id: object, text: str) -> ContextSnapshot:
    content_hash = sha256(text.encode()).hexdigest()
    snapshot_id = uuid4()
    return ContextSnapshot(
        id=snapshot_id,
        source_type="synthetic_real_codex_e2e",
        source_id=uuid4().hex,
        source_ids=["synthetic-e2e"],
        message_ids=[f"synthetic-{uuid4().hex}"],
        file_ids=[],
        relevant_matter_ids=[str(matter_id)],
        participant_ids=["synthetic-business-user"],
        permission_snapshot={"synthetic": True, "authorized": True},
        generated_at=datetime.now(UTC),
        content_hash=content_hash,
        included_segments=[
            {
                "contentHash": content_hash,
                "paragraphNumber": 1,
                "content": text,
            }
        ],
        content={
            "messages": [
                {
                    "messageId": "synthetic-e2e-message",
                    "plainText": text,
                }
            ]
        },
        builder_version="real-e2e-v1",
        selection_policy_version="real-e2e-v1",
        original_size=len(text),
        included_size=len(text),
    )


@pytest.mark.real_codex
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_codex_single_and_multi_agent_e2e() -> None:
    if os.getenv("RUN_REAL_CODEX_E2E") != "1":
        pytest.skip("Real Codex Legal Agent E2E is explicitly gated")
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.models import (
        CommunicationModel,
        DraftArtifactModel,
        ReviewPackageModel,
    )
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    factory = SqlAlchemyUnitOfWorkFactory(session_factory)
    rules_text = (
        "非敏感测试业务规则：合作合同应明确责任范围和责任上限；使用图片、音乐等素材前，"
        "应取得覆盖使用主体、渠道、地域和期限的书面授权，并留存授权链证据。"
    )
    document = KnowledgeDocument(
        id=uuid4(),
        source_type="synthetic_e2e_fixture",
        source_id=uuid4().hex,
        title="非敏感合作与素材授权测试业务规则",
        document_type="business_rule",
        agent_types=["*"],
        matter_types=["*"],
        jurisdiction="CN",
        effective_from=date(2026, 1, 1),
        source_priority=100,
        internal_precedent=False,
        confidentiality="internal",
        approved_by="synthetic-fixture",
    )
    chunk = KnowledgeChunk(
        id=uuid4(),
        knowledge_document_id=document.id,
        sequence=1,
        locator="测试业务规则第1段",
        text=rules_text,
        normalized_text=rules_text.casefold(),
        text_hash=sha256(rules_text.encode()).hexdigest(),
    )
    cases = [
        {
            "name": "single",
            "title": "非敏感宣传内容法律咨询",
            "category": MatterCategory.GENERAL_CONSULTATION,
            "secondary": [],
            "objective": "判断虚构官网宣传图片授权资料不完整时应如何处理",
            "text": (
                "业务拟在官网发布一张合作方提供的宣传图片，目前只收到口头同意，"
                "未提供书面授权。"
            ),
            "specialist": "legal_consultation",
            "expected_agents": {"legal_consultation"},
        },
        {
            "name": "dispute",
            "title": "非敏感虚构服务费争议",
            "category": MatterCategory.DISPUTE,
            "secondary": [],
            "objective": "整理虚构服务费争议时间线、主张、抗辩与证据缺口",
            "text": (
                "虚构服务项目约定完成验收后付款。服务方称已通过邮件交付，客户以未达到"
                "验收标准为由拒付。目前只有服务方制作的工作汇总，没有签字验收记录、"
                "完整往来邮件、付款凭证或客户提出质量异议的时间记录。"
            ),
            "specialist": "dispute_complaint",
            "expected_agents": {"dispute_complaint"},
        },
        {
            "name": "labor",
            "title": "非敏感虚构违纪解除评估",
            "category": MatterCategory.EMPLOYMENT,
            "secondary": [],
            "objective": "分开评估虚构违纪解除的实体依据和程序风险",
            "text": (
                "虚构员工一个月内多次迟到，公司拟以严重违纪解除。目前只有考勤汇总，"
                "未提供规章制度的制定程序、公示或签收记录、历次处分、员工申辩、工会"
                "通知及解除通知送达记录。"
            ),
            "specialist": "labor_employment",
            "expected_agents": {"labor_employment"},
        },
        {
            "name": "multi",
            "title": "非敏感合作合同与图片授权审查",
            "category": MatterCategory.CONTRACT,
            "secondary": [MatterCategory.INTELLECTUAL_PROPERTY],
            "objective": "审查虚构合作合同第8.2条责任上限及图片著作权授权链",
            "text": (
                "虚构合同第8.2条：乙方对任何损失承担全部责任且无责任上限。"
                "附件说明双方可使用合作图片，但没有权利人、渠道、地域和期限信息。"
            ),
            "specialist": None,
            "expected_agents": {"contract_review", "ip_copyright"},
        },
    ]
    runs_root = Path(os.environ["LEGAL_WORKBENCH_REAL_E2E_RUNS_ROOT"])
    runtime = CodexCliRuntime(runs_root=runs_root)
    orchestrator = LegalAgentOrchestrator(
        factory,
        runtime,
        LegalContextBuilder(KnowledgeRetrievalService(factory)),
        runs_root=runs_root,
    )
    try:
        async with factory() as uow:
            await uow.knowledge.add_document(document)
            await uow.flush()
            await uow.knowledge.add_chunks([chunk])
            await uow.commit()
        async with session_factory() as session:
            communications_before = int(
                await session.scalar(select(func.count(CommunicationModel.id))) or 0
            )
        for case in cases:
            matter = LegalMatter.create(
                title=str(case["title"]),
                primary_category=case["category"],
                secondary_categories=case["secondary"],
                owner_id="synthetic-e2e-user",
                legal_risk=LegalRisk.MEDIUM,
                business_impact=BusinessImpact.PROJECT,
                confidentiality=Confidentiality.INTERNAL,
                requester_ids=[],
                summary="合成非敏感 Real Codex E2E。",
                objective=str(case["objective"]),
            )
            snapshot = _snapshot(matter.id, str(case["text"]))
            async with factory() as uow:
                await uow.matters.add(matter)
                await uow.context_snapshots.add(snapshot)
                await uow.commit()
            result = await orchestrator.execute(
                LegalAgentTrigger(
                    matter_id=matter.id,
                    context_snapshot_id=snapshot.id,
                    objective=str(case["objective"]),
                    actor_id="synthetic-e2e-user",
                    correlation_id=f"real-e2e:{case['name']}:{uuid4().hex}",
                    idempotency_key=f"real-e2e:{case['name']}:{uuid4().hex}",
                    specialist_only=case["specialist"],
                )
            )
            assert result.status in {
                AgentExecutionPlanStatus.COMPLETED,
                AgentExecutionPlanStatus.NEEDS_INFORMATION,
            }
            assert result.artifact_id is not None
            assert result.review_package_id is not None
            async with factory() as uow:
                plan = await uow.agent_execution_plans.get(result.plan_id)
                runs = list(await uow.agent_runs.list_by_plan(result.plan_id))
            assert plan is not None
            assert {step.agent_key for step in plan.steps} == case["expected_agents"]
            assert all(step.latest_run_id for step in plan.steps)
            assert {run.run_role for run in runs} == {
                AgentRunRole.BUTLER_PLANNING,
                AgentRunRole.SPECIALIST,
                AgentRunRole.BUTLER_SYNTHESIS,
            }
            specialist_runs = [
                run for run in runs if run.run_role == AgentRunRole.SPECIALIST
            ]
            assert all(run.output_payload for run in specialist_runs)
            assert all(run.parent_run_id == plan.planning_run_id for run in runs[1:])
            async with session_factory() as session:
                artifact = await session.get(DraftArtifactModel, result.artifact_id)
                review = await session.get(ReviewPackageModel, result.review_package_id)
            assert artifact is not None
            assert artifact.structured_payload["participatingAgents"]
            assert artifact.structured_payload["citations"]
            assert review is not None
        async with session_factory() as session:
            communications_after = int(
                await session.scalar(select(func.count(CommunicationModel.id))) or 0
            )
        assert communications_after == communications_before
    finally:
        await engine.dispose()
