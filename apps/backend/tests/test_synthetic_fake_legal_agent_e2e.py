# ruff: noqa: RUF001

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from legal_workbench.agents.contracts import LegalAgentContractRegistry
from legal_workbench.agents.legal_butler import (
    ButlerPlanningOutput,
    ButlerSynthesisOutput,
)
from legal_workbench.agents.legal_contracts import ContractReviewProduct
from legal_workbench.agents.message_judgement import MessageJudgementResult
from legal_workbench.agents.runtime import AgentExecutionContext, AgentExecutionResult
from legal_workbench.application.commands import (
    ConfirmCandidateCreateMatterCommand,
    InitialWorkItemInput,
)
from legal_workbench.application.context_snapshots import ContextSnapshotBuilder
from legal_workbench.application.handlers import ConfirmCandidateCreateMatterHandler
from legal_workbench.application.knowledge import KnowledgeRetrievalService
from legal_workbench.application.legal_agent_orchestrator import (
    LegalAgentOrchestrator,
    LegalAgentTrigger,
)
from legal_workbench.application.legal_context import LegalContextBuilder
from legal_workbench.application.message_analysis import (
    AnalyseFeishuMessageCommand,
    AnalyseFeishuMessageHandler,
)
from legal_workbench.domain.entities import (
    FeishuMessage,
    FeishuRawEvent,
    KnowledgeChunk,
    KnowledgeDocument,
)
from legal_workbench.domain.enums import (
    AgentExecutionPlanStatus,
    AgentRunRole,
    AuthorityRole,
    AuthorityStatus,
    AuthorityType,
    BusinessImpact,
    Confidentiality,
    FeishuEventStatus,
    FeishuMessageStatus,
    KnowledgeMetadataStatus,
    LegalRisk,
    MatterCategory,
    Priority,
    PrioritySource,
    ReviewPackageStatus,
)


class SyntheticFakeMessageRuntime:
    def __init__(self, source_message_id: str) -> None:
        self._source_message_id = source_message_id

    async def execute(
        self,
        definition: Any,
        run: Any,
        context: AgentExecutionContext,
    ) -> AgentExecutionResult:
        del definition, context
        return AgentExecutionResult(
            output=MessageJudgementResult.model_validate(
                {
                    "legalRelevance": "relevant",
                    "messageRole": "new_request",
                    "actionability": "create_candidate",
                    "suggestedTitle": "审核非敏感 synthetic 合作协议",
                    "categoryCandidates": [
                        {
                            "category": "contract",
                            "confidence": 0.96,
                            "reason": "消息明确请求合同审查",
                        }
                    ],
                    "deadlineCandidates": [],
                    "confirmedFacts": [
                        {
                            "statement": "业务请求审查 synthetic 合作协议",
                            "sourceMessageId": self._source_message_id,
                        }
                    ],
                    "inferredFacts": [],
                    "missingInformation": [],
                    "reasons": ["存在明确法务行动要求"],
                    "confidence": 0.96,
                }
            ),
            raw_stdout="synthetic-fake-message-runtime",
            raw_stderr="",
            output_path=Path(run.working_directory) / "output.json",
            runtime_version="synthetic-fake-message-v1",
        )


class SyntheticFakeLegalRuntime:
    """Fake Codex only; contracts, authorization and persistence remain production code."""

    def __init__(self) -> None:
        self._contracts = LegalAgentContractRegistry()

    async def execute(
        self,
        definition: Any,
        run: Any,
        context: AgentExecutionContext,
    ) -> AgentExecutionResult:
        assert context.heartbeat is not None
        await context.heartbeat()
        phase = str((context.input_payload or {}).get("phase"))
        if phase == "planning":
            output = ButlerPlanningOutput.model_validate(
                {
                    "phase": "planning",
                    "objective": run.objective,
                    "matterId": str(run.matter_id),
                    "workItemId": str(run.work_item_id),
                    "taskTypes": ["contract"],
                    "steps": [
                        {
                            "stepId": "contract",
                            "agentKey": "contract_review",
                            "objective": run.objective,
                            "dependsOn": [],
                            "contextRequirements": ["authorized_message", "law"],
                        }
                    ],
                    "missingInformation": [],
                    "requiresUserInput": False,
                    "synthesisStrategy": "仅整合已授权的当前 specialist 结果。",
                }
            )
        else:
            analysis_context = (context.input_payload or {}).get(
                "authorizedContext", {}
            )
            assert isinstance(analysis_context, dict)
            effective_date = str(analysis_context["analysisEffectiveDate"])
            if phase == "specialist":
                retrieval_results = analysis_context.get("retrievalResults", [])
                assert isinstance(retrieval_results, list) and retrieval_results
                first_result = retrieval_results[0]
                assert isinstance(first_result, dict)
                knowledge_ref = str(first_result["sourceRef"])
                raw_output: dict[str, object] = {
                    "executiveSummary": "应补充责任上限后进入人工复核。",
                    "facts": [
                        {
                            "fact": "synthetic 合作协议包含无上限责任安排。",
                            "sourceRefs": [knowledge_ref],
                        }
                    ],
                    "issues": ["责任范围与责任上限"],
                    "legalBasis": [
                        {
                            "proposition": "合同约定应遵循有效法律规则。",
                            "sourceRefs": [knowledge_ref],
                            "authorityRole": "formal_legal_basis",
                            "jurisdiction": "CN",
                            "effectiveDate": effective_date,
                            "historicalAnalysis": False,
                        }
                    ],
                    "analysis": [
                        {
                            "conclusion": "无上限责任条款需要修改。",
                            "supportRefs": [knowledge_ref],
                        }
                    ],
                    "risks": [
                        {
                            "description": "责任范围失衡",
                            "severity": "high",
                            "likelihood": "possible",
                        }
                    ],
                    "recommendedActions": ["增加明确责任上限"],
                    "missingInformation": [],
                    "assumptions": [],
                    "draftResponse": "建议修改责任条款并提交法务人工复核。",
                    "confidence": 0.82,
                    "citations": [
                        {
                            "sourceRef": knowledge_ref,
                            "title": "模型伪造标题，必须由服务端覆盖",
                            "sourceType": "historical_matter",
                            "locator": "模型伪造定位",
                            "contentHash": "0" * 64,
                            "internalPrecedent": True,
                        }
                    ],
                    "contractSummary": "非敏感 synthetic 合作协议",
                    "parties": ["甲方", "乙方"],
                    "commercialTerms": ["按约履行"],
                    "clauseRisks": [
                        {
                            "clauseLocator": "synthetic 第8.2条",
                            "clauseText": "乙方承担全部损失",
                            "risk": "缺少责任上限",
                            "severity": "high",
                            "sourceRefs": [knowledge_ref],
                        }
                    ],
                    "missingTerms": ["责任上限"],
                    "proposedChanges": ["增加责任上限"],
                    "fallbackPositions": ["排除间接损失"],
                    "negotiationPoints": ["责任上限"],
                }
                output = ContractReviewProduct.model_validate(raw_output)
            else:
                upstream_outputs = (context.input_payload or {}).get(
                    "upstreamOutputs", {}
                )
                assert isinstance(upstream_outputs, dict)
                contract_output = upstream_outputs["contract"]
                assert isinstance(contract_output, dict)
                citations = contract_output["citations"]
                assert isinstance(citations, list) and citations
                knowledge_ref = str(citations[0]["sourceRef"])
                raw_synthesis: dict[str, object] = {
                    "phase": "synthesis",
                    "matterAssessment": "责任上限需修改后再推进。",
                    "coreFacts": [
                        {
                            "fact": "存在无上限责任风险",
                            "sourceRefs": [knowledge_ref],
                        }
                    ],
                    "keyLegalIssues": [
                        {"issue": "责任上限", "sourceRefs": [knowledge_ref]}
                    ],
                    "integratedRisks": [
                        {
                            "description": "责任范围失衡",
                            "severity": "high",
                            "likelihood": "possible",
                            "supportRefs": [knowledge_ref],
                        }
                    ],
                    "recommendedStrategy": [
                        {
                            "action": "修改责任条款",
                            "rationale": "控制责任风险",
                            "supportRefs": [knowledge_ref],
                        }
                    ],
                    "nextActions": [
                        {
                            "action": "提交法务人工复核",
                            "supportRefs": [knowledge_ref],
                        }
                    ],
                    "missingInformation": [],
                    "draftResponse": "建议修改责任条款，人工批准前不得发送。",
                    "participatingAgents": ["contract_review"],
                    "citations": [
                        {
                            "sourceRef": knowledge_ref,
                            "title": "模型伪造标题，必须由服务端覆盖",
                            "sourceType": "historical_matter",
                            "locator": "模型伪造定位",
                            "contentHash": "0" * 64,
                            "internalPrecedent": False,
                        }
                    ],
                    "conflicts": [],
                    "confidence": 0.8,
                }
                output = self._contracts.validate_output(
                    definition, raw_synthesis, context
                )
                assert isinstance(output, ButlerSynthesisOutput)
        return AgentExecutionResult(
            output=output,
            raw_stdout="synthetic-fake-legal-runtime",
            raw_stderr="",
            output_path=Path(run.working_directory) / "output.json",
            runtime_version="synthetic-fake-legal-v1",
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_synthetic_fake_runtime_message_to_review_package_e2e(tmp_path: Path) -> None:
    """This is explicitly Fake Runtime E2E, not Real Codex evidence."""

    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.models import (
        CommunicationModel,
        DraftArtifactModel,
        KnowledgeRetrievalLogModel,
        OutboxEventModel,
        ReviewPackageModel,
    )
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    factory = SqlAlchemyUnitOfWorkFactory(session_factory)
    suffix = uuid4().hex
    marker = f"syntheticphase2{suffix}"
    external_message_id = f"om_synthetic_{suffix}"
    event = FeishuRawEvent(
        id=uuid4(),
        event_id=f"evt-{suffix}",
        event_type="im.message.receive_v1",
        tenant_key="synthetic-tenant",
        app_id="synthetic-app",
        schema_version="2.0",
        raw_payload={"synthetic": True},
        payload_hash=sha256(f"event:{suffix}".encode()).hexdigest(),
        status=FeishuEventStatus.RECEIVED,
    )
    message = FeishuMessage(
        id=uuid4(),
        event_id=event.id,
        tenant_key=event.tenant_key,
        message_id=external_message_id,
        chat_id=f"synthetic-chat-{suffix}",
        thread_id=None,
        root_id=None,
        parent_id=None,
        sender_id="synthetic-business-user",
        sender_type="user",
        message_type="text",
        content={"text": f"请审查 {marker} 合作协议的责任上限。"},
        mentions=[],
        create_time=datetime.now(UTC),
        update_time=None,
        raw_message={"synthetic": True, "message_id": external_message_id},
        status=FeishuMessageStatus.RECEIVED,
    )
    law_text = f"{marker} 非敏感测试法律规则：依法成立的合同对当事人具有约束力。"
    law = KnowledgeDocument(
        id=uuid4(),
        source_type="synthetic_fake_e2e_fixture",
        source_id=f"law:{suffix}",
        title="非敏感 Synthetic 合同法律规则",
        document_type="law",
        agent_types=["contract_review"],
        matter_types=["contract"],
        jurisdiction="CN",
        effective_from=date(2021, 1, 1),
        source_priority=100,
        internal_precedent=False,
        confidentiality="internal",
        approved_by="synthetic-fixture",
        authority_type=AuthorityType.LAW,
        authority_role=AuthorityRole.FORMAL_LEGAL_BASIS,
        authority_status=AuthorityStatus.EFFECTIVE,
        metadata_status=KnowledgeMetadataStatus.READY,
    )
    chunk = KnowledgeChunk(
        id=uuid4(),
        knowledge_document_id=law.id,
        sequence=1,
        locator="Synthetic 第一条",
        text=law_text,
        normalized_text=law_text.casefold(),
        text_hash=sha256(law_text.encode()).hexdigest(),
    )
    correlation_id = f"synthetic-fake-e2e:{suffix}"
    try:
        async with factory() as uow:
            await uow.feishu.add_event(event)
            await uow.feishu.add_message(message)
            await uow.knowledge.add_document(law)
            await uow.flush()
            await uow.knowledge.add_chunks([chunk])
            await uow.commit()

        triage = await AnalyseFeishuMessageHandler(
            factory,
            SyntheticFakeMessageRuntime(external_message_id),
            ContextSnapshotBuilder(factory, max_messages=10, max_text_characters=5000),
            runs_root=tmp_path / "message-runs",
            manual_review_threshold=0.75,
        ).execute(
            AnalyseFeishuMessageCommand(
                message_id=message.id,
                actor_id="synthetic-legal-user",
                actor_source="test",
                correlation_id=correlation_id,
            )
        )
        assert triage.candidate_id is not None
        async with factory() as uow:
            candidate = await uow.candidates.get(triage.candidate_id)
        assert candidate is not None

        matter_result = await ConfirmCandidateCreateMatterHandler(factory).execute(
            ConfirmCandidateCreateMatterCommand(
                candidate_id=candidate.id,
                candidate_version=candidate.version,
                actor_id="synthetic-legal-user",
                correlation_id=correlation_id,
                idempotency_key=f"confirm:{suffix}",
                title="非敏感 Synthetic 合作协议审查",
                primary_category=MatterCategory.CONTRACT,
                secondary_categories=[],
                owner_id="synthetic-legal-user",
                requester_ids=["synthetic-business-user"],
                legal_risk=LegalRisk.MEDIUM,
                business_impact=BusinessImpact.PROJECT,
                confidentiality=Confidentiality.INTERNAL,
                summary="仅使用非敏感 synthetic fixture。",
                objective=f"审查 {marker} 合作协议责任上限",
                initial_work_items=[
                    InitialWorkItemInput(
                        title="核查 synthetic 责任条款",
                        owner_id="synthetic-legal-user",
                        priority=Priority.HIGH,
                        priority_source=PrioritySource.LEGAL_CONFIRMED,
                        next_action="形成草稿并提交人工审核",
                    )
                ],
            )
        )
        async with session_factory() as session:
            butler_event = (
                await session.execute(
                    select(OutboxEventModel)
                    .where(
                        OutboxEventModel.event_type == "LegalButlerRequested",
                        OutboxEventModel.aggregate_id == matter_result.matter_id,
                    )
                    .order_by(OutboxEventModel.occurred_at.desc())
                )
            ).scalars().first()
            communications_before = int(
                await session.scalar(select(func.count(CommunicationModel.id))) or 0
            )
        assert butler_event is not None
        payload = butler_event.payload

        result = await LegalAgentOrchestrator(
            factory,
            SyntheticFakeLegalRuntime(),
            LegalContextBuilder(KnowledgeRetrievalService(factory)),
            runs_root=tmp_path / "legal-runs",
            analysis_date_provider=lambda: date(2026, 8, 10),
        ).execute(
            LegalAgentTrigger(
                matter_id=matter_result.matter_id,
                work_item_id=matter_result.work_item_ids[0],
                context_snapshot_id=candidate.context_snapshot_id,
                objective=str(payload["objective"]),
                actor_id=str(payload["actorId"]),
                correlation_id=correlation_id,
                idempotency_key=str(payload["idempotencyKey"]),
                jurisdiction=str(payload["jurisdiction"]),
            )
        )

        assert result.status == AgentExecutionPlanStatus.COMPLETED
        assert result.artifact_id is not None
        assert result.review_package_id is not None
        async with factory() as uow:
            plan = await uow.agent_execution_plans.get(result.plan_id)
            runs = list(await uow.agent_runs.list_by_plan(result.plan_id))
        assert plan is not None
        from legal_workbench.api.routes.agents import _plan_response

        response = await _plan_response(plan, factory)
        assert plan.analysis_effective_date == date(2026, 8, 10)
        assert plan.historical_as_of is None
        assert plan.steps[0].latest_run_id == plan.steps[0].latest_valid_run_id
        assert response.analysis_effective_date == date(2026, 8, 10)
        assert response.historical_as_of is None
        assert response.steps[0].latest_valid_run_id == plan.steps[0].latest_valid_run_id
        assert {run.run_role for run in runs} == {
            AgentRunRole.BUTLER_PLANNING,
            AgentRunRole.SPECIALIST,
            AgentRunRole.BUTLER_SYNTHESIS,
        }
        specialist_run = next(
            run for run in runs if run.run_role == AgentRunRole.SPECIALIST
        )
        assert specialist_run.dependency_run_ids == []
        assert specialist_run.output_payload is not None
        specialist_citation = specialist_run.output_payload["citations"][0]
        assert specialist_citation["title"] == law.title
        assert specialist_citation["locator"] == chunk.locator
        assert specialist_citation["contentHash"] == chunk.text_hash
        assert specialist_citation["internalPrecedent"] is False
        specialist_response = next(
            run for run in response.agent_runs if run.id == specialist_run.id
        )
        assert specialist_response.dependency_run_ids == []

        async with session_factory() as session:
            artifact = await session.get(DraftArtifactModel, result.artifact_id)
            review = await session.get(ReviewPackageModel, result.review_package_id)
            retrieval_count = int(
                await session.scalar(
                    select(func.count(KnowledgeRetrievalLogModel.id)).where(
                        KnowledgeRetrievalLogModel.correlation_id == correlation_id
                    )
                )
                or 0
            )
            communications_after = int(
                await session.scalar(select(func.count(CommunicationModel.id))) or 0
            )
        assert artifact is not None
        assert review is not None
        assert review.status == ReviewPackageStatus.PENDING_REVIEW
        assert retrieval_count == 1
        assert review.citations[0]["title"] == law.title
        assert review.citations[0]["locator"] == chunk.locator
        assert review.citations[0]["contentHash"] == chunk.text_hash
        assert review.citations[0]["authorityType"] == AuthorityType.LAW.value
        assert review.citations[0]["internalPrecedent"] is False
        assert communications_after == communications_before
    finally:
        await engine.dispose()
