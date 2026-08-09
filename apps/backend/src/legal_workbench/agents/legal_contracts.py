from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from legal_workbench.agents.message_judgement import _to_camel


class StrictLegalModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class LegalAgentInput(StrictLegalModel):
    run_id: str = Field(min_length=1)
    phase: Literal["planning", "specialist", "synthesis"]
    objective: str = Field(min_length=1)
    matter_id: str | None = None
    work_item_id: str | None = None
    authorized_context: dict[str, object]
    authorized_source_refs: list[str]
    upstream_outputs: dict[str, object] = Field(default_factory=dict)
    constraints: dict[str, object]


class GroundedFact(StrictLegalModel):
    fact: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class LegalBasisItem(StrictLegalModel):
    proposition: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)
    effective_date: dt.date


class AnalysisItem(StrictLegalModel):
    conclusion: str = Field(min_length=1)
    support_refs: list[str] = Field(min_length=1)


RiskSeverity = Literal["critical", "high", "medium", "low"]
RiskLikelihood = Literal["likely", "possible", "unlikely", "unknown"]


class LegalRiskItem(StrictLegalModel):
    description: str = Field(min_length=1)
    severity: RiskSeverity
    likelihood: RiskLikelihood


class LegalCitation(StrictLegalModel):
    source_ref: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: Literal[
        "context_snapshot",
        "feishu_message",
        "attachment",
        "knowledge_document",
        "historical_matter",
        "approved_example",
        "upstream_agent",
    ]
    locator: str | None = None
    content_hash: str | None = None
    internal_precedent: bool = False


class LegalWorkProduct(StrictLegalModel):
    executive_summary: str = Field(min_length=1)
    facts: list[GroundedFact]
    issues: list[str]
    legal_basis: list[LegalBasisItem]
    analysis: list[AnalysisItem]
    risks: list[LegalRiskItem]
    recommended_actions: list[str]
    missing_information: list[str]
    assumptions: list[str]
    draft_response: str
    confidence: float = Field(ge=0, le=1)
    citations: list[LegalCitation]


class LegalConsultationProduct(LegalWorkProduct):
    questions: list[str] = Field(min_length=1)
    legal_relationships: list[str]


class ClauseRisk(StrictLegalModel):
    clause_locator: str = Field(min_length=1)
    clause_text: str = Field(min_length=1)
    risk: str = Field(min_length=1)
    severity: RiskSeverity
    source_refs: list[str] = Field(min_length=1)


class ContractReviewProduct(LegalWorkProduct):
    contract_summary: str = Field(min_length=1)
    parties: list[str]
    commercial_terms: list[str]
    clause_risks: list[ClauseRisk]
    missing_terms: list[str]
    proposed_changes: list[str]
    fallback_positions: list[str]
    negotiation_points: list[str]


class TimelineEvent(StrictLegalModel):
    date: dt.date | None = None
    event: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class EvidenceItem(StrictLegalModel):
    description: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    supports: list[str]


class DisputeRisk(StrictLegalModel):
    issue: str = Field(min_length=1)
    severity: RiskSeverity
    likelihood: RiskLikelihood
    mitigation: str = Field(min_length=1)


class DisputeComplaintProduct(LegalWorkProduct):
    timeline: list[TimelineEvent]
    claims: list[str]
    counterparty_positions: list[str]
    evidence: list[EvidenceItem]
    evidence_gaps: list[str]
    legal_arguments: list[str]
    defenses: list[str]
    risk_matrix: list[DisputeRisk]
    strategy: list[str]
    next_actions: list[str]


class RightsObject(StrictLegalModel):
    category: Literal[
        "copyright",
        "trademark",
        "image_portrait",
        "music_material_license",
        "content_similarity",
    ]
    description: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class AuthorizationLink(StrictLegalModel):
    grantor: str = Field(min_length=1)
    grantee: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    evidence_refs: list[str]
    gap: str | None = None


class IpCopyrightProduct(LegalWorkProduct):
    rights_objects: list[RightsObject]
    rights_basis: list[str]
    authorization_chain: list[AuthorizationLink]
    infringement_elements: list[str]
    defenses: list[str]
    evidence: list[EvidenceItem]
    evidence_gaps: list[str]


class EmploymentAssessment(StrictLegalModel):
    conclusion: str = Field(min_length=1)
    basis_refs: list[str] = Field(min_length=1)
    risks: list[str]


class LaborEmploymentProduct(LegalWorkProduct):
    employment_relationship: str = Field(min_length=1)
    discipline: list[str]
    termination: list[str]
    resignation: list[str]
    compensation: list[str]
    substantive_assessment: EmploymentAssessment
    procedural_assessment: EmploymentAssessment
    evidence: list[EvidenceItem]


LEGAL_OUTPUT_MODELS: dict[str, type[LegalWorkProduct]] = {
    "legal_consultation": LegalConsultationProduct,
    "contract_review": ContractReviewProduct,
    "dispute_complaint": DisputeComplaintProduct,
    "ip_copyright": IpCopyrightProduct,
    "labor_employment": LaborEmploymentProduct,
}


def validate_legal_work_product_sources(
    product: LegalWorkProduct,
    *,
    authorized_source_refs: set[str],
    internal_precedent_refs: set[str] | None = None,
) -> None:
    """Fail closed when a specialist cites anything outside its authorized context."""

    used: set[str] = set()

    def collect(value: object, *, field_name: str | None = None) -> None:
        if isinstance(value, list):
            if field_name in {"sourceRefs", "supportRefs", "basisRefs", "evidenceRefs"}:
                used.update(item for item in value if isinstance(item, str))
            else:
                for item in value:
                    collect(item)
            return
        if not isinstance(value, dict):
            if field_name == "sourceRef" and isinstance(value, str):
                used.add(value)
            return
        for key, item in value.items():
            collect(item, field_name=key)

    collect(product.model_dump(by_alias=True, mode="json"))
    unauthorized = sorted(used - authorized_source_refs)
    if unauthorized:
        raise ValueError(f"Unauthorized legal source references: {unauthorized}")
    precedents = internal_precedent_refs or set()
    invalid_basis = sorted(
        {ref for item in product.legal_basis for ref in item.source_refs if ref in precedents}
    )
    if invalid_basis:
        raise ValueError(f"Internal precedent cannot ground formal legal basis: {invalid_basis}")
    mislabeled = sorted(
        citation.source_ref
        for citation in product.citations
        if citation.internal_precedent != (citation.source_ref in precedents)
    )
    if mislabeled:
        raise ValueError(f"Internal precedent citation labels do not match context: {mislabeled}")
