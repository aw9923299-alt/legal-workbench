# ruff: noqa: RUF001

from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from legal_workbench.agents.legal_butler import (
    ButlerPlanningOutput,
    ButlerSynthesisOutput,
)
from legal_workbench.agents.legal_contracts import (
    ContractReviewProduct,
    IpCopyrightProduct,
    LegalConsultationProduct,
)
from legal_workbench.agents.runtime import (
    AgentExecutionContext,
    AgentExecutionResult,
)
from legal_workbench.application.analysis_recovery import AnalysisRecoveryService
from legal_workbench.application.legal_agent_orchestrator import (
    LegalAgentOrchestrator,
    LegalAgentTrigger,
)
from legal_workbench.application.legal_context import AuthorizedLegalContext
from legal_workbench.domain.entities import ContextSnapshot, LegalMatter
from legal_workbench.domain.enums import (
    AgentExecutionPlanStatus,
    AgentRunRole,
    BusinessImpact,
    Confidentiality,
    LegalRisk,
    MatterCategory,
    ReviewPackageStatus,
)
from legal_workbench.domain.errors import InvalidStateTransitionError

SOURCE_REF = "knowledge:chunk:fixture-law"
STALE_SUMMARY_SOURCE_REF = "knowledge:chunk:stale-summary-only"


def _common_product(
    *, effective_date: str, historical_analysis: bool
) -> dict[str, object]:
    return {
        "executiveSummary": "建议在补齐授权链并收窄责任条款后推进。",
        "facts": [
            {
                "fact": "虚构合作合同包含图片使用安排。",
                "sourceRefs": ["ctx:snapshot:fixture"],
            }
        ],
        "issues": ["合同责任与图片授权范围"],
        "legalBasis": [
            {
                "proposition": "应核验合同约定及授权范围。",
                "sourceRefs": [SOURCE_REF],
                "authorityRole": "formal_legal_basis",
                "jurisdiction": "CN",
                "effectiveDate": effective_date,
                "historicalAnalysis": historical_analysis,
            }
        ],
        "analysis": [
            {
                "conclusion": "现有资料显示需要补充授权链。",
                "supportRefs": ["ctx:snapshot:fixture", SOURCE_REF],
            }
        ],
        "risks": [
            {
                "description": "授权范围不完整",
                "severity": "high",
                "likelihood": "possible",
            }
        ],
        "recommendedActions": ["补充授权文件"],
        "missingInformation": [],
        "assumptions": [],
        "draftResponse": "请补充授权链，并确认责任上限。",
        "confidence": 0.82,
        "citations": [
            {
                "sourceRef": SOURCE_REF,
                "title": "非敏感法律依据 fixture",
                "sourceType": "knowledge_document",
                "locator": "第一条",
                "contentHash": "b" * 64,
                "internalPrecedent": False,
            }
        ],
    }


class FakeContextBuilder:
    def planning(self, snapshot: ContextSnapshot) -> AuthorizedLegalContext:
        return AuthorizedLegalContext(
            payload={"contextSnapshot": snapshot.content},
            source_refs=frozenset({"ctx:snapshot:fixture"}),
            internal_precedent_refs=frozenset(),
        )

    async def specialist(self, **kwargs: object) -> AuthorizedLegalContext:
        agent_type = str(kwargs.get("agent_type") or "")
        retrieval_results = [
            {
                "sourceRef": SOURCE_REF,
                "title": "非敏感法律依据 fixture",
                "textHash": "b" * 64,
                "locator": "第一条",
                "internalPrecedent": False,
                "authorityType": "law",
                "authorityRole": "formal_legal_basis",
                "authorityStatus": "effective",
                "metadataStatus": "ready",
                "jurisdiction": "CN",
                "effectiveFrom": "2021-01-01",
                "effectiveTo": None,
            }
        ]
        if agent_type == "legal_consultation":
            retrieval_results.append(
                {
                    "sourceRef": STALE_SUMMARY_SOURCE_REF,
                    "title": "仅旧下游咨询使用的非敏感 fixture",
                    "textHash": "e" * 64,
                    "locator": "旧咨询段落",
                    "internalPrecedent": False,
                    "authorityType": "law",
                    "authorityRole": "formal_legal_basis",
                    "authorityStatus": "effective",
                    "metadataStatus": "ready",
                    "jurisdiction": "CN",
                    "effectiveFrom": "2021-01-01",
                    "effectiveTo": None,
                }
            )
        source_refs = {"ctx:snapshot:fixture", SOURCE_REF}
        source_refs.update(
            str(value["sourceRef"])
            for value in retrieval_results
        )
        return AuthorizedLegalContext(
            payload={
                "contextSnapshot": {"fixture": True},
                "retrievalResults": retrieval_results,
                "upstreamOutputs": kwargs.get("upstream_outputs", {}),
            },
            source_refs=frozenset(source_refs),
            internal_precedent_refs=frozenset(),
            source_authorities={
                "ctx:snapshot:fixture": {
                    "title": "Authorized ContextSnapshot fixture",
                    "sourceType": "context_snapshot",
                    "locator": None,
                    "contentHash": "a" * 64,
                    "internalPrecedent": False,
                },
                **{
                    str(value["sourceRef"]): {
                        "title": value["title"],
                        "sourceType": "knowledge_document",
                        "locator": value["locator"],
                        "contentHash": value["textHash"],
                        "internalPrecedent": value["internalPrecedent"],
                        "authorityType": value["authorityType"],
                        "authorityRole": value["authorityRole"],
                        "authorityStatus": value["authorityStatus"],
                        "metadataStatus": value["metadataStatus"],
                        "jurisdiction": value["jurisdiction"],
                        "effectiveFrom": value["effectiveFrom"],
                        "effectiveTo": value["effectiveTo"],
                    }
                    for value in retrieval_results
                },
            },
        )


class FakeLegalRuntime:
    def __init__(
        self,
        *,
        crash_at: str | None = None,
        planning_requires_user_input: bool = False,
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self.upstream_by_key: dict[str, list[dict[str, object]]] = {}
        self.crash_at = crash_at
        self.crashed = False
        self.planning_requires_user_input = planning_requires_user_input
        self.block_next_specialist_key: str | None = None
        self.blocked_specialist_entered = asyncio.Event()
        self.release_blocked_specialist = asyncio.Event()

    async def execute(
        self,
        definition: Any,
        run: Any,
        context: AgentExecutionContext,
    ) -> AgentExecutionResult:
        key = definition.key
        phase = str((context.input_payload or {}).get("phase"))
        assert context.heartbeat is not None
        await context.heartbeat()
        self.calls.append((key, phase))
        if phase == "specialist":
            upstream = (context.input_payload or {}).get("upstreamOutputs", {})
            assert isinstance(upstream, dict)
            self.upstream_by_key.setdefault(key, []).append(upstream)
            if self.block_next_specialist_key == key:
                self.block_next_specialist_key = None
                self.blocked_specialist_entered.set()
                await self.release_blocked_specialist.wait()
        marker = f"specialist:{key}" if phase == "specialist" else phase
        if marker == self.crash_at and not self.crashed:
            self.crashed = True
            raise RuntimeError(f"Synthetic worker crash at {marker}.")
        analysis_context = (context.input_payload or {}).get("authorizedContext", {})
        assert isinstance(analysis_context, dict)
        historical_as_of = analysis_context.get("analysisHistoricalAsOf")
        basis_date = historical_as_of or analysis_context.get("analysisEffectiveDate")
        assert isinstance(basis_date, str)
        common_product = _common_product(
            effective_date=basis_date,
            historical_analysis=historical_as_of is not None,
        )
        if key == "legal_butler" and phase == "planning":
            output = ButlerPlanningOutput.model_validate(
                {
                    "phase": "planning",
                    "objective": run.objective,
                    "matterId": str(run.matter_id),
                    "workItemId": None,
                    "taskTypes": ["contract", "ip"],
                    "steps": [
                        {
                            "stepId": "contract",
                            "agentKey": "contract_review",
                            "objective": "定位合同条款风险",
                            "dependsOn": [],
                            "contextRequirements": ["contract_segments"],
                        },
                        {
                            "stepId": "ip",
                            "agentKey": "ip_copyright",
                            "objective": "核验图片授权链",
                            "dependsOn": [],
                            "contextRequirements": ["license_documents"],
                        },
                        {
                            "stepId": "summary",
                            "agentKey": "legal_consultation",
                            "objective": "仅根据合同审查结果形成咨询意见",
                            "dependsOn": ["contract"],
                            "contextRequirements": ["contract_result"],
                        },
                    ],
                    "missingInformation": (
                        ["请补充不影响现有材料分析的登记信息"]
                        if self.planning_requires_user_input
                        else []
                    ),
                    "requiresUserInput": self.planning_requires_user_input,
                    "synthesisStrategy": "并行分析后显式处理冲突。",
                }
            )
        elif key == "contract_review":
            output = ContractReviewProduct.model_validate(
                common_product
                | {
                    "contractSummary": "虚构合作合同",
                    "parties": ["甲方", "乙方"],
                    "commercialTerms": ["按月结算"],
                    "clauseRisks": [
                        {
                            "clauseLocator": "第8.2条",
                            "clauseText": "乙方承担全部责任",
                            "risk": "责任无上限",
                            "severity": "high",
                            "sourceRefs": ["ctx:snapshot:fixture"],
                        }
                    ],
                    "missingTerms": ["责任上限"],
                    "proposedChanges": ["增加责任上限"],
                    "fallbackPositions": ["排除间接损失"],
                    "negotiationPoints": ["责任上限"],
                }
            )
        elif key == "ip_copyright":
            output = IpCopyrightProduct.model_validate(
                common_product
                | {
                    "rightsObjects": [
                        {
                            "category": "image_portrait",
                            "description": "合作图片",
                            "sourceRefs": ["ctx:snapshot:fixture"],
                        }
                    ],
                    "rightsBasis": ["图片作品及肖像权益"],
                    "authorizationChain": [
                        {
                            "grantor": "权利人",
                            "grantee": "公司",
                            "scope": "待核实",
                            "evidenceRefs": ["ctx:snapshot:fixture"],
                            "gap": "缺少书面授权",
                        }
                    ],
                    "infringementElements": ["受保护客体", "未经许可使用"],
                    "defenses": ["有效许可"],
                    "evidence": [
                        {
                            "description": "合同图片条款",
                            "sourceRefs": ["ctx:snapshot:fixture"],
                            "supports": ["存在图片使用安排"],
                        }
                    ],
                    "evidenceGaps": ["权利人授权文件"],
                }
            )
        elif key == "legal_consultation":
            output = LegalConsultationProduct.model_validate(
                common_product
                | {
                    "questions": ["是否可推进"],
                    "legalRelationships": ["合同关系"],
                }
            )
        else:
            upstream = (context.input_payload or {}).get("upstreamOutputs", {})
            output = ButlerSynthesisOutput.model_validate(
                {
                    "phase": "synthesis",
                    "matterAssessment": "合同责任及图片授权均需处理后再推进。",
                    "coreFacts": [
                        {
                            "fact": "存在合同及图片使用安排",
                            "sourceRefs": [SOURCE_REF],
                        }
                    ],
                    "keyLegalIssues": [
                        {"issue": "责任上限", "sourceRefs": [SOURCE_REF]},
                        {"issue": "授权链", "sourceRefs": [SOURCE_REF]},
                    ],
                    "integratedRisks": [
                        {
                            "description": "责任和授权风险",
                            "severity": "high",
                            "likelihood": "possible",
                            "supportRefs": [SOURCE_REF],
                        }
                    ],
                    "recommendedStrategy": [
                        {
                            "action": "先补授权，再修改责任条款",
                            "rationale": "控制授权和责任风险",
                            "supportRefs": [SOURCE_REF],
                        }
                    ],
                    "nextActions": [
                        {"action": "取得授权文件", "supportRefs": [SOURCE_REF]},
                        {"action": "发出合同修订意见", "supportRefs": [SOURCE_REF]},
                    ],
                    "missingInformation": [],
                    "draftResponse": "建议补充授权链，并按意见修改第8.2条。",
                    "participatingAgents": sorted(
                        {
                            value.get("agentKey", step_id)
                            if isinstance(value, dict)
                            else step_id
                            for step_id, value in upstream.items()
                        }
                    ),
                    "citations": [
                        {
                            "sourceRef": SOURCE_REF,
                            "title": "非敏感法律依据 fixture",
                            "sourceType": "knowledge_document",
                            "locator": "第一条",
                            "contentHash": "b" * 64,
                            "internalPrecedent": False,
                        }
                    ],
                    "conflicts": [],
                    "confidence": 0.8,
                }
            )
        return AgentExecutionResult(
            output=output,
            raw_stdout="fake-runtime",
            raw_stderr="",
            output_path=Path("/isolated/fake-output.json"),
            runtime_version="fake-legal-v1",
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_agent_orchestration_persists_lineage_draft_and_review() -> None:
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
    matter = LegalMatter.create(
        title="非敏感合作合同与图片授权",
        primary_category=MatterCategory.CONTRACT,
        secondary_categories=[MatterCategory.INTELLECTUAL_PROPERTY],
        owner_id="user:fixture",
        legal_risk=LegalRisk.HIGH,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.INTERNAL,
        requester_ids=[],
        summary="仅用于 E2E fixture。",
        objective="验证两阶段管家。",
    )
    snapshot = ContextSnapshot(
        id=uuid4(),
        source_type="matter_fixture",
        source_id=uuid4().hex,
        source_ids=[],
        message_ids=[],
        file_ids=[],
        relevant_matter_ids=[str(matter.id)],
        participant_ids=[],
        permission_snapshot={},
        generated_at=datetime.now(UTC),
        content_hash="a" * 64,
        content={"fixture": "合同及图片授权"},
    )
    runtime = FakeLegalRuntime()
    trigger = LegalAgentTrigger(
        matter_id=matter.id,
        context_snapshot_id=snapshot.id,
        objective="并行审查合作合同及图片授权风险",
        actor_id="user:fixture",
        correlation_id=f"corr-{uuid4().hex}",
        idempotency_key=f"manual-{uuid4().hex}",
    )
    try:
        async with factory() as uow:
            await uow.matters.add(matter)
            await uow.context_snapshots.add(snapshot)
            await uow.commit()
        async with session_factory() as session:
            communications_before = await session.scalar(
                select(func.count(CommunicationModel.id))
            )

        analysis_clock = [date(2026, 8, 10)]
        orchestrator = LegalAgentOrchestrator(
            factory,
            runtime,
            FakeContextBuilder(),
            runs_root="/isolated/legal-agent-runs",
            analysis_date_provider=lambda: analysis_clock[0],
        )
        result = await orchestrator.execute(trigger)

        assert result.status == AgentExecutionPlanStatus.COMPLETED
        assert result.artifact_id is not None
        assert result.review_package_id is not None
        async with factory() as uow:
            plan = await uow.agent_execution_plans.get(result.plan_id)
            runs = list(await uow.agent_runs.list_by_plan(result.plan_id))
            children = list(await uow.agent_runs.list_children(result.planning_run_id))
            attempts_by_run = {
                run.id: list(await uow.agent_run_attempts.list_by_run(run.id))
                for run in runs
            }
            status_events_by_run = {
                run.id: list(await uow.agent_runs.list_status_events(run.id))
                for run in runs
            }
        assert plan is not None
        assert plan.analysis_effective_date == date(2026, 8, 10)
        assert [step.status.value for step in plan.steps] == [
            "completed",
            "completed",
            "completed",
        ]
        assert set(runtime.upstream_by_key["legal_consultation"][0]) == {"contract"}
        assert runtime.upstream_by_key["contract_review"][0] == {}
        assert runtime.upstream_by_key["ip_copyright"][0] == {}
        assert [run.run_role for run in runs] == [
            AgentRunRole.BUTLER_PLANNING,
            AgentRunRole.SPECIALIST,
            AgentRunRole.SPECIALIST,
            AgentRunRole.SPECIALIST,
            AgentRunRole.BUTLER_SYNTHESIS,
        ]
        assert len(children) == 4
        assert all(
            [attempt.status.value for attempt in attempts_by_run[run.id]] == [
                "completed"
            ]
            for run in runs
        )
        assert all(
            [event.to_status.value for event in status_events_by_run[run.id]]
            == ["queued", "preparing", "running", "validating", "completed"]
            for run in runs
        )
        async with session_factory() as session:
            artifact = await session.get(DraftArtifactModel, result.artifact_id)
            review = await session.get(ReviewPackageModel, result.review_package_id)
            communications_after = await session.scalar(
                select(func.count(CommunicationModel.id))
            )
        assert artifact is not None
        assert artifact.structured_payload["participatingAgents"]
        assert review is not None
        assert review.status == ReviewPackageStatus.PENDING_REVIEW
        assert review.citations[0]["sourceRef"] == SOURCE_REF
        assert communications_after == communications_before

        replay = await orchestrator.execute(trigger)
        assert replay.idempotent_replay is True
        assert replay.plan_id == result.plan_id

        analysis_clock[0] = date(2026, 8, 11)
        runtime.block_next_specialist_key = "contract_review"
        first_rerun = asyncio.create_task(
            orchestrator.rerun_step(
                plan_id=result.plan_id,
                step_id="contract",
                actor_id="user:fixture",
                correlation_id=f"rerun-{uuid4().hex}",
            )
        )
        await asyncio.wait_for(runtime.blocked_specialist_entered.wait(), timeout=5)
        with pytest.raises(InvalidStateTransitionError, match="already active"):
            await orchestrator.rerun_step(
                plan_id=result.plan_id,
                step_id="contract",
                actor_id="user:fixture",
                correlation_id=f"overlapping-rerun-{uuid4().hex}",
            )
        runtime.release_blocked_specialist.set()
        rerun = await first_rerun
        assert rerun.status == AgentExecutionPlanStatus.PARTIAL
        async with factory() as uow:
            rerun_plan = await uow.agent_execution_plans.get(result.plan_id)
            rerun_runs = list(await uow.agent_runs.list_by_plan(result.plan_id))
        assert rerun_plan is not None
        contract_step = next(
            step for step in rerun_plan.steps if step.step_id == "contract"
        )
        assert contract_step.attempt_count == 2
        assert contract_step.latest_valid_run_id == contract_step.latest_run_id
        latest_contract_run = next(
            run for run in rerun_runs if run.id == contract_step.latest_run_id
        )
        assert latest_contract_run.retry_of_run_id is not None
        assert latest_contract_run.input_payload["authorizedContext"][
            "analysisEffectiveDate"
        ] == "2026-08-10"
        stale_summary = next(
            step for step in rerun_plan.steps if step.step_id == "summary"
        )
        assert stale_summary.status.value == "skipped"
        assert stale_summary.failure_code == "STALE_DEPENDENCY_RUN"
        latest_synthesis = next(
            run
            for run in reversed(rerun_runs)
            if run.run_role == AgentRunRole.BUTLER_SYNTHESIS
        )
        stale_summary_input = latest_synthesis.input_payload["upstreamOutputs"][
            "summary"
        ]
        assert stale_summary_input["status"] == "skipped"
        assert "executiveSummary" not in stale_summary_input
        assert STALE_SUMMARY_SOURCE_REF not in latest_synthesis.input_payload[
            "authorizedSourceRefs"
        ]
        assert latest_synthesis.input_payload["authorizedContext"][
            "analysisEffectiveDate"
        ] == "2026-08-10"

        rerun_summary = await orchestrator.rerun_step(
            plan_id=result.plan_id,
            step_id="summary",
            actor_id="user:fixture",
            correlation_id=f"rerun-summary-{uuid4().hex}",
        )
        assert rerun_summary.status == AgentExecutionPlanStatus.COMPLETED
        async with factory() as uow:
            final_plan = await uow.agent_execution_plans.get(result.plan_id)
            final_runs = list(await uow.agent_runs.list_by_plan(result.plan_id))
        assert final_plan is not None
        final_contract = next(
            step for step in final_plan.steps if step.step_id == "contract"
        )
        final_summary = next(
            step for step in final_plan.steps if step.step_id == "summary"
        )
        assert final_summary.attempt_count == 2
        latest_summary_run = next(
            run for run in final_runs if run.id == final_summary.latest_valid_run_id
        )
        assert latest_summary_run.dependency_run_ids == [
            final_contract.latest_valid_run_id
        ]
        assert set(runtime.upstream_by_key["legal_consultation"][-1]) == {"contract"}
        assert len(
            [run for run in final_runs if run.run_role == AgentRunRole.BUTLER_SYNTHESIS]
        ) == 3
    finally:
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_planning_information_gap_still_produces_grounded_review_package() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"])
    factory = SqlAlchemyUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    matter = LegalMatter.create(
        title="Planning information gap fixture",
        primary_category=MatterCategory.CONTRACT,
        secondary_categories=[MatterCategory.INTELLECTUAL_PROPERTY],
        owner_id="user:fixture",
        legal_risk=LegalRisk.MEDIUM,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.INTERNAL,
        requester_ids=[],
        summary="Synthetic partial analysis fixture.",
        objective="Use available evidence while retaining planning information gaps.",
    )
    snapshot = ContextSnapshot(
        id=uuid4(),
        source_type="planning_information_gap_fixture",
        source_id=uuid4().hex,
        source_ids=[],
        message_ids=[],
        file_ids=[],
        relevant_matter_ids=[str(matter.id)],
        participant_ids=[],
        permission_snapshot={},
        generated_at=datetime.now(UTC),
        content_hash=uuid4().hex * 2,
        content={"fixture": "planning information gap"},
    )
    runtime = FakeLegalRuntime(planning_requires_user_input=True)
    orchestrator = LegalAgentOrchestrator(
        factory,
        runtime,
        FakeContextBuilder(),
        runs_root="/isolated/legal-agent-runs",
    )
    try:
        async with factory() as uow:
            await uow.matters.add(matter)
            await uow.context_snapshots.add(snapshot)
            await uow.commit()

        result = await orchestrator.execute(
            LegalAgentTrigger(
                matter_id=matter.id,
                context_snapshot_id=snapshot.id,
                objective=matter.objective,
                actor_id="user:fixture",
                correlation_id=f"planning-gap-{uuid4().hex}",
                idempotency_key=f"planning-gap-{uuid4().hex}",
            )
        )

        assert result.status == AgentExecutionPlanStatus.NEEDS_INFORMATION
        assert result.artifact_id is not None
        assert result.review_package_id is not None
        assert [phase for _, phase in runtime.calls] == [
            "planning",
            "specialist",
            "specialist",
            "specialist",
            "synthesis",
        ]
        async with factory() as uow:
            review = await uow.review_packages.get(result.review_package_id)
        assert review is not None
        assert review.unconfirmed_facts == [
            {"missingInformation": "请补充不影响现有材料分析的登记信息"}
        ]
    finally:
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "crash_at",
    ["planning", "specialist:contract_review", "synthesis"],
)
async def test_legal_agent_crash_recovery_resumes_only_incomplete_phase(
    crash_at: str,
) -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.domain.enums import AgentAttemptStatus
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"])
    factory = SqlAlchemyUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    matter = LegalMatter.create(
        title=f"Crash recovery fixture: {crash_at}",
        primary_category=MatterCategory.CONTRACT,
        secondary_categories=[MatterCategory.INTELLECTUAL_PROPERTY],
        owner_id="user:fixture",
        legal_risk=LegalRisk.HIGH,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.INTERNAL,
        requester_ids=[],
        summary="Synthetic crash recovery only.",
        objective="Verify fenced recovery.",
    )
    snapshot = ContextSnapshot(
        id=uuid4(),
        source_type="crash_recovery_fixture",
        source_id=uuid4().hex,
        source_ids=[],
        message_ids=[],
        file_ids=[],
        relevant_matter_ids=[str(matter.id)],
        participant_ids=[],
        permission_snapshot={},
        generated_at=datetime.now(UTC),
        content_hash=uuid4().hex * 2,
        included_segments=[
            {
                "attachmentId": str(uuid4()),
                "fileName": "非敏感恢复测试.txt",
                "paragraphNumber": 1,
                "contentHash": "d" * 64,
            }
        ],
        content={"fixture": "crash recovery"},
    )
    runtime = FakeLegalRuntime(crash_at=crash_at)
    orchestrator = LegalAgentOrchestrator(
        factory,
        runtime,
        FakeContextBuilder(),
        runs_root="/isolated/legal-agent-runs",
        lease_seconds=1,
        worker_id="crash-fixture-worker",
        analysis_date_provider=lambda: date(2026, 8, 10),
    )
    trigger = LegalAgentTrigger(
        matter_id=matter.id,
        context_snapshot_id=snapshot.id,
        objective="Verify planning, specialist, and synthesis crash recovery.",
        actor_id="user:fixture",
        correlation_id=f"crash-{uuid4().hex}",
        idempotency_key=f"crash-{uuid4().hex}",
        historical_as_of=date(2024, 1, 15),
    )
    try:
        async with factory() as uow:
            await uow.matters.add(matter)
            await uow.context_snapshots.add(snapshot)
            await uow.commit()

        with pytest.raises((RuntimeError, BaseExceptionGroup)):
            await orchestrator.execute(trigger)

        async with factory() as uow:
            plans = list(await uow.agent_execution_plans.list_by_matter(matter.id))
        assert len(plans) == 1
        plan = plans[0]
        completed_before = {
            step.step_id: step.latest_valid_run_id
            for step in plan.steps
            if step.status.value in {"completed", "needs_information"}
        }

        recovery_result = await AnalysisRecoveryService(
            factory,
            stale_after_seconds=1,
            now=lambda: datetime.now(UTC) + timedelta(minutes=5),
        ).recover()
        assert recovery_result.legal_runs_requeued == 1

        recovered = await orchestrator.recover(
            plan_id=plan.id,
            correlation_id=f"recovered-{uuid4().hex}",
        )

        assert recovered.status == AgentExecutionPlanStatus.COMPLETED
        async with factory() as uow:
            final_plan = await uow.agent_execution_plans.get(plan.id)
            final_runs = list(await uow.agent_runs.list_by_plan(plan.id))
        assert final_plan is not None
        assert final_plan.analysis_effective_date == date(2026, 8, 10)
        assert final_plan.historical_as_of == date(2024, 1, 15)
        assert all(step.status.value == "completed" for step in final_plan.steps)
        assert {
            step.step_id: step.latest_valid_run_id
            for step in final_plan.steps
            if step.step_id in completed_before
        } == completed_before
        recovered_run = next(value for value in final_runs if value.attempt_number == 2)
        assert recovered_run.input_payload["authorizedContext"][
            "analysisEffectiveDate"
        ] == "2026-08-10"
        assert recovered_run.input_payload["authorizedContext"][
            "analysisHistoricalAsOf"
        ] == "2024-01-15"
        async with factory() as uow:
            attempts = list(
                await uow.agent_run_attempts.list_by_run(recovered_run.id)
            )
        assert [value.status for value in attempts] == [
            AgentAttemptStatus.EXPIRED,
            AgentAttemptStatus.COMPLETED,
        ]
        if crash_at == "synthesis":
            assert "ctx:segment:" + "d" * 64 in recovered_run.input_payload[
                "authorizedSourceRefs"
            ]
    finally:
        await engine.dispose()
