from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from legal_workbench.agents.legal_contracts import LegalCitation, LegalRiskItem, StrictLegalModel

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
    resolution_needed: str = Field(min_length=1)


class ButlerSynthesisOutput(StrictLegalModel):
    phase: Literal["synthesis"]
    matter_assessment: str = Field(min_length=1)
    core_facts: list[str]
    key_legal_issues: list[str]
    integrated_risks: list[LegalRiskItem]
    recommended_strategy: list[str]
    next_actions: list[str]
    missing_information: list[str]
    draft_response: str
    participating_agents: list[str]
    citations: list[LegalCitation]
    conflicts: list[ButlerConflict]
    confidence: float = Field(ge=0, le=1)
