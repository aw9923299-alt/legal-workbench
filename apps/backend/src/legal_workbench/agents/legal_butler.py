from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from legal_workbench.agents.legal_contracts import (
    LegalCitation,
    RiskLikelihood,
    RiskSeverity,
    StrictLegalModel,
)

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
    core_facts: list[ButlerGroundedFact]
    key_legal_issues: list[ButlerGroundedIssue]
    integrated_risks: list[ButlerGroundedRisk]
    recommended_strategy: list[ButlerGroundedStrategy]
    next_actions: list[ButlerGroundedAction]
    missing_information: list[str]
    draft_response: str
    participating_agents: list[str]
    citations: list[LegalCitation]
    conflicts: list[ButlerConflict]
    confidence: float = Field(ge=0, le=1)


def validate_butler_synthesis_sources(
    output: ButlerSynthesisOutput,
    *,
    authorized_source_refs: set[str],
    internal_precedent_refs: set[str],
) -> None:
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
