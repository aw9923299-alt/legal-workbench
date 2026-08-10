from __future__ import annotations

from datetime import date

import pytest

from legal_workbench.agents.legal_contracts import (
    LegalConsultationProduct,
    validate_legal_work_product_sources,
)

CANONICAL_CITATION_METADATA = {
    "title": "数据库权威资料",
    "sourceType": "knowledge_document",
    "locator": "第一条",
    "contentHash": "a" * 64,
    "internalPrecedent": False,
}


def _product(
    *,
    role: str,
    confidence: float = 0.8,
    missing: list[str] | None = None,
    effective_date: str = "2026-08-09",
    historical_analysis: bool = False,
):
    return LegalConsultationProduct.model_validate(
        {
            "executiveSummary": "结论",
            "facts": [{"fact": "存在争议", "sourceRefs": ["ctx:message:m1"]}],
            "issues": ["依据类型"],
            "legalBasis": [
                {
                    "proposition": "待验证命题",
                    "sourceRefs": ["knowledge:chunk:k1"],
                    "authorityRole": role,
                    "jurisdiction": "CN",
                    "effectiveDate": effective_date,
                    "historicalAnalysis": historical_analysis,
                }
            ],
            "analysis": [
                {"conclusion": "分析", "supportRefs": ["knowledge:chunk:k1"]}
            ],
            "risks": [],
            "recommendedActions": [],
            "missingInformation": missing or [],
            "assumptions": [],
            "draftResponse": "草稿",
            "confidence": confidence,
            "citations": [
                {
                    "sourceRef": "knowledge:chunk:k1",
                    "title": "资料",
                    "sourceType": "knowledge_document",
                    "internalPrecedent": False,
                }
            ],
            "questions": ["问题"],
            "legalRelationships": [],
        }
    )


@pytest.mark.parametrize(
    ("authority_type", "actual_role", "declared_role"),
    [
        ("company_policy", "internal_basis", "formal_legal_basis"),
        ("legal_opinion", "strategy_reference", "formal_legal_basis"),
        ("contract", "contractual_basis", "formal_legal_basis"),
    ],
)
def test_non_law_sources_cannot_masquerade_as_formal_legal_basis(
    authority_type: str,
    actual_role: str,
    declared_role: str,
) -> None:
    product = _product(role=declared_role)

    with pytest.raises(ValueError, match="authority role"):
        validate_legal_work_product_sources(
            product,
            authorized_source_refs={"ctx:message:m1", "knowledge:chunk:k1"},
            source_authorities={
                "knowledge:chunk:k1": {
                    **CANONICAL_CITATION_METADATA,
                    "authorityType": authority_type,
                    "authorityRole": actual_role,
                    "authorityStatus": "effective",
                    "metadataStatus": "ready",
                    "jurisdiction": "CN",
                    "effectiveFrom": "2020-01-01",
                    "effectiveTo": None,
                }
            },
        )


def test_effective_law_can_ground_formal_legal_basis() -> None:
    product = _product(role="formal_legal_basis")

    validate_legal_work_product_sources(
        product,
        authorized_source_refs={"ctx:message:m1", "knowledge:chunk:k1"},
        source_authorities={
            "knowledge:chunk:k1": {
                **CANONICAL_CITATION_METADATA,
                "authorityType": "law",
                "authorityRole": "formal_legal_basis",
                "authorityStatus": "effective",
                "metadataStatus": "ready",
                "jurisdiction": "CN",
                "effectiveFrom": "2021-01-01",
                "effectiveTo": None,
            }
        },
    )


def test_repealed_law_rejected_for_current_basis() -> None:
    product = _product(role="formal_legal_basis")

    with pytest.raises(ValueError, match="not effective"):
        validate_legal_work_product_sources(
            product,
            authorized_source_refs={"ctx:message:m1", "knowledge:chunk:k1"},
            source_authorities={
                "knowledge:chunk:k1": {
                    **CANONICAL_CITATION_METADATA,
                    "authorityType": "law",
                    "authorityRole": "formal_legal_basis",
                    "authorityStatus": "repealed",
                    "metadataStatus": "ready",
                    "jurisdiction": "CN",
                    "effectiveFrom": "2010-01-01",
                    "effectiveTo": "2020-12-31",
                }
            },
        )


def test_historical_basis_requires_backend_as_of_and_valid_period() -> None:
    product = _product(
        role="formal_legal_basis",
        effective_date="2019-06-01",
        historical_analysis=True,
    )
    authority = {
        "knowledge:chunk:k1": {
            **CANONICAL_CITATION_METADATA,
            "authorityType": "law",
            "authorityRole": "formal_legal_basis",
            "authorityStatus": "repealed",
            "metadataStatus": "ready",
            "jurisdiction": "CN",
            "effectiveFrom": "2010-01-01",
            "effectiveTo": "2020-12-31",
        }
    }

    with pytest.raises(ValueError, match="authorized by deterministic input"):
        validate_legal_work_product_sources(
            product,
            authorized_source_refs={"ctx:message:m1", "knowledge:chunk:k1"},
            source_authorities=authority,
        )

    validate_legal_work_product_sources(
        product,
        authorized_source_refs={"ctx:message:m1", "knowledge:chunk:k1"},
        source_authorities=authority,
        analysis_effective_date=date(2019, 6, 1),
        historical_as_of=date(2019, 6, 1),
    )


def test_unknown_status_requires_low_confidence_and_missing_information() -> None:
    product = _product(role="formal_legal_basis", confidence=0.8)
    authority = {
        "knowledge:chunk:k1": {
            **CANONICAL_CITATION_METADATA,
            "authorityType": "law",
            "authorityRole": "formal_legal_basis",
            "authorityStatus": "unknown",
            "metadataStatus": "ready",
            "jurisdiction": "CN",
            "effectiveFrom": None,
            "effectiveTo": None,
        }
    }

    with pytest.raises(ValueError, match="confidence"):
        validate_legal_work_product_sources(
            product,
            authorized_source_refs={"ctx:message:m1", "knowledge:chunk:k1"},
            source_authorities=authority,
        )

    validate_legal_work_product_sources(
        _product(role="formal_legal_basis", confidence=0.6, missing=["核实法规效力"]),
        authorized_source_refs={"ctx:message:m1", "knowledge:chunk:k1"},
        source_authorities=authority,
    )
