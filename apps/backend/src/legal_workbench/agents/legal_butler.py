from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Literal

from pydantic import Field, model_validator

from legal_workbench.agents.legal_contracts import (
    LegalCitation,
    RiskLikelihood,
    RiskSeverity,
    SourceAuthorityMetadata,
    StrictLegalModel,
)
from legal_workbench.domain.enums import AuthorityStatus

LEGAL_SPECIALIST_KEYS = frozenset(
    {
        "legal_consultation",
        "contract_review",
        "dispute_complaint",
        "ip_copyright",
        "labor_employment",
    }
)


class ButlerPlanStep(StrictLegalModel):
    step_id: str = Field(min_length=1)
    agent_key: Literal[
        "legal_consultation",
        "contract_review",
        "dispute_complaint",
        "ip_copyright",
        "labor_employment",
    ]
    objective: str = Field(min_length=1)
    depends_on: list[str]
    context_requirements: list[str]


class ButlerPlanningOutput(StrictLegalModel):
    phase: Literal["planning"]
    objective: str = Field(min_length=1)
    matter_id: str | None
    work_item_id: str | None
    task_types: list[str] = Field(min_length=1)
    steps: list[ButlerPlanStep] = Field(min_length=1, max_length=4)
    missing_information: list[str]
    requires_user_input: bool
    synthesis_strategy: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dag(self) -> ButlerPlanningOutput:
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Butler step IDs must be unique.")
        known = set(ids)
        if any(dep not in known for step in self.steps for dep in step.depends_on):
            raise ValueError("Butler dependencies must reference a plan step.")
        dependencies = {step.step_id: set(step.depends_on) for step in self.steps}
        ready = {step_id for step_id, deps in dependencies.items() if not deps}
        visited: set[str] = set()
        while ready:
            current = min(ready)
            ready.remove(current)
            visited.add(current)
            for step_id, deps in dependencies.items():
                if step_id not in visited and deps <= visited:
                    ready.add(step_id)
        if visited != known:
            raise ValueError("Butler execution plan cannot contain a cycle.")
        return self


class ButlerAgentPosition(StrictLegalModel):
    agent_key: str = Field(min_length=1)
    position: str = Field(min_length=1)


class ButlerConflict(StrictLegalModel):
    topic: str = Field(min_length=1)
    agent_positions: list[ButlerAgentPosition] = Field(min_length=2)
    support_refs: list[str] = Field(min_length=1)
    resolution_needed: str = Field(min_length=1)


class ButlerGroundedFact(StrictLegalModel):
    fact: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class ButlerGroundedIssue(StrictLegalModel):
    issue: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class ButlerGroundedRisk(StrictLegalModel):
    description: str = Field(min_length=1)
    severity: RiskSeverity
    likelihood: RiskLikelihood
    support_refs: list[str] = Field(min_length=1)


class ButlerGroundedStrategy(StrictLegalModel):
    action: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    support_refs: list[str] = Field(min_length=1)


class ButlerGroundedAction(StrictLegalModel):
    action: str = Field(min_length=1)
    support_refs: list[str] = Field(min_length=1)


class ButlerSynthesisOutput(StrictLegalModel):
    phase: Literal["synthesis"]
    matter_assessment: str = Field(min_length=1)
    core_facts: list[ButlerGroundedFact] = Field(min_length=1)
    key_legal_issues: list[ButlerGroundedIssue] = Field(min_length=1)
    integrated_risks: list[ButlerGroundedRisk] = Field(min_length=1)
    recommended_strategy: list[ButlerGroundedStrategy] = Field(min_length=1)
    next_actions: list[ButlerGroundedAction] = Field(min_length=1)
    missing_information: list[str]
    draft_response: str = Field(min_length=1)
    participating_agents: list[str]
    citations: list[LegalCitation] = Field(min_length=1)
    conflicts: list[ButlerConflict]
    confidence: float = Field(ge=0, le=1)


def validate_butler_synthesis_sources(
    output: ButlerSynthesisOutput,
    *,
    authorized_source_refs: set[str],
    internal_precedent_refs: set[str],
    source_metadata: Mapping[str, Mapping[str, object]] | None = None,
    analysis_jurisdiction: str | None = None,
    historical_as_of: dt.date | None = None,
) -> ButlerSynthesisOutput:
    support_refs = {
        source_ref
        for item in (
            *output.core_facts,
            *output.key_legal_issues,
            *output.integrated_risks,
            *output.recommended_strategy,
            *output.next_actions,
            *output.conflicts,
        )
        for source_ref in (
            getattr(item, "source_refs", None)
            or getattr(item, "support_refs", None)
            or []
        )
    }
    unauthorized = sorted(support_refs - authorized_source_refs)
    if unauthorized:
        raise ValueError(f"Unauthorized Butler synthesis support references: {unauthorized}")
    if any(citation.source_type == "upstream_agent" for citation in output.citations):
        raise ValueError("Butler synthesis citations must identify original sources.")
    citation_refs = {citation.source_ref for citation in output.citations}
    unauthorized_citations = sorted(citation_refs - authorized_source_refs)
    if unauthorized_citations:
        raise ValueError(f"Unauthorized Butler synthesis citations: {unauthorized_citations}")
    missing_citations = sorted(support_refs - citation_refs)
    if missing_citations:
        raise ValueError(
            f"Butler synthesis support references are missing final citations: {missing_citations}"
        )
    mislabeled = sorted(
        citation.source_ref
        for citation in output.citations
        if citation.internal_precedent
        != (citation.source_ref in internal_precedent_refs)
    )
    if mislabeled:
        raise ValueError(
            "Butler synthesis precedent labels do not match authorized context: "
            f"{mislabeled}"
        )
    if source_metadata is None:
        return output

    unknown_status_used = False
    for source_ref in support_refs:
        metadata = source_metadata.get(source_ref)
        if metadata is None:
            raise ValueError(
                f"Canonical source metadata is required for Butler support: {source_ref}"
            )
        if not metadata.get("authorityType"):
            continue
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
        if (
            analysis_jurisdiction
            and authority.jurisdiction not in {analysis_jurisdiction, "ANY"}
        ):
            raise ValueError(
                f"Butler source jurisdiction does not match analysis: {source_ref}"
            )
        if authority.authority_status == AuthorityStatus.UNKNOWN:
            unknown_status_used = True
            continue
        if authority.authority_status in {
            AuthorityStatus.REPEALED,
            AuthorityStatus.SUPERSEDED,
        }:
            if historical_as_of is None:
                raise ValueError(f"Butler authority source is not effective: {source_ref}")
            if (
                authority.effective_from is not None
                and historical_as_of < authority.effective_from
            ) or (
                authority.effective_to is not None
                and historical_as_of > authority.effective_to
            ):
                raise ValueError(
                    f"Butler historical date is outside source validity: {source_ref}"
                )
    if unknown_status_used and (
        output.confidence > 0.6 or not output.missing_information
    ):
        raise ValueError(
            "Unknown authority status requires Butler confidence at most 0.6 "
            "and missing information."
        )

    canonical_citations: list[LegalCitation] = []
    for citation in output.citations:
        metadata = source_metadata.get(citation.source_ref)
        if metadata is None:
            raise ValueError(
                f"Canonical citation metadata is required for: {citation.source_ref}"
            )
        source_type = str(metadata.get("sourceType") or "")
        if source_type == "document_segment":
            source_type = "attachment"
        canonical_citations.append(
            LegalCitation.model_validate(
                {
                    "sourceRef": citation.source_ref,
                    "title": str(metadata.get("title") or citation.source_ref),
                    "sourceType": source_type,
                    "locator": metadata.get("locator"),
                    "contentHash": metadata.get("contentHash"),
                    "internalPrecedent": (
                        citation.source_ref in internal_precedent_refs
                    ),
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
    return output.model_copy(update={"citations": canonical_citations})
