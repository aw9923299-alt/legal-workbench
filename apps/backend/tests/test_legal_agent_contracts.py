# ruff: noqa: RUF001

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from legal_workbench.agents.contracts import LegalAgentContractRegistry
from legal_workbench.agents.definitions import build_legal_agent_definitions
from legal_workbench.agents.legal_butler import ButlerPlanningOutput
from legal_workbench.agents.legal_contracts import (
    ContractReviewProduct,
    LegalConsultationProduct,
    validate_legal_work_product_sources,
)
from legal_workbench.agents.professional import LEGAL_SPECIALIST_KEYS
from legal_workbench.agents.runtime import AgentExecutionContext
from legal_workbench.domain.entities import ContextSnapshot


def _grounded_envelope() -> dict[str, object]:
    return {
        "executiveSummary": "现有资料支持先补充书面授权，再决定是否上线。",
        "facts": [{"fact": "业务拟于官网使用合作方图片。", "sourceRefs": ["ctx:message:m-1"]}],
        "issues": ["图片使用是否已获得完整授权"],
        "legalBasis": [
            {
                "proposition": "使用他人作品通常需要核验许可范围。",
                "sourceRefs": ["knowledge:chunk:k-1"],
                "authorityRole": "formal_legal_basis",
                "jurisdiction": "CN",
                "effectiveDate": date(2021, 6, 1).isoformat(),
                "historicalAnalysis": False,
            }
        ],
        "analysis": [
            {
                "conclusion": "当前授权链证据不足。",
                "supportRefs": ["ctx:message:m-1", "knowledge:chunk:k-1"],
            }
        ],
        "risks": [
            {
                "description": "未经许可使用图片",
                "severity": "high",
                "likelihood": "possible",
            }
        ],
        "recommendedActions": ["取得权利人书面授权并留档"],
        "missingInformation": ["原始授权文件"],
        "assumptions": ["尚未收到其他授权材料"],
        "draftResponse": "请先补充图片权属及授权链文件。",
        "confidence": 0.72,
        "citations": [
            {
                "sourceRef": "knowledge:chunk:k-1",
                "title": "法规资料",
                "sourceType": "knowledge_document",
                "locator": "第1条",
                "internalPrecedent": False,
            }
        ],
    }


def test_all_registered_legal_agents_have_independent_strict_contracts() -> None:
    definitions = build_legal_agent_definitions()

    assert set(definitions) == {"legal_butler", *LEGAL_SPECIALIST_KEYS}
    assert all(item.version for item in definitions.values())
    assert all(item.allowed_tools == [] for item in definitions.values())
    assert all(item.requires_human_review for item in definitions.values())
    for item in definitions.values():
        variants = item.output_schema.get("oneOf")
        if isinstance(variants, list):
            assert all(variant.get("additionalProperties") is False for variant in variants)
        else:
            assert item.output_schema.get("additionalProperties") is False


def test_contract_review_requires_clause_locator_and_grounded_legal_basis() -> None:
    payload = _grounded_envelope() | {
        "contractSummary": "渠道合作合同",
        "parties": ["甲方", "乙方"],
        "commercialTerms": ["服务费按月结算"],
        "clauseRisks": [
            {
                "clauseLocator": "",
                "clauseText": "乙方承担全部责任",
                "risk": "责任范围无上限",
                "severity": "high",
                "sourceRefs": ["ctx:segment:s-1"],
            }
        ],
        "missingTerms": ["责任上限"],
        "proposedChanges": ["增加责任上限"],
        "fallbackPositions": ["至少排除间接损失"],
        "negotiationPoints": ["以年度服务费为责任上限"],
    }

    with pytest.raises(ValidationError):
        ContractReviewProduct.model_validate(payload)

    payload["clauseRisks"][0]["clauseLocator"] = "第8.2条"
    product = ContractReviewProduct.model_validate(payload)
    assert product.clause_risks[0].clause_locator == "第8.2条"

    payload["legalBasis"][0]["sourceRefs"] = []
    with pytest.raises(ValidationError):
        ContractReviewProduct.model_validate(payload)


def test_domain_specific_source_refs_are_authorized_and_precedent_is_not_legal_basis() -> None:
    payload = _grounded_envelope() | {
        "contractSummary": "渠道合作合同",
        "parties": ["甲方", "乙方"],
        "commercialTerms": [],
        "clauseRisks": [
            {
                "clauseLocator": "第8.2条",
                "clauseText": "乙方承担全部责任",
                "risk": "责任范围无上限",
                "severity": "high",
                "sourceRefs": ["ctx:segment:unauthorized"],
            }
        ],
        "missingTerms": [],
        "proposedChanges": [],
        "fallbackPositions": [],
        "negotiationPoints": [],
    }
    product = ContractReviewProduct.model_validate(payload)

    with pytest.raises(ValueError, match="Unauthorized"):
        validate_legal_work_product_sources(
            product,
            authorized_source_refs={"ctx:message:m-1", "knowledge:chunk:k-1"},
        )

    payload["clauseRisks"][0]["sourceRefs"] = ["ctx:message:m-1"]
    product = ContractReviewProduct.model_validate(payload)
    with pytest.raises(ValueError, match="formal legal basis"):
        validate_legal_work_product_sources(
            product,
            authorized_source_refs={"ctx:message:m-1", "knowledge:chunk:k-1"},
            internal_precedent_refs={"knowledge:chunk:k-1"},
        )


def test_consultation_keeps_assumptions_separate_from_grounded_facts() -> None:
    payload = _grounded_envelope() | {
        "questions": ["是否可以直接上线图片"],
        "legalRelationships": ["公司与图片权利人之间的许可关系"],
    }
    product = LegalConsultationProduct.model_validate(payload)

    assert product.facts[0].fact not in product.assumptions
    assert product.facts[0].source_refs == ["ctx:message:m-1"]

    payload["facts"][0]["sourceRefs"] = []
    with pytest.raises(ValidationError):
        LegalConsultationProduct.model_validate(payload)


def test_butler_planning_rejects_unknown_agent_cycle_and_unbounded_steps() -> None:
    base = {
        "phase": "planning",
        "objective": "审查合同及图片授权",
        "matterId": None,
        "workItemId": None,
        "taskTypes": ["contract", "ip"],
        "missingInformation": [],
        "requiresUserInput": False,
        "synthesisStrategy": "先审合同，再综合图片授权风险。",
    }
    steps = [
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
            "dependsOn": ["contract"],
            "contextRequirements": ["license_documents"],
        },
    ]
    output = ButlerPlanningOutput.model_validate(base | {"steps": steps})
    assert output.steps[1].depends_on == ["contract"]

    invalid = [dict(step) for step in steps]
    invalid[0]["agentKey"] = "legal_butler"
    with pytest.raises(ValidationError):
        ButlerPlanningOutput.model_validate(base | {"steps": invalid})

    cyclic = [dict(step) for step in steps]
    cyclic[0]["dependsOn"] = ["ip"]
    with pytest.raises(ValidationError):
        ButlerPlanningOutput.model_validate(base | {"steps": cyclic})

    with pytest.raises(ValidationError):
        ButlerPlanningOutput.model_validate(base | {"steps": steps * 3})


def test_butler_runtime_selects_one_phase_schema_without_root_one_of() -> None:
    definition = build_legal_agent_definitions()["legal_butler"]
    snapshot = ContextSnapshot(
        id=uuid4(),
        source_type="fixture",
        source_ids=["fixture"],
        message_ids=[],
        file_ids=[],
        relevant_matter_ids=[],
        participant_ids=[],
        permission_snapshot={},
        generated_at=datetime.now(UTC),
        content_hash="a" * 64,
    )

    schema = LegalAgentContractRegistry().runtime_output_schema(
        definition,
        AgentExecutionContext(snapshot=snapshot, input_payload={"phase": "planning"}),
    )

    assert "oneOf" not in schema
    assert schema["properties"]["phase"]["const"] == "planning"
