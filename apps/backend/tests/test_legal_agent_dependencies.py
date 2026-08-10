from __future__ import annotations

from uuid import uuid4

import pytest

from legal_workbench.application.legal_dependencies import (
    DependencyContextAssembler,
    DependencyResult,
)
from legal_workbench.domain.agents import AgentPlanStep
from legal_workbench.domain.enums import AgentPlanStepStatus
from legal_workbench.domain.errors import DomainValidationError


def _step(step_id: str, depends_on: list[str]) -> AgentPlanStep:
    return AgentPlanStep(
        id=uuid4(),
        execution_plan_id=uuid4(),
        step_id=step_id,
        sequence=2,
        agent_key="legal_consultation",
        objective="分析",
        depends_on=depends_on,
        context_requirements=[],
    )


def _result(step_id: str, source_ref: str) -> DependencyResult:
    return DependencyResult(
        step_id=step_id,
        run_id=uuid4(),
        status=AgentPlanStepStatus.COMPLETED,
        output_payload={"step": step_id},
        source_refs=frozenset({source_ref}),
        internal_precedent_refs=frozenset(),
        source_authorities={
            source_ref: {
                "authorityType": "law",
                "authorityRole": "formal_legal_basis",
            }
        },
    )


def test_direct_dependency_excludes_sibling_output_and_authorization() -> None:
    a = _result("A", "knowledge:chunk:a")
    b = _result("B", "knowledge:chunk:b")

    context = DependencyContextAssembler().build(
        _step("C", ["A"]),
        {"A": a, "B": b},
    )

    assert context.upstream_outputs == {"A": {"step": "A"}}
    assert context.source_refs == frozenset({"knowledge:chunk:a"})
    assert "knowledge:chunk:b" not in context.source_authorities
    assert context.dependency_run_ids == (a.run_id,)


def test_needs_information_is_a_valid_direct_dependency() -> None:
    a = _result("A", "ctx:segment:a")
    a.status = AgentPlanStepStatus.NEEDS_INFORMATION

    context = DependencyContextAssembler().build(_step("C", ["A"]), {"A": a})

    assert context.upstream_outputs["A"] == {"step": "A"}


@pytest.mark.parametrize(
    "status",
    [AgentPlanStepStatus.FAILED, AgentPlanStepStatus.SKIPPED, AgentPlanStepStatus.RUNNING],
)
def test_invalid_or_stale_dependency_fails_closed(status: AgentPlanStepStatus) -> None:
    a = _result("A", "ctx:segment:a")
    a.status = status

    with pytest.raises(DomainValidationError, match="not valid"):
        DependencyContextAssembler().build(_step("C", ["A"]), {"A": a})


def test_missing_latest_valid_run_fails_closed() -> None:
    a = _result("A", "ctx:segment:a")
    a.run_id = None

    with pytest.raises(DomainValidationError, match="latest valid Run"):
        DependencyContextAssembler().build(_step("C", ["A"]), {"A": a})
