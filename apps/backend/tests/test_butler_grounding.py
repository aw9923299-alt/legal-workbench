from __future__ import annotations

import pytest
from pydantic import ValidationError

from legal_workbench.agents.legal_butler import (
    ButlerSynthesisOutput,
    validate_butler_synthesis_sources,
)


def _payload() -> dict[str, object]:
    return {
        "phase": "synthesis",
        "matterAssessment": "需要先补材料再推进。",
        "coreFacts": [{"fact": "已签合同", "sourceRefs": ["ctx:segment:s1"]}],
        "keyLegalIssues": [
            {"issue": "责任范围", "sourceRefs": ["knowledge:chunk:k1"]}
        ],
        "integratedRisks": [
            {
                "description": "责任无上限",
                "severity": "high",
                "likelihood": "possible",
                "supportRefs": ["ctx:segment:s1", "knowledge:chunk:k1"],
            }
        ],
        "recommendedStrategy": [
            {
                "action": "增加责任上限",
                "rationale": "控制敞口",
                "supportRefs": ["ctx:segment:s1", "knowledge:chunk:k1"],
            }
        ],
        "nextActions": [
            {"action": "发修订稿", "supportRefs": ["ctx:segment:s1"]}
        ],
        "missingInformation": [],
        "draftResponse": "请确认修订稿。",
        "participatingAgents": ["contract_review"],
        "citations": [
            {
                "sourceRef": "ctx:segment:s1",
                "title": "合同第八条",
                "sourceType": "attachment",
                "internalPrecedent": False,
            },
            {
                "sourceRef": "knowledge:chunk:k1",
                "title": "法律",
                "sourceType": "knowledge_document",
                "internalPrecedent": False,
            },
        ],
        "conflicts": [],
        "confidence": 0.8,
    }


def test_every_butler_item_is_grounded_in_original_authorized_sources() -> None:
    output = ButlerSynthesisOutput.model_validate(_payload())

    validate_butler_synthesis_sources(
        output,
        authorized_source_refs={"ctx:segment:s1", "knowledge:chunk:k1"},
        internal_precedent_refs=set(),
    )


def test_unauthorized_item_support_ref_fails_closed_even_if_citations_are_valid() -> None:
    payload = _payload()
    payload["nextActions"] = [
        {"action": "外部动作", "supportRefs": ["agent-run:specialist-1"]}
    ]
    output = ButlerSynthesisOutput.model_validate(payload)

    with pytest.raises(ValueError, match="Unauthorized Butler synthesis support"):
        validate_butler_synthesis_sources(
            output,
            authorized_source_refs={"ctx:segment:s1", "knowledge:chunk:k1"},
            internal_precedent_refs=set(),
        )


def test_support_ref_must_have_final_original_source_citation() -> None:
    payload = _payload()
    payload["citations"] = [payload["citations"][0]]  # type: ignore[index]
    output = ButlerSynthesisOutput.model_validate(payload)

    with pytest.raises(ValueError, match="missing final citations"):
        validate_butler_synthesis_sources(
            output,
            authorized_source_refs={"ctx:segment:s1", "knowledge:chunk:k1"},
            internal_precedent_refs=set(),
        )


def test_specialist_run_cannot_replace_original_source_citation() -> None:
    payload = _payload()
    payload["citations"] = [
        {
            "sourceRef": "agent-run:specialist-1",
            "title": "Specialist",
            "sourceType": "upstream_agent",
            "internalPrecedent": False,
        }
    ]
    output = ButlerSynthesisOutput.model_validate(payload)

    with pytest.raises(ValueError, match="original sources"):
        validate_butler_synthesis_sources(
            output,
            authorized_source_refs={
                "ctx:segment:s1",
                "knowledge:chunk:k1",
                "agent-run:specialist-1",
            },
            internal_precedent_refs=set(),
        )


@pytest.mark.parametrize(
    "field",
    [
        "coreFacts",
        "keyLegalIssues",
        "integratedRisks",
        "recommendedStrategy",
        "nextActions",
        "citations",
    ],
)
def test_final_butler_review_rejects_missing_grounded_sections(field: str) -> None:
    payload = _payload()
    payload[field] = []

    with pytest.raises(ValidationError):
        ButlerSynthesisOutput.model_validate(payload)
