# ruff: noqa: RUF001

from __future__ import annotations

from datetime import date
from pathlib import Path

from legal_workbench.agents.legal_butler import (
    ButlerPlanningOutput,
    ButlerSynthesisOutput,
)
from legal_workbench.agents.legal_contracts import LegalConsultationProduct
from legal_workbench.application.evaluations import load_evaluation_fixture
from legal_workbench.application.legal_evaluations import (
    score_butler_outputs,
    score_legal_work_product,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "evaluations"
LEGAL_SUITES = {
    "legal_consultation",
    "contract_review",
    "dispute_complaint",
    "ip_copyright",
    "labor_employment",
    "legal_butler",
}


def test_each_legal_agent_has_an_independent_non_sensitive_versioned_fixture() -> None:
    suites = [
        load_evaluation_fixture(FIXTURE_ROOT / f"{agent_key}_v1.json")
        for agent_key in sorted(LEGAL_SUITES)
    ]

    assert {suite.agent_key for suite in suites} == LEGAL_SUITES
    assert all(suite.version == 1 for suite in suites)
    assert all(suite.data_classification == "synthetic_non_sensitive" for suite in suites)
    assert all(len(suite.cases) >= 1 for suite in suites)


def test_specialist_quality_scores_cover_grounding_hallucination_and_usefulness() -> None:
    product = LegalConsultationProduct.model_validate(
        {
            "executiveSummary": "应在明确投放渠道和适用规则后上线。",
            "facts": [
                {
                    "fact": "虚构业务拟上线促销文案。",
                    "sourceRefs": ["ctx:snapshot:fixture"],
                }
            ],
            "issues": ["促销文案合规问题"],
            "legalBasis": [
                {
                        "proposition": "应核验适用规则。",
                        "sourceRefs": ["knowledge:chunk:fixture"],
                        "authorityRole": "formal_legal_basis",
                        "jurisdiction": "CN",
                        "effectiveDate": date(2026, 1, 1).isoformat(),
                        "historicalAnalysis": False,
                }
            ],
            "analysis": [
                {
                    "conclusion": "当前投放渠道不明。",
                    "supportRefs": ["ctx:snapshot:fixture"],
                }
            ],
            "risks": [
                {
                    "description": "渠道规则未核验",
                    "severity": "medium",
                    "likelihood": "possible",
                }
            ],
            "recommendedActions": ["补充投放渠道"],
            "missingInformation": ["投放渠道"],
            "assumptions": [],
            "draftResponse": "请补充具体投放渠道，我们将据此核验适用规则。",
            "confidence": 0.8,
            "citations": [
                {
                    "sourceRef": "knowledge:chunk:fixture",
                    "title": "非敏感规则 fixture",
                    "sourceType": "knowledge_document",
                    "internalPrecedent": False,
                }
            ],
            "questions": ["能否上线"],
            "legalRelationships": ["公司与消费者之间的交易关系"],
        }
    )

    scores = score_legal_work_product(
        product,
        authorized_source_refs=frozenset(
            {"ctx:snapshot:fixture", "knowledge:chunk:fixture"}
        ),
        expected_issue_terms=("合规",),
        expected_missing_information=("投放渠道",),
    ).to_dict()

    assert set(scores) == {
        "schema_validity",
        "fact_grounding",
        "issue_coverage",
        "legal_basis_grounding",
        "citation_fidelity",
        "hallucination",
        "risk_identification",
        "actionability",
        "missing_information_detection",
        "draft_usefulness",
    }
    assert all(score == 1.0 for score in scores.values())


def test_butler_quality_scores_route_only_required_parallel_specialists() -> None:
    planning = ButlerPlanningOutput.model_validate(
        {
            "phase": "planning",
            "objective": "合同及图片授权分析",
            "matterId": None,
            "workItemId": None,
            "taskTypes": ["contract", "ip"],
            "steps": [
                {
                    "stepId": "contract",
                    "agentKey": "contract_review",
                    "objective": "定位合同风险",
                    "dependsOn": [],
                    "contextRequirements": ["contract"],
                },
                {
                    "stepId": "ip",
                    "agentKey": "ip_copyright",
                    "objective": "核验授权链",
                    "dependsOn": [],
                    "contextRequirements": ["license"],
                },
            ],
            "missingInformation": [],
            "requiresUserInput": False,
            "synthesisStrategy": "并行后综合。",
        }
    )
    synthesis = ButlerSynthesisOutput.model_validate(
        {
            "phase": "synthesis",
            "matterAssessment": "需修改合同并补授权。",
            "coreFacts": [
                {"fact": "存在合同及图片使用安排", "sourceRefs": ["ctx:fixture"]}
            ],
            "keyLegalIssues": [
                {"issue": "责任条款", "sourceRefs": ["ctx:fixture"]},
                {"issue": "图片授权", "sourceRefs": ["ctx:fixture"]},
            ],
            "integratedRisks": [],
            "recommendedStrategy": [
                {
                    "action": "同步推进修改和补件",
                    "rationale": "两项风险并行",
                    "supportRefs": ["ctx:fixture"],
                }
            ],
            "nextActions": [
                {"action": "修改合同", "supportRefs": ["ctx:fixture"]},
                {"action": "补授权", "supportRefs": ["ctx:fixture"]},
            ],
            "missingInformation": [],
            "draftResponse": "请按清单补充资料并确认修改。",
            "participatingAgents": ["contract_review", "ip_copyright"],
            "citations": [],
            "conflicts": [],
            "confidence": 0.8,
        }
    )

    scores = score_butler_outputs(
        planning,
        synthesis,
        required_specialists=frozenset({"contract_review", "ip_copyright"}),
    ).to_dict()

    assert all(score == 1.0 for score in scores.values())
