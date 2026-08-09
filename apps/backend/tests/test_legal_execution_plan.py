from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest

from legal_workbench.agents.professional import LEGAL_SPECIALIST_KEYS
from legal_workbench.domain.entities import AgentExecutionPlan, AgentPlanStep
from legal_workbench.domain.enums import AgentExecutionPlanStatus, AgentPlanStepStatus
from legal_workbench.domain.errors import DomainValidationError


def _step(
    plan_id: UUID,
    step_id: str,
    agent_key: str,
    *,
    depends_on: list[str] | None = None,
    sequence: int = 1,
) -> AgentPlanStep:
    return AgentPlanStep(
        id=uuid4(),
        execution_plan_id=plan_id,
        step_id=step_id,
        sequence=sequence,
        agent_key=agent_key,
        objective=f"处理 {step_id}",
        depends_on=depends_on or [],
        context_requirements=["matter"],
    )


def _plan(steps: list[AgentPlanStep]) -> AgentExecutionPlan:
    plan_id = steps[0].execution_plan_id
    return AgentExecutionPlan(
        id=plan_id,
        matter_id=uuid4(),
        work_item_id=None,
        objective="审查合作合同及图片授权",
        status=AgentExecutionPlanStatus.PLANNED,
        task_types=["contract", "ip"],
        synthesis_strategy="显式综合合同与授权风险",
        missing_information=[],
        requires_user_input=False,
        correlation_id="corr-legal-1",
        idempotency_key="manual:matter:1",
        created_by="user:test",
        steps=steps,
    )


def test_plan_builds_deterministic_parallel_and_sequential_waves() -> None:
    plan_id = uuid4()
    plan = _plan(
        [
            _step(plan_id, "ip", "ip_copyright", sequence=2),
            _step(plan_id, "contract", "contract_review", sequence=1),
            _step(
                plan_id,
                "consult",
                "legal_consultation",
                depends_on=["contract", "ip"],
                sequence=3,
            ),
        ]
    )

    plan.validate_steps(LEGAL_SPECIALIST_KEYS)

    assert [[step.step_id for step in wave] for wave in plan.ready_waves()] == [
        ["contract", "ip"],
        ["consult"],
    ]
    assert all(step.status == AgentPlanStepStatus.PENDING for step in plan.steps)


@pytest.mark.parametrize(
    "steps_factory",
    [
        lambda plan_id: [
            _step(plan_id, "a", "contract_review", depends_on=["b"]),
            _step(plan_id, "b", "ip_copyright", depends_on=["a"], sequence=2),
        ],
        lambda plan_id: [_step(plan_id, "a", "not_registered")],
        lambda plan_id: [_step(plan_id, "a", "legal_butler")],
        lambda plan_id: [
            _step(plan_id, str(index), "legal_consultation", sequence=index) for index in range(5)
        ],
    ],
)
def test_plan_rejects_cycle_unknown_agent_recursive_butler_and_more_than_four(
    steps_factory: Callable[[UUID], list[AgentPlanStep]],
) -> None:
    plan_id = uuid4()
    plan = _plan(steps_factory(plan_id))

    with pytest.raises(DomainValidationError):
        plan.validate_steps(LEGAL_SPECIALIST_KEYS)


def test_plan_rejects_unknown_dependency_and_cross_plan_step() -> None:
    plan_id = uuid4()
    plan = _plan(
        [
            _step(plan_id, "contract", "contract_review", depends_on=["missing"]),
            _step(uuid4(), "ip", "ip_copyright", sequence=2),
        ]
    )

    with pytest.raises(DomainValidationError):
        plan.validate_steps(LEGAL_SPECIALIST_KEYS)
