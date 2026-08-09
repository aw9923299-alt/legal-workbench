from __future__ import annotations

import asyncio
from time import monotonic
from uuid import uuid4

import pytest

from legal_workbench.application.legal_agent_orchestrator import (
    SpecialistStepExecution,
    execute_plan_waves,
)
from legal_workbench.domain.entities import AgentExecutionPlan, AgentPlanStep
from legal_workbench.domain.enums import AgentExecutionPlanStatus, AgentPlanStepStatus


@pytest.mark.asyncio
async def test_independent_steps_overlap_and_dependency_waits_for_wave() -> None:
    plan_id = uuid4()
    steps = [
        AgentPlanStep(
            id=uuid4(),
            execution_plan_id=plan_id,
            step_id="contract",
            sequence=1,
            agent_key="contract_review",
            objective="合同",
            depends_on=[],
            context_requirements=[],
        ),
        AgentPlanStep(
            id=uuid4(),
            execution_plan_id=plan_id,
            step_id="ip",
            sequence=2,
            agent_key="ip_copyright",
            objective="知识产权",
            depends_on=[],
            context_requirements=[],
        ),
        AgentPlanStep(
            id=uuid4(),
            execution_plan_id=plan_id,
            step_id="consult",
            sequence=3,
            agent_key="legal_consultation",
            objective="综合前置事实",
            depends_on=["contract", "ip"],
            context_requirements=[],
        ),
    ]
    plan = AgentExecutionPlan(
        id=plan_id,
        matter_id=uuid4(),
        work_item_id=None,
        objective="并发测试",
        status=AgentExecutionPlanStatus.PLANNED,
        task_types=["contract", "ip"],
        synthesis_strategy="测试",
        missing_information=[],
        requires_user_input=False,
        correlation_id="corr-concurrency",
        idempotency_key="concurrency",
        created_by="test",
        steps=steps,
    )
    timestamps: dict[str, tuple[float, float]] = {}

    async def runner(
        step: AgentPlanStep,
        completed: dict[str, SpecialistStepExecution],
    ) -> SpecialistStepExecution:
        started = monotonic()
        if step.step_id == "consult":
            assert set(completed) == {"contract", "ip"}
        await asyncio.sleep(0.05)
        timestamps[step.step_id] = (started, monotonic())
        return SpecialistStepExecution(
            step_id=step.step_id,
            agent_key=step.agent_key,
            run_id=uuid4(),
            status=AgentPlanStepStatus.COMPLETED,
        )

    results = await execute_plan_waves(plan, runner)

    assert [result.step_id for result in results] == ["contract", "ip", "consult"]
    assert timestamps["contract"][0] < timestamps["ip"][1]
    assert timestamps["ip"][0] < timestamps["contract"][1]
    assert timestamps["consult"][0] >= max(
        timestamps["contract"][1], timestamps["ip"][1]
    )


@pytest.mark.asyncio
async def test_failed_dependency_is_skipped_without_invoking_runner() -> None:
    plan_id = uuid4()
    first = AgentPlanStep(
        id=uuid4(),
        execution_plan_id=plan_id,
        step_id="first",
        sequence=1,
        agent_key="contract_review",
        objective="先执行",
        depends_on=[],
        context_requirements=[],
    )
    dependent = AgentPlanStep(
        id=uuid4(),
        execution_plan_id=plan_id,
        step_id="dependent",
        sequence=2,
        agent_key="ip_copyright",
        objective="依赖执行",
        depends_on=["first"],
        context_requirements=[],
    )
    plan = AgentExecutionPlan(
        id=plan_id,
        matter_id=uuid4(),
        work_item_id=None,
        objective="失败降级测试",
        status=AgentExecutionPlanStatus.PLANNED,
        task_types=["test"],
        synthesis_strategy="测试",
        missing_information=[],
        requires_user_input=False,
        correlation_id="corr-failure",
        idempotency_key="failure",
        created_by="test",
        steps=[first, dependent],
    )
    invoked: list[str] = []

    async def runner(
        step: AgentPlanStep,
        completed: dict[str, SpecialistStepExecution],
    ) -> SpecialistStepExecution:
        invoked.append(step.step_id)
        return SpecialistStepExecution(
            step_id=step.step_id,
            agent_key=step.agent_key,
            run_id=uuid4(),
            status=AgentPlanStepStatus.FAILED,
            failure_code="FIXTURE_FAILURE",
        )

    results = await execute_plan_waves(plan, runner)

    assert invoked == ["first"]
    assert results[1].status == AgentPlanStepStatus.SKIPPED
    assert results[1].failure_code == "DEPENDENCY_FAILED"
