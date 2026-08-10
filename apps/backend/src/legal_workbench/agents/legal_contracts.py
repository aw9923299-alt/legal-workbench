from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from legal_workbench.agents.message_judgement import _to_camel
from legal_workbench.domain.enums import (
    AuthorityRole,
    AuthorityStatus,
    AuthorityType,
    KnowledgeMetadataStatus,
)


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
    authority_role: AuthorityRole
    jurisdiction: str = Field(min_length=1)
    effective_date: dt.date
    historical_analysis: bool


class SourceAuthorityMetadata(StrictLegalModel):
    authority_type: AuthorityType
    authority_role: AuthorityRole | None
    authority_status: AuthorityStatus
    metadata_status: KnowledgeMetadataStatus
    jurisdiction: str = Field(min_length=1)
    effective_from: dt.date | None
    effective_to: dt.date | None


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
    authority_type: AuthorityType | None = None
    authority_role: AuthorityRole | None = None
    authority_status: AuthorityStatus | None = None
    metadata_status: KnowledgeMetadataStatus | None = None
    jurisdiction: str | None = None
    effective_from: dt.date | None = None
    effective_to: dt.date | None = None


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
    source_authorities: Mapping[str, Mapping[str, object]] | None = None,
    analysis_effective_date: dt.date | None = None,
    historical_as_of: dt.date | None = None,
) -> LegalWorkProduct:
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
    if source_authorities is None:
        return product
    unknown_status_used = False
    for item in product.legal_basis:
        if item.historical_analysis != (historical_as_of is not None):
            raise ValueError(
                "Historical legal basis mode must be authorized by deterministic input."
            )
        expected_date = historical_as_of or analysis_effective_date
        if expected_date is not None and item.effective_date != expected_date:
            raise ValueError(
                "Legal basis effective date must match the deterministic analysis date."
            )
        for source_ref in item.source_refs:
            metadata = source_authorities.get(source_ref)
            if metadata is None:
                raise ValueError(
                    f"Authority metadata is required for legal basis source: {source_ref}"
                )
            authority = SourceAuthorityMetadata.model_validate(
                {
                    key: metadata.get(key)
                    for key in (
                        "authorityType",
                        "authorityRole",
                        "authorityStatus",
                        "metadataStatus",
                        "jurisdiction",
                        "effectiveFrom",
                        "effectiveTo",
                    )
                }
            )
            if authority.authority_role != item.authority_role:
                raise ValueError(
                    "Declared legal basis authority role does not match source metadata: "
                    f"{source_ref}"
                )
            if authority.jurisdiction not in {item.jurisdiction, "ANY"}:
                raise ValueError(f"Legal basis jurisdiction does not match source: {source_ref}")
            if authority.authority_status == AuthorityStatus.UNKNOWN:
                unknown_status_used = True
                continue
            if authority.authority_status in {
                AuthorityStatus.REPEALED,
                AuthorityStatus.SUPERSEDED,
            } and not item.historical_analysis:
                raise ValueError(f"Legal basis source is not effective: {source_ref}")
            if (
                authority.effective_from is not None
                and item.effective_date < authority.effective_from
            ) or (
                authority.effective_to is not None
                and item.effective_date > authority.effective_to
            ):
                raise ValueError(
                    f"Legal basis effective date is outside source validity: {source_ref}"
                )
            if (
                item.authority_role == AuthorityRole.FORMAL_LEGAL_BASIS
                and authority.authority_status != AuthorityStatus.EFFECTIVE
                and not item.historical_analysis
            ):
                raise ValueError(f"Formal legal basis source is not effective: {source_ref}")
    if unknown_status_used and (
        product.confidence > 0.6 or not product.missing_information
    ):
        raise ValueError(
            "Unknown authority status requires confidence at most 0.6 and missing information."
        )
    canonical_citations: list[LegalCitation] = []
    for citation in product.citations:
        metadata = source_authorities.get(citation.source_ref)
        if not isinstance(metadata, Mapping):
            raise ValueError(
                f"Canonical citation metadata is required for: {citation.source_ref}"
            )
        title = metadata.get("title")
        source_type = metadata.get("sourceType")
        content_hash = metadata.get("contentHash")
        if source_type == "document_segment":
            source_type = "attachment"
        if (
            not isinstance(title, str)
            or not title.strip()
            or not isinstance(source_type, str)
            or not source_type.strip()
            or not isinstance(content_hash, str)
            or not content_hash.strip()
        ):
            raise ValueError(
                f"Canonical citation metadata is incomplete for: {citation.source_ref}"
            )
        canonical_citations.append(
            LegalCitation.model_validate(
                {
                    "sourceRef": citation.source_ref,
                    "title": title,
                    "sourceType": source_type,
                    "locator": metadata.get("locator"),
                    "contentHash": content_hash,
                    "internalPrecedent": citation.source_ref in precedents,
                    "authorityType": metadata.get("authorityType"),
                    "authorityRole": metadata.get("authorityRole"),
                    "authorityStatus": metadata.get("authorityStatus"),
                    "metadataStatus": metadata.get("metadataStatus"),
                    "jurisdiction": metadata.get("jurisdiction"),
                    "effectiveFrom": metadata.get("effectiveFrom"),
                    "effectiveTo": metadata.get("effectiveTo"),
                }
            )
        )
    return product.model_copy(update={"citations": canonical_citations})
