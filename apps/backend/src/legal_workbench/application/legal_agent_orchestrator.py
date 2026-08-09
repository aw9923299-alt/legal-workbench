from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from legal_workbench.agents.definitions import build_legal_agent_definitions
from legal_workbench.agents.legal_butler import (
    ButlerPlanningOutput,
    ButlerSynthesisOutput,
)
from legal_workbench.agents.legal_contracts import LEGAL_OUTPUT_MODELS, LegalWorkProduct
from legal_workbench.agents.professional import LEGAL_SPECIALIST_KEYS
from legal_workbench.agents.runtime import (
    AgentExecutionContext,
    AgentExecutionResult,
    AgentRuntime,
    AgentRuntimeError,
)
from legal_workbench.application.agent_attempts import AgentExecutionLeaseService
from legal_workbench.application.legal_context import (
    AuthorizedLegalContext,
    LegalContextBuilder,
)
from legal_workbench.application.legal_dependencies import (
    DependencyContext,
    DependencyContextAssembler,
    DependencyResult,
)
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.common import utc_now
from legal_workbench.domain.entities import (
    AgentAttemptLease,
    AgentExecutionPlan,
    AgentPlanStep,
    AgentRun,
    AgentRunSource,
    ContextSnapshot,
    DraftArtifact,
    OutboxEvent,
    ReviewPackage,
)
from legal_workbench.domain.enums import (
    AgentAttemptStatus,
    AgentExecutionPlanStatus,
    AgentPlanStepStatus,
    AgentRunRole,
    AgentRunSourceType,
    AgentRunStatus,
    ReviewPackageType,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityNotFoundError,
)


@dataclass(frozen=True, slots=True)
class LegalAgentTrigger:
    matter_id: UUID
    context_snapshot_id: UUID
    objective: str
    actor_id: str
    correlation_id: str
    idempotency_key: str
    work_item_id: UUID | None = None
    special_requirements: str | None = None
    specialist_only: str | None = None
    jurisdiction: str = "CN"


@dataclass(frozen=True, slots=True)
class SpecialistStepExecution:
    step_id: str
    agent_key: str
    run_id: UUID | None
    status: AgentPlanStepStatus
    output: LegalWorkProduct | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    source_refs: frozenset[str] = frozenset()
    internal_precedent_refs: frozenset[str] = frozenset()
    source_authorities: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LegalAgentOrchestrationResult:
    plan_id: UUID
    status: AgentExecutionPlanStatus
    planning_run_id: UUID | None
    synthesis_run_id: UUID | None
    artifact_id: UUID | None
    review_package_id: UUID | None
    step_results: tuple[SpecialistStepExecution, ...]
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class _ExistingPlanFound(Exception):
    plan: AgentExecutionPlan


StepRunner = Callable[
    [AgentPlanStep, dict[str, SpecialistStepExecution]],
    Awaitable[SpecialistStepExecution],
]


async def execute_plan_waves(
    plan: AgentExecutionPlan,
    runner: StepRunner,
    *,
    initial_results: tuple[SpecialistStepExecution, ...] = (),
) -> list[SpecialistStepExecution]:
    """Execute deterministic topological waves; only tasks in one wave overlap."""

    results = {value.step_id: value for value in initial_results}
    for wave in plan.ready_waves():
        runnable: list[AgentPlanStep] = []
        for step in wave:
            if step.step_id in results:
                continue
            dependency_results = [results[value] for value in step.depends_on]
            if any(
                value.status
                not in {
                    AgentPlanStepStatus.COMPLETED,
                    AgentPlanStepStatus.NEEDS_INFORMATION,
                }
                for value in dependency_results
            ):
                results[step.step_id] = SpecialistStepExecution(
                    step_id=step.step_id,
                    agent_key=step.agent_key,
                    run_id=None,
                    status=AgentPlanStepStatus.SKIPPED,
                    failure_code="DEPENDENCY_FAILED",
                    failure_message="A required specialist step did not complete.",
                )
            else:
                runnable.append(step)
        tasks: dict[str, asyncio.Task[SpecialistStepExecution]] = {}

        async def invoke(step: AgentPlanStep) -> SpecialistStepExecution:
            return await runner(step, dict(results))

        async with asyncio.TaskGroup() as group:
            for step in runnable:
                tasks[step.step_id] = group.create_task(invoke(step))
        for step in runnable:
            results[step.step_id] = tasks[step.step_id].result()
    return [results[step.step_id] for step in sorted(plan.steps, key=lambda item: item.sequence)]


class LegalAgentOrchestrator:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        runtime: AgentRuntime,
        context_builder: LegalContextBuilder,
        *,
        runs_root: str | Path,
        lease_seconds: int = 60,
        worker_id: str = "legal-agent-worker",
    ) -> None:
        self._uow_factory = uow_factory
        self._runtime = runtime
        self._context_builder = context_builder
        self._runs_root = Path(runs_root)
        self._lease_seconds = lease_seconds
        self._worker_id = worker_id
        self._definitions = build_legal_agent_definitions()
        self._dependency_assembler = DependencyContextAssembler()

    async def execute(self, trigger: LegalAgentTrigger) -> LegalAgentOrchestrationResult:
        existing = await self._get_existing(trigger.idempotency_key)
        if existing is not None:
            return await self._replay_result(existing)
        try:
            plan, planning_run, snapshot, matter_type = await self._prepare_planning(trigger)
        except _ExistingPlanFound as found:
            return await self._replay_result(found.plan)
        accepted_plan = await self._run_planning_phase(
            plan=plan,
            planning_run=planning_run,
            snapshot=snapshot,
            trigger=trigger,
        )
        if accepted_plan is None:
            return self._failed_result(plan, planning_run.id)
        plan = accepted_plan
        if plan.requires_user_input:
            return LegalAgentOrchestrationResult(
                plan_id=plan.id,
                status=AgentExecutionPlanStatus.NEEDS_INFORMATION,
                planning_run_id=plan.planning_run_id,
                synthesis_run_id=None,
                artifact_id=None,
                review_package_id=None,
                step_results=(),
            )

        async def runner(
            step: AgentPlanStep,
            completed: dict[str, SpecialistStepExecution],
        ) -> SpecialistStepExecution:
            dependency_context = self._dependency_assembler.build(
                step,
                self._dependency_results(completed),
            )
            return await self._execute_step(
                plan=plan,
                step=step,
                snapshot=snapshot,
                trigger=trigger,
                matter_type=matter_type,
                dependency_context=dependency_context,
            )

        step_results = await execute_plan_waves(plan, runner)
        await self._persist_skipped_steps(plan.id, step_results)
        return await self._synthesize(
            plan=plan,
            snapshot=snapshot,
            trigger=trigger,
            step_results=step_results,
        )

    async def recover(
        self,
        *,
        plan_id: UUID,
        correlation_id: str | None = None,
    ) -> LegalAgentOrchestrationResult:
        """Resume only the durable Legal Agent phase queued by recovery scan."""

        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation="legal_agent_recovery",
                key=str(plan_id),
            )
            plan = await uow.agent_execution_plans.get_for_update(plan_id)
            if plan is None or plan.planning_run_id is None:
                raise EntityNotFoundError("Recoverable Agent execution plan was not found.")
            planning_run = await uow.agent_runs.get(plan.planning_run_id)
            if planning_run is None:
                raise EntityNotFoundError("Recoverable Butler planning run was not found.")
            snapshot = await uow.context_snapshots.get(planning_run.context_snapshot_id)
            matter = await uow.matters.get(plan.matter_id)
            runs = list(await uow.agent_runs.list_by_plan(plan.id))
            if snapshot is None or matter is None:
                raise EntityNotFoundError("Recoverable Legal Agent context was not found.")
            await uow.commit()

        if plan.status in {
            AgentExecutionPlanStatus.COMPLETED,
            AgentExecutionPlanStatus.NEEDS_INFORMATION,
            AgentExecutionPlanStatus.CANCELLED,
        }:
            return await self._replay_result(plan)
        active = {
            AgentRunStatus.PREPARING,
            AgentRunStatus.RUNNING,
            AgentRunStatus.VALIDATING,
        }
        if any(run.status in active for run in runs):
            return await self._replay_result(plan)

        trigger = LegalAgentTrigger(
            matter_id=plan.matter_id,
            work_item_id=plan.work_item_id,
            context_snapshot_id=snapshot.id,
            objective=plan.objective,
            actor_id=plan.created_by,
            correlation_id=correlation_id or plan.correlation_id,
            idempotency_key=plan.idempotency_key,
        )
        if planning_run.status == AgentRunStatus.QUEUED:
            accepted = await self._run_planning_phase(
                plan=plan,
                planning_run=planning_run,
                snapshot=snapshot,
                trigger=trigger,
            )
            if accepted is None:
                return self._failed_result(plan, planning_run.id)
            plan = accepted
            if plan.requires_user_input:
                return await self._replay_result(plan)
        elif planning_run.status not in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.NEEDS_MORE_INFORMATION,
        }:
            return await self._replay_result(plan)

        persisted_results = await self._list_step_results(plan.id)
        initial_results = tuple(
            value
            for value in persisted_results
            if value.status
            in {
                AgentPlanStepStatus.COMPLETED,
                AgentPlanStepStatus.NEEDS_INFORMATION,
                AgentPlanStepStatus.FAILED,
                AgentPlanStepStatus.SKIPPED,
            }
        )
        runs_by_id = {run.id: run for run in runs}

        async def runner(
            step: AgentPlanStep,
            completed: dict[str, SpecialistStepExecution],
        ) -> SpecialistStepExecution:
            dependency_context = self._dependency_assembler.build(
                step,
                self._dependency_results(completed),
            )
            latest = runs_by_id.get(step.latest_run_id) if step.latest_run_id else None
            existing_run = (
                latest
                if latest is not None
                and latest.status == AgentRunStatus.QUEUED
                and latest.run_role == AgentRunRole.SPECIALIST
                else None
            )
            return await self._execute_step(
                plan=plan,
                step=step,
                snapshot=snapshot,
                trigger=trigger,
                matter_type=matter.primary_category.value,
                dependency_context=dependency_context,
                existing_run=existing_run,
            )

        step_results = await execute_plan_waves(
            plan,
            runner,
            initial_results=initial_results,
        )
        await self._persist_skipped_steps(plan.id, step_results)
        synthesis_run = next(
            (
                run
                for run in runs
                if run.run_role == AgentRunRole.BUTLER_SYNTHESIS
                and run.status == AgentRunStatus.QUEUED
                and run.id == plan.synthesis_run_id
            ),
            None,
        )
        return await self._synthesize(
            plan=plan,
            snapshot=snapshot,
            trigger=trigger,
            step_results=step_results,
            existing_run=synthesis_run,
        )

    async def _run_planning_phase(
        self,
        *,
        plan: AgentExecutionPlan,
        planning_run: AgentRun,
        snapshot: ContextSnapshot,
        trigger: LegalAgentTrigger,
    ) -> AgentExecutionPlan | None:
        planning_run, planning_lease = await self._claim_run(planning_run.id)
        planning_context = self._context_builder.planning(snapshot)
        planning_input = self._legal_input(
            run=planning_run,
            phase="planning",
            trigger=trigger,
            context=planning_context,
            upstream_outputs={},
            extra={
                "specialRequirements": trigger.special_requirements,
                "specialistOnly": trigger.specialist_only,
                "registeredSpecialists": sorted(LEGAL_SPECIALIST_KEYS),
            },
        )
        try:
            planning_execution = await self._runtime.execute(
                self._definitions["legal_butler"],
                planning_run,
                AgentExecutionContext(
                    snapshot=snapshot,
                    heartbeat=lambda: self._heartbeat(planning_run.id, planning_lease),
                    input_payload=planning_input,
                    authorized_source_refs=planning_context.source_refs,
                ),
            )
            if not isinstance(planning_execution.output, ButlerPlanningOutput):
                raise DomainValidationError("Butler planning returned the wrong output contract.")
            self._validate_planning_output(trigger, planning_execution.output)
        except (AgentRuntimeError, DomainValidationError) as exc:
            failure = self._runtime_failure(exc)
            await self._fail_run_and_plan(
                plan.id,
                planning_run.id,
                planning_lease,
                failure,
                input_payload=planning_input,
                working_directory=planning_run.working_directory,
            )
            return None
        planning_output = planning_execution.output
        plan = await self._accept_planning(
            plan_id=plan.id,
            run_id=planning_run.id,
            lease=planning_lease,
            output=planning_output,
            execution=planning_execution,
            run_input=planning_input,
            working_directory=planning_run.working_directory,
        )
        return plan

    async def rerun_step(
        self,
        *,
        plan_id: UUID,
        step_id: str,
        actor_id: str,
        correlation_id: str,
    ) -> LegalAgentOrchestrationResult:
        async with self._uow_factory() as uow:
            plan = await uow.agent_execution_plans.get(plan_id)
            if plan is None:
                raise EntityNotFoundError("Agent execution plan was not found.")
            step = next((value for value in plan.steps if value.step_id == step_id), None)
            if step is None:
                raise EntityNotFoundError("Agent plan step was not found.")
            snapshot_id = await self._snapshot_id_for_plan(uow, plan)
            snapshot = await uow.context_snapshots.get(snapshot_id)
            matter = await uow.matters.get(plan.matter_id)
            if snapshot is None or matter is None:
                raise EntityNotFoundError("Legal Agent rerun context was not found.")
        trigger = LegalAgentTrigger(
            matter_id=plan.matter_id,
            work_item_id=plan.work_item_id,
            context_snapshot_id=snapshot.id,
            objective=plan.objective,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key=f"rerun:{plan.id}:{step.id}:{uuid4().hex}",
        )
        persisted_results = await self._list_step_results(plan.id)
        dependency_context = self._dependency_assembler.build(
            step,
            self._dependency_results(
                {value.step_id: value for value in persisted_results}
            ),
        )
        step_result = await self._execute_step(
            plan=plan,
            step=step,
            snapshot=snapshot,
            trigger=trigger,
            matter_type=matter.primary_category.value,
            dependency_context=dependency_context,
            retry_of_run_id=step.latest_run_id,
        )
        all_results = await self._list_step_results(plan.id)
        by_step = {value.step_id: value for value in all_results}
        by_step[step_result.step_id] = step_result
        return await self._synthesize(
            plan=plan,
            snapshot=snapshot,
            trigger=trigger,
            step_results=list(by_step.values()),
        )

    async def _prepare_planning(
        self, trigger: LegalAgentTrigger
    ) -> tuple[AgentExecutionPlan, AgentRun, ContextSnapshot, str]:
        if trigger.specialist_only and trigger.specialist_only not in LEGAL_SPECIALIST_KEYS:
            raise DomainValidationError("Manual trigger requested an unregistered specialist.")
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation="legal_agent_orchestration", key=trigger.idempotency_key
            )
            existing = await uow.agent_execution_plans.get_by_idempotency_key(
                trigger.idempotency_key
            )
            if existing is not None:
                raise _ExistingPlanFound(existing)
            matter = await uow.matters.get(trigger.matter_id)
            snapshot = await uow.context_snapshots.get(trigger.context_snapshot_id)
            if matter is None or snapshot is None:
                raise EntityNotFoundError("Matter or ContextSnapshot was not found.")
            for definition in self._definitions.values():
                if await uow.agent_definitions.get(definition.id) is None:
                    await uow.agent_definitions.add(definition)
            await uow.flush()
            plan = AgentExecutionPlan(
                id=uuid4(),
                matter_id=trigger.matter_id,
                work_item_id=trigger.work_item_id,
                objective=trigger.objective,
                status=AgentExecutionPlanStatus.PLANNING,
                task_types=["pending_planning"],
                synthesis_strategy="Pending Butler planning.",
                missing_information=[],
                requires_user_input=False,
                correlation_id=trigger.correlation_id,
                idempotency_key=trigger.idempotency_key,
                created_by=trigger.actor_id,
            )
            await uow.agent_execution_plans.add(plan)
            await uow.flush()
            planning_run = self._new_run(
                definition_key="legal_butler",
                snapshot=snapshot,
                plan=plan,
                objective=trigger.objective,
                actor_id=trigger.actor_id,
                role=AgentRunRole.BUTLER_PLANNING,
            )
            await uow.agent_runs.add(planning_run)
            await uow.agent_run_sources.add_many(
                self._context_sources(planning_run.id, snapshot, None)
            )
            await uow.flush()
            plan.planning_run_id = planning_run.id
            await uow.agent_execution_plans.save(plan)
            await uow.commit()
        return plan, planning_run, snapshot, matter.primary_category.value

    async def _accept_planning(
        self,
        *,
        plan_id: UUID,
        run_id: UUID,
        lease: AgentAttemptLease,
        output: ButlerPlanningOutput,
        execution: AgentExecutionResult,
        run_input: dict[str, object],
        working_directory: str,
    ) -> AgentExecutionPlan:
        async with self._uow_factory() as uow:
            plan = await uow.agent_execution_plans.get_for_update(plan_id)
            run = await uow.agent_runs.get_for_update(run_id)
            if plan is None or run is None:
                raise EntityNotFoundError("Planning state was not found.")
            steps = [
                AgentPlanStep(
                    id=uuid4(),
                    execution_plan_id=plan.id,
                    step_id=value.step_id,
                    sequence=index,
                    agent_key=value.agent_key,
                    objective=value.objective,
                    depends_on=value.depends_on,
                    context_requirements=value.context_requirements,
                )
                for index, value in enumerate(output.steps, start=1)
            ]
            candidate = AgentExecutionPlan(
                id=plan.id,
                matter_id=plan.matter_id,
                work_item_id=plan.work_item_id,
                objective=output.objective,
                status=(
                    AgentExecutionPlanStatus.NEEDS_INFORMATION
                    if output.requires_user_input
                    else AgentExecutionPlanStatus.PLANNED
                ),
                task_types=output.task_types,
                synthesis_strategy=output.synthesis_strategy,
                missing_information=output.missing_information,
                requires_user_input=output.requires_user_input,
                correlation_id=plan.correlation_id,
                idempotency_key=plan.idempotency_key,
                created_by=plan.created_by,
                steps=steps,
                planning_run_id=run.id,
                created_at=plan.created_at,
                updated_at=utc_now(),
                version=plan.version + 1,
            )
            candidate.validate_steps(LEGAL_SPECIALIST_KEYS)
            await uow.agent_execution_plans.add_steps(steps)
            await self._apply_run_success(
                uow,
                run,
                execution,
                lease=lease,
                run_input=run_input,
                working_directory=working_directory,
                needs_information=output.requires_user_input,
            )
            plan.objective = candidate.objective
            plan.status = candidate.status
            plan.task_types = candidate.task_types
            plan.synthesis_strategy = candidate.synthesis_strategy
            plan.missing_information = candidate.missing_information
            plan.requires_user_input = candidate.requires_user_input
            plan.steps = steps
            plan.updated_at = candidate.updated_at
            plan.version = candidate.version
            await uow.agent_execution_plans.save(plan)
            await uow.commit()
        return candidate

    async def _execute_step(
        self,
        *,
        plan: AgentExecutionPlan,
        step: AgentPlanStep,
        snapshot: ContextSnapshot,
        trigger: LegalAgentTrigger,
        matter_type: str,
        dependency_context: DependencyContext,
        retry_of_run_id: UUID | None = None,
        existing_run: AgentRun | None = None,
    ) -> SpecialistStepExecution:
        run = existing_run or await self._start_step_run(
            plan=plan,
            step=step,
            snapshot=snapshot,
            trigger=trigger,
            retry_of_run_id=retry_of_run_id,
            dependency_run_ids=dependency_context.dependency_run_ids,
        )
        run, lease = await self._claim_run(run.id)
        context = await self._context_builder.specialist(
            snapshot=snapshot,
            agent_type=step.agent_key,
            matter_type=matter_type,
            objective=step.objective,
            jurisdiction=trigger.jurisdiction,
            effective_date=date.today(),
            correlation_id=trigger.correlation_id,
            agent_run_id=run.id,
            upstream_outputs=dependency_context.upstream_outputs,
        )
        context = AuthorizedLegalContext(
            payload=context.payload,
            source_refs=context.source_refs | dependency_context.source_refs,
            internal_precedent_refs=(
                context.internal_precedent_refs
                | dependency_context.internal_precedent_refs
            ),
            source_authorities={
                **dependency_context.source_authorities,
                **context.source_authorities,
            },
        )
        await self._add_context_sources(
            run.id,
            snapshot,
            context,
            dependency_run_ids=dependency_context.dependency_run_ids,
        )
        input_payload = self._legal_input(
            run=run,
            phase="specialist",
            trigger=trigger,
            context=context,
            upstream_outputs=dependency_context.upstream_outputs,
            extra={"stepId": step.step_id, "contextRequirements": step.context_requirements},
        )
        try:
            execution = await self._runtime.execute(
                self._definitions[step.agent_key],
                run,
                AgentExecutionContext(
                    snapshot=snapshot,
                    heartbeat=lambda: self._heartbeat(run.id, lease),
                    input_payload=input_payload,
                    authorized_source_refs=context.source_refs,
                    internal_precedent_refs=context.internal_precedent_refs,
                    source_authorities=context.source_authorities,
                ),
            )
            if not isinstance(execution.output, LegalWorkProduct):
                raise DomainValidationError("Specialist returned the wrong output contract.")
        except (AgentRuntimeError, DomainValidationError) as exc:
            failure = self._runtime_failure(exc)
            await self._fail_step(
                plan.id,
                step.step_id,
                run.id,
                lease,
                failure,
                run_input=input_payload,
                working_directory=run.working_directory,
            )
            return SpecialistStepExecution(
                step_id=step.step_id,
                agent_key=step.agent_key,
                run_id=run.id,
                status=AgentPlanStepStatus.FAILED,
                failure_code=failure.code,
                failure_message=str(failure),
                source_refs=context.source_refs,
                internal_precedent_refs=context.internal_precedent_refs,
                source_authorities=context.source_authorities,
            )
        product = execution.output
        needs_information = bool(product.missing_information)
        status = (
            AgentPlanStepStatus.NEEDS_INFORMATION
            if needs_information
            else AgentPlanStepStatus.COMPLETED
        )
        async with self._uow_factory() as uow:
            stored_run = await uow.agent_runs.get_for_update(run.id)
            stored_step = await uow.agent_execution_plans.get_step_for_update(
                plan.id, step.step_id
            )
            if stored_run is None or stored_step is None:
                raise EntityNotFoundError("Specialist persistence state was not found.")
            await self._apply_run_success(
                uow,
                stored_run,
                execution,
                lease=lease,
                run_input=input_payload,
                working_directory=run.working_directory,
                needs_information=needs_information,
            )
            stored_step.status = status
            stored_step.latest_valid_run_id = run.id
            stored_step.failure_code = None
            stored_step.failure_message = None
            stored_step.updated_at = utc_now()
            stored_step.version += 1
            await uow.agent_execution_plans.save_step(stored_step)
            await uow.commit()
        return SpecialistStepExecution(
            step_id=step.step_id,
            agent_key=step.agent_key,
            run_id=run.id,
            status=status,
            output=product,
            source_refs=context.source_refs,
            internal_precedent_refs=context.internal_precedent_refs,
            source_authorities=context.source_authorities,
        )

    async def _start_step_run(
        self,
        *,
        plan: AgentExecutionPlan,
        step: AgentPlanStep,
        snapshot: ContextSnapshot,
        trigger: LegalAgentTrigger,
        retry_of_run_id: UUID | None,
        dependency_run_ids: tuple[UUID, ...],
    ) -> AgentRun:
        async with self._uow_factory() as uow:
            stored_step = await uow.agent_execution_plans.get_step_for_update(
                plan.id, step.step_id
            )
            if stored_step is None:
                raise EntityNotFoundError("Agent plan step was not found.")
            run = self._new_run(
                definition_key=step.agent_key,
                snapshot=snapshot,
                plan=plan,
                objective=step.objective,
                actor_id=trigger.actor_id,
                role=AgentRunRole.SPECIALIST,
                step=stored_step,
                retry_of_run_id=retry_of_run_id,
                dependency_run_ids=dependency_run_ids,
            )
            await uow.agent_runs.add(run)
            await uow.flush()
            stored_step.status = AgentPlanStepStatus.RUNNING
            stored_step.latest_run_id = run.id
            stored_step.attempt_count += 1
            stored_step.updated_at = utc_now()
            stored_step.version += 1
            await uow.agent_execution_plans.save_step(stored_step)
            await uow.commit()
        return run

    async def _synthesize(
        self,
        *,
        plan: AgentExecutionPlan,
        snapshot: ContextSnapshot,
        trigger: LegalAgentTrigger,
        step_results: list[SpecialistStepExecution],
        existing_run: AgentRun | None = None,
    ) -> LegalAgentOrchestrationResult:
        synthesis_run = existing_run or await self._start_synthesis_run(
            plan, snapshot, trigger
        )
        synthesis_run, synthesis_lease = await self._claim_run(synthesis_run.id)
        source_refs = frozenset(
            value for result in step_results for value in result.source_refs
        )
        precedents = frozenset(
            value
            for result in step_results
            for value in result.internal_precedent_refs
        )
        source_authorities = {
            source_ref: metadata
            for result in step_results
            for source_ref, metadata in result.source_authorities.items()
        }
        context = AuthorizedLegalContext(
            payload={
                "contextSnapshot": self._context_builder.planning(snapshot).payload,
                "specialistFailures": [
                    {
                        "stepId": result.step_id,
                        "agentKey": result.agent_key,
                        "status": result.status.value,
                        "failureCode": result.failure_code,
                        "failureMessage": result.failure_message,
                    }
                    for result in step_results
                    if result.output is None
                ],
            },
            source_refs=source_refs
            | self._context_builder.planning(snapshot).source_refs,
            internal_precedent_refs=precedents,
            source_authorities=source_authorities,
        )
        upstream: dict[str, object] = {
            result.step_id: (
                result.output.model_dump(by_alias=True, mode="json")
                if result.output is not None
                else {
                    "agentKey": result.agent_key,
                    "status": result.status.value,
                    "failureCode": result.failure_code,
                    "failureMessage": result.failure_message,
                }
            )
            for result in step_results
        }
        input_payload = self._legal_input(
            run=synthesis_run,
            phase="synthesis",
            trigger=trigger,
            context=context,
            upstream_outputs=upstream,
            extra={
                "acceptedPlan": self._plan_payload(plan),
                "synthesisStrategy": plan.synthesis_strategy,
            },
        )
        try:
            execution = await self._runtime.execute(
                self._definitions["legal_butler"],
                synthesis_run,
                AgentExecutionContext(
                    snapshot=snapshot,
                    heartbeat=lambda: self._heartbeat(
                        synthesis_run.id, synthesis_lease
                    ),
                    input_payload=input_payload,
                    authorized_source_refs=context.source_refs,
                    internal_precedent_refs=context.internal_precedent_refs,
                    source_authorities=context.source_authorities,
                ),
            )
            if not isinstance(execution.output, ButlerSynthesisOutput):
                raise DomainValidationError("Butler synthesis returned the wrong contract.")
        except (AgentRuntimeError, DomainValidationError) as exc:
            failure = self._runtime_failure(exc)
            await self._fail_run_and_plan(
                plan.id,
                synthesis_run.id,
                synthesis_lease,
                failure,
                input_payload=input_payload,
                working_directory=synthesis_run.working_directory,
                partial=any(result.output is not None for result in step_results),
            )
            return LegalAgentOrchestrationResult(
                plan_id=plan.id,
                status=(
                    AgentExecutionPlanStatus.PARTIAL
                    if any(result.output is not None for result in step_results)
                    else AgentExecutionPlanStatus.FAILED
                ),
                planning_run_id=plan.planning_run_id,
                synthesis_run_id=synthesis_run.id,
                artifact_id=None,
                review_package_id=None,
                step_results=tuple(step_results),
            )
        output = execution.output
        any_failed = any(
            result.status in {AgentPlanStepStatus.FAILED, AgentPlanStepStatus.SKIPPED}
            for result in step_results
        )
        needs_information = bool(output.missing_information) or any(
            result.status == AgentPlanStepStatus.NEEDS_INFORMATION
            for result in step_results
        )
        final_status = (
            AgentExecutionPlanStatus.PARTIAL
            if any_failed
            else (
                AgentExecutionPlanStatus.NEEDS_INFORMATION
                if needs_information
                else AgentExecutionPlanStatus.COMPLETED
            )
        )
        artifact = DraftArtifact(
            id=uuid4(),
            agent_run_id=synthesis_run.id,
            artifact_type="legal_butler_synthesis",
            title=f"法务管家综合意见: {plan.objective}",
            content=output.draft_response,
            structured_payload=output.model_dump(by_alias=True, mode="json"),
        )
        review = ReviewPackage.create(
            matter_id=plan.matter_id,
            work_item_id=plan.work_item_id,
            package_type=ReviewPackageType.LEGAL_ANALYSIS,
            title=artifact.title,
            background=output.matter_assessment,
            confirmed_facts=[
                value.model_dump(by_alias=True, mode="json") for value in output.core_facts
            ],
            unconfirmed_facts=[
                {"missingInformation": value} for value in output.missing_information
            ],
            reasoning="\n".join(
                f"{value.action}: {value.rationale}"
                for value in output.recommended_strategy
            )
            or "Butler synthesis is available in the structured payload.",
            risks=[
                value.model_dump(by_alias=True, mode="json")
                for value in output.integrated_risks
            ],
            alternatives=[
                {"conflict": value.model_dump(by_alias=True, mode="json")}
                for value in output.conflicts
            ],
            citations=[value.model_dump(by_alias=True, mode="json") for value in output.citations],
            proposed_content=output.draft_response,
            target={"channel": "internal", "matterId": str(plan.matter_id)},
            created_by=trigger.actor_id,
            grounding_payload={
                "coreFacts": [
                    value.model_dump(by_alias=True, mode="json")
                    for value in output.core_facts
                ],
                "keyLegalIssues": [
                    value.model_dump(by_alias=True, mode="json")
                    for value in output.key_legal_issues
                ],
                "integratedRisks": [
                    value.model_dump(by_alias=True, mode="json")
                    for value in output.integrated_risks
                ],
                "recommendedStrategy": [
                    value.model_dump(by_alias=True, mode="json")
                    for value in output.recommended_strategy
                ],
                "nextActions": [
                    value.model_dump(by_alias=True, mode="json")
                    for value in output.next_actions
                ],
                "conflicts": [
                    value.model_dump(by_alias=True, mode="json")
                    for value in output.conflicts
                ],
            },
        )
        review.submit(expected_version=review.version)
        async with self._uow_factory() as uow:
            stored_run = await uow.agent_runs.get_for_update(synthesis_run.id)
            stored_plan = await uow.agent_execution_plans.get_for_update(plan.id)
            if stored_run is None or stored_plan is None:
                raise EntityNotFoundError("Synthesis persistence state was not found.")
            await self._apply_run_success(
                uow,
                stored_run,
                execution,
                lease=synthesis_lease,
                run_input=input_payload,
                working_directory=synthesis_run.working_directory,
                needs_information=needs_information,
            )
            stored_plan.status = final_status
            stored_plan.synthesis_run_id = synthesis_run.id
            stored_plan.updated_at = utc_now()
            stored_plan.version += 1
            await uow.agent_execution_plans.save(stored_plan)
            await uow.draft_artifacts.add(artifact)
            await uow.review_packages.add(review)
            await uow.commit()
        return LegalAgentOrchestrationResult(
            plan_id=plan.id,
            status=final_status,
            planning_run_id=plan.planning_run_id,
            synthesis_run_id=synthesis_run.id,
            artifact_id=artifact.id,
            review_package_id=review.id,
            step_results=tuple(step_results),
        )

    async def _start_synthesis_run(
        self,
        plan: AgentExecutionPlan,
        snapshot: ContextSnapshot,
        trigger: LegalAgentTrigger,
    ) -> AgentRun:
        async with self._uow_factory() as uow:
            run = self._new_run(
                definition_key="legal_butler",
                snapshot=snapshot,
                plan=plan,
                objective=f"综合执行计划 {plan.id} 的专业意见",
                actor_id=trigger.actor_id,
                role=AgentRunRole.BUTLER_SYNTHESIS,
            )
            await uow.agent_runs.add(run)
            await uow.flush()
            await uow.agent_run_sources.add_many(
                self._context_sources(run.id, snapshot, None)
            )
            stored_plan = await uow.agent_execution_plans.get_for_update(plan.id)
            if stored_plan is None:
                raise EntityNotFoundError("Agent execution plan was not found.")
            stored_plan.status = AgentExecutionPlanStatus.RUNNING
            stored_plan.synthesis_run_id = run.id
            stored_plan.updated_at = utc_now()
            stored_plan.version += 1
            await uow.agent_execution_plans.save(stored_plan)
            await uow.commit()
        return run

    async def _apply_run_success(
        self,
        uow: Any,
        run: AgentRun,
        execution: AgentExecutionResult,
        *,
        lease: AgentAttemptLease,
        run_input: dict[str, object],
        working_directory: str,
        needs_information: bool,
    ) -> None:
        await AgentExecutionLeaseService(
            uow.agent_run_attempts,
            lease_seconds=self._lease_seconds,
        ).complete(run, lease)
        run.input_payload = run_input
        run.output_payload = execution.output.model_dump(by_alias=True, mode="json")
        run.raw_stdout = execution.raw_stdout
        run.raw_stderr = execution.raw_stderr
        run.working_directory = working_directory
        run.runtime_version = execution.runtime_version
        run.validation_errors = list(execution.validation_errors)
        run.repair_attempted = execution.repair_attempted
        run.token_usage = execution.token_usage
        run.transition_to(AgentRunStatus.VALIDATING)
        run.transition_to(
            AgentRunStatus.NEEDS_MORE_INFORMATION
            if needs_information
            else AgentRunStatus.COMPLETED
        )
        await uow.agent_runs.save(run)

    async def _fail_step(
        self,
        plan_id: UUID,
        step_id: str,
        run_id: UUID,
        lease: AgentAttemptLease,
        error: AgentRuntimeError,
        *,
        run_input: dict[str, object],
        working_directory: str,
    ) -> None:
        async with self._uow_factory() as uow:
            run = await uow.agent_runs.get_for_update(run_id)
            step = await uow.agent_execution_plans.get_step_for_update(plan_id, step_id)
            if run is None or step is None:
                raise EntityNotFoundError("Failed specialist state was not found.")
            await self._apply_attempt_failure(uow, run, lease, error)
            self._apply_run_failure(run, error, run_input, working_directory)
            retry_queued = await self._queue_retry_or_dead_letter(uow, run, error)
            await uow.agent_runs.save(run)
            step.status = (
                AgentPlanStepStatus.RUNNING
                if retry_queued
                else AgentPlanStepStatus.FAILED
            )
            step.failure_code = error.code
            step.failure_message = str(error)
            step.updated_at = utc_now()
            step.version += 1
            await uow.agent_execution_plans.save_step(step)
            await uow.commit()

    async def _fail_run_and_plan(
        self,
        plan_id: UUID,
        run_id: UUID,
        lease: AgentAttemptLease,
        error: AgentRuntimeError,
        *,
        input_payload: dict[str, object],
        working_directory: str,
        partial: bool = False,
    ) -> None:
        async with self._uow_factory() as uow:
            run = await uow.agent_runs.get_for_update(run_id)
            plan = await uow.agent_execution_plans.get_for_update(plan_id)
            if run is None or plan is None:
                raise EntityNotFoundError("Failed Agent state was not found.")
            await self._apply_attempt_failure(uow, run, lease, error)
            self._apply_run_failure(run, error, input_payload, working_directory)
            retry_queued = await self._queue_retry_or_dead_letter(uow, run, error)
            await uow.agent_runs.save(run)
            if not retry_queued:
                plan.status = (
                    AgentExecutionPlanStatus.PARTIAL
                    if partial
                    else AgentExecutionPlanStatus.FAILED
                )
            plan.updated_at = utc_now()
            plan.version += 1
            await uow.agent_execution_plans.save(plan)
            await uow.commit()

    @staticmethod
    def _apply_run_failure(
        run: AgentRun,
        error: AgentRuntimeError,
        input_payload: dict[str, object],
        working_directory: str,
    ) -> None:
        run.input_payload = input_payload
        run.working_directory = working_directory
        run.raw_stdout = error.raw_stdout
        run.raw_stderr = error.raw_stderr
        run.validation_errors = list(error.validation_errors)
        run.repair_attempted = error.repair_attempted
        run.failure_code = error.code
        run.failure_message = str(error)
        run.transition_to(AgentRunStatus.FAILED)

    async def _apply_attempt_failure(
        self,
        uow: Any,
        run: AgentRun,
        lease: AgentAttemptLease,
        error: AgentRuntimeError,
    ) -> None:
        attempt_status = {
            "AGENT_RUNTIME_TIMEOUT": AgentAttemptStatus.TIMED_OUT,
            "AGENT_RUNTIME_CANCELLED": AgentAttemptStatus.CANCELLED,
        }.get(error.code, AgentAttemptStatus.FAILED)
        await AgentExecutionLeaseService(
            uow.agent_run_attempts,
            lease_seconds=self._lease_seconds,
        ).fail(
            run,
            lease,
            status=attempt_status,
            failure_code=error.code,
            failure_message=str(error)[:4000],
        )

    async def _queue_retry_or_dead_letter(
        self,
        uow: Any,
        run: AgentRun,
        error: AgentRuntimeError,
    ) -> bool:
        if error.retryable and run.attempt_number < run.max_attempts:
            run.attempt_number += 1
            run.transition_to(AgentRunStatus.QUEUED)
            run.finished_at = None
            run.worker_id = None
            run.failure_code = None
            run.failure_message = None
            if run.execution_plan_id is not None and not await uow.outbox_events.exists_pending(
                event_type="LegalAgentRecoveryRequested",
                aggregate_id=run.execution_plan_id,
            ):
                await uow.outbox_events.add(
                    OutboxEvent(
                        id=uuid4(),
                        event_type="LegalAgentRecoveryRequested",
                        aggregate_type="agent_execution_plan",
                        aggregate_id=run.execution_plan_id,
                        payload={
                            "planId": str(run.execution_plan_id),
                            "runId": str(run.id),
                            "runRole": run.run_role.value,
                            "recoveryReason": "retryable_runtime_failure",
                        },
                        correlation_id=run.correlation_id,
                    )
                )
            return True
        if run.status == AgentRunStatus.FAILED:
            run.transition_to(AgentRunStatus.DEAD_LETTER)
        return False

    async def _persist_skipped_steps(
        self, plan_id: UUID, results: list[SpecialistStepExecution]
    ) -> None:
        skipped = [value for value in results if value.status == AgentPlanStepStatus.SKIPPED]
        if not skipped:
            return
        async with self._uow_factory() as uow:
            for result in skipped:
                step = await uow.agent_execution_plans.get_step_for_update(
                    plan_id, result.step_id
                )
                if step is None:
                    continue
                step.status = AgentPlanStepStatus.SKIPPED
                step.failure_code = result.failure_code
                step.failure_message = result.failure_message
                step.updated_at = utc_now()
                step.version += 1
                await uow.agent_execution_plans.save_step(step)
            await uow.commit()

    async def _add_context_sources(
        self,
        run_id: UUID,
        snapshot: ContextSnapshot,
        context: AuthorizedLegalContext,
        *,
        dependency_run_ids: tuple[UUID, ...] = (),
    ) -> None:
        async with self._uow_factory() as uow:
            sources = self._context_sources(run_id, snapshot, context)
            existing_keys = {
                (value.source_type, value.source_id, value.source_hash)
                for value in await uow.agent_run_sources.list_by_run(run_id)
            }
            sources = [
                value
                for value in sources
                if (value.source_type, value.source_id, value.source_hash)
                not in existing_keys
            ]
            existing_keys.update(
                (value.source_type, value.source_id, value.source_hash) for value in sources
            )
            for dependency_run_id in dependency_run_ids:
                for source in await uow.agent_run_sources.list_by_run(dependency_run_id):
                    key = (source.source_type, source.source_id, source.source_hash)
                    if key in existing_keys:
                        continue
                    existing_keys.add(key)
                    sources.append(
                        AgentRunSource(
                            id=uuid4(),
                            agent_run_id=run_id,
                            source_type=source.source_type,
                            source_id=source.source_id,
                            source_version=source.source_version,
                            source_hash=source.source_hash,
                            display_name=source.display_name,
                            citation_metadata=source.citation_metadata,
                        )
                    )
            await uow.agent_run_sources.add_many(sources)
            await uow.commit()

    async def _claim_run(self, run_id: UUID) -> tuple[AgentRun, AgentAttemptLease]:
        async with self._uow_factory() as uow:
            run = await uow.agent_runs.get_for_update(run_id)
            if run is None:
                raise EntityNotFoundError("Agent run was not found before lease claim.")
            lease = await AgentExecutionLeaseService(
                uow.agent_run_attempts,
                lease_seconds=self._lease_seconds,
            ).start(run, worker_id=self._worker_id)
            await uow.agent_runs.save(run)
            await uow.commit()
        return run, lease

    async def _heartbeat(self, run_id: UUID, lease: AgentAttemptLease) -> None:
        async with self._uow_factory() as uow:
            run = await uow.agent_runs.get_for_update(run_id)
            if run is None:
                raise EntityNotFoundError("Agent run was not found during heartbeat.")
            await AgentExecutionLeaseService(
                uow.agent_run_attempts,
                lease_seconds=self._lease_seconds,
            ).heartbeat(run, lease)
            await uow.agent_runs.save(run)
            await uow.commit()

    def _context_sources(
        self,
        run_id: UUID,
        snapshot: ContextSnapshot,
        context: AuthorizedLegalContext | None,
    ) -> list[AgentRunSource]:
        values = [
            AgentRunSource(
                id=uuid4(),
                agent_run_id=run_id,
                source_type=AgentRunSourceType.CONTEXT_SNAPSHOT,
                source_id=str(snapshot.id),
                source_version=str(snapshot.snapshot_version),
                source_hash=snapshot.content_hash,
                display_name="Authorized ContextSnapshot",
                citation_metadata={"sourceRef": f"ctx:snapshot:{snapshot.id}"},
            )
        ]
        if context is None:
            return values
        retrieval = context.payload.get("retrievalResults", [])
        if not isinstance(retrieval, list):
            return values
        for item in retrieval:
            if not isinstance(item, dict):
                continue
            source_ref = str(item.get("sourceRef") or "")
            source_hash = str(item.get("textHash") or "")
            if not source_ref or len(source_hash) != 64:
                continue
            values.append(
                AgentRunSource(
                    id=uuid4(),
                    agent_run_id=run_id,
                    source_type=AgentRunSourceType.KNOWLEDGE_DOCUMENT,
                    source_id=source_ref,
                    source_version=None,
                    source_hash=source_hash,
                    display_name=str(item.get("title") or source_ref),
                    citation_metadata={
                        "sourceRef": source_ref,
                        "locator": item.get("locator"),
                        "internalPrecedent": item.get("internalPrecedent", False),
                        "authorityType": item.get("authorityType"),
                        "authorityRole": item.get("authorityRole"),
                        "authorityStatus": item.get("authorityStatus"),
                        "metadataStatus": item.get("metadataStatus"),
                        "jurisdiction": item.get("jurisdiction"),
                        "effectiveFrom": item.get("effectiveFrom"),
                        "effectiveTo": item.get("effectiveTo"),
                    },
                )
            )
        return values

    def _new_run(
        self,
        *,
        definition_key: str,
        snapshot: ContextSnapshot,
        plan: AgentExecutionPlan,
        objective: str,
        actor_id: str,
        role: AgentRunRole,
        step: AgentPlanStep | None = None,
        retry_of_run_id: UUID | None = None,
        dependency_run_ids: tuple[UUID, ...] = (),
    ) -> AgentRun:
        definition = self._definitions[definition_key]
        return AgentRun(
            id=uuid4(),
            agent_definition_id=definition.id,
            context_snapshot_id=snapshot.id,
            status=AgentRunStatus.QUEUED,
            objective=objective,
            prompt_snapshot=definition.prompt_template,
            working_directory=str(self._runs_root / "pending"),
            attempt_number=1,
            max_attempts=definition.max_retries + 1,
            correlation_id=plan.correlation_id,
            created_by=actor_id,
            matter_id=plan.matter_id,
            work_item_id=plan.work_item_id,
            execution_plan_id=plan.id,
            plan_step_id=step.id if step else None,
            parent_run_id=plan.planning_run_id if role != AgentRunRole.BUTLER_PLANNING else None,
            retry_of_run_id=retry_of_run_id,
            run_role=role,
            dependency_run_ids=list(dependency_run_ids),
            agent_definition_version=definition.version,
            prompt_version=definition.version,
        )

    @staticmethod
    def _legal_input(
        *,
        run: AgentRun,
        phase: str,
        trigger: LegalAgentTrigger,
        context: AuthorizedLegalContext,
        upstream_outputs: dict[str, object],
        extra: dict[str, object],
    ) -> dict[str, object]:
        authorized_context = dict(context.payload)
        authorized_context.update(extra)
        return {
            "runId": str(run.id),
            "phase": phase,
            "objective": run.objective,
            "matterId": str(trigger.matter_id),
            "workItemId": str(trigger.work_item_id) if trigger.work_item_id else None,
            "authorizedContext": authorized_context,
            "authorizedSourceRefs": sorted(context.source_refs),
            "upstreamOutputs": upstream_outputs,
            "constraints": {
                "networkAccess": False,
                "databaseAccess": False,
                "repositoryAccess": False,
                "shellAccess": False,
                "agentDispatchAccess": False,
                "externalMessagingAccess": False,
            },
        }

    @staticmethod
    def _plan_payload(plan: AgentExecutionPlan) -> dict[str, object]:
        return {
            "id": str(plan.id),
            "objective": plan.objective,
            "taskTypes": plan.task_types,
            "steps": [
                {
                    "stepId": step.step_id,
                    "agentKey": step.agent_key,
                    "objective": step.objective,
                    "dependsOn": step.depends_on,
                    "contextRequirements": step.context_requirements,
                }
                for step in plan.steps
            ],
        }

    async def _get_existing(self, key: str) -> AgentExecutionPlan | None:
        async with self._uow_factory() as uow:
            return await uow.agent_execution_plans.get_by_idempotency_key(key)

    async def _list_step_results(self, plan_id: UUID) -> list[SpecialistStepExecution]:
        async with self._uow_factory() as uow:
            plan = await uow.agent_execution_plans.get(plan_id)
            runs = list(await uow.agent_runs.list_by_plan(plan_id))
            sources_by_run = {
                run.id: list(await uow.agent_run_sources.list_by_run(run.id))
                for run in runs
            }
        if plan is None:
            return []
        by_id = {run.id: run for run in runs}
        values: list[SpecialistStepExecution] = []
        for step in plan.steps:
            selected_run_id = (
                step.latest_valid_run_id
                if step.status
                in {
                    AgentPlanStepStatus.COMPLETED,
                    AgentPlanStepStatus.NEEDS_INFORMATION,
                }
                else step.latest_run_id
            )
            run = by_id.get(selected_run_id) if selected_run_id else None
            output: LegalWorkProduct | None = None
            if (
                run
                and run.output_payload
                and run.status
                in {
                    AgentRunStatus.COMPLETED,
                    AgentRunStatus.NEEDS_MORE_INFORMATION,
                }
                and step.status
                in {
                    AgentPlanStepStatus.COMPLETED,
                    AgentPlanStepStatus.NEEDS_INFORMATION,
                }
            ):
                output = LEGAL_OUTPUT_MODELS[step.agent_key].model_validate(
                    run.output_payload
                )
            run_sources = sources_by_run.get(run.id, []) if run else []
            source_refs = frozenset(
                str(source.citation_metadata.get("sourceRef"))
                for source in run_sources
                if source.citation_metadata.get("sourceRef")
            )
            internal_precedent_refs = frozenset(
                str(source.citation_metadata.get("sourceRef"))
                for source in run_sources
                if source.citation_metadata.get("sourceRef")
                and source.citation_metadata.get("internalPrecedent") is True
            )
            source_authorities = {
                str(source.citation_metadata["sourceRef"]): {
                    key: source.citation_metadata.get(key)
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
                for source in run_sources
                if source.citation_metadata.get("sourceRef")
                and source.citation_metadata.get("authorityType")
            }
            values.append(
                SpecialistStepExecution(
                    step_id=step.step_id,
                    agent_key=step.agent_key,
                    run_id=run.id if run is not None else step.latest_run_id,
                    status=step.status,
                    output=output,
                    failure_code=step.failure_code,
                    failure_message=step.failure_message,
                    source_refs=source_refs,
                    internal_precedent_refs=internal_precedent_refs,
                    source_authorities=source_authorities,
                )
            )
        return values

    @staticmethod
    def _dependency_results(
        results: dict[str, SpecialistStepExecution],
    ) -> dict[str, DependencyResult]:
        return {
            step_id: DependencyResult(
                step_id=value.step_id,
                run_id=value.run_id,
                status=value.status,
                output_payload=(
                    value.output.model_dump(by_alias=True, mode="json")
                    if value.output is not None
                    else None
                ),
                source_refs=value.source_refs,
                internal_precedent_refs=value.internal_precedent_refs,
                source_authorities=value.source_authorities,
            )
            for step_id, value in results.items()
        }

    async def _snapshot_id_for_plan(self, uow: Any, plan: AgentExecutionPlan) -> UUID:
        if plan.planning_run_id is None:
            raise EntityNotFoundError("Plan has no Butler planning run.")
        run = await uow.agent_runs.get(plan.planning_run_id)
        if run is None:
            raise EntityNotFoundError("Butler planning run was not found.")
        return UUID(str(run.context_snapshot_id))

    async def _replay_result(
        self, plan: AgentExecutionPlan
    ) -> LegalAgentOrchestrationResult:
        runs = await self._list_step_results(plan.id)
        return LegalAgentOrchestrationResult(
            plan_id=plan.id,
            status=plan.status,
            planning_run_id=plan.planning_run_id,
            synthesis_run_id=plan.synthesis_run_id,
            artifact_id=None,
            review_package_id=None,
            step_results=tuple(runs),
            idempotent_replay=True,
        )

    @staticmethod
    def _validate_planning_output(
        trigger: LegalAgentTrigger, output: ButlerPlanningOutput
    ) -> None:
        if output.matter_id not in {None, str(trigger.matter_id)}:
            raise DomainValidationError("Butler planning changed the authorized matter ID.")
        expected_work_item = str(trigger.work_item_id) if trigger.work_item_id else None
        if output.work_item_id != expected_work_item:
            raise DomainValidationError("Butler planning changed the authorized WorkItem ID.")
        if trigger.specialist_only and (
            len(output.steps) != 1
            or output.steps[0].agent_key != trigger.specialist_only
        ):
            raise DomainValidationError(
                "Butler planning did not honor the deterministic specialist-only request."
            )

    @staticmethod
    def _runtime_failure(error: AgentRuntimeError | DomainValidationError) -> AgentRuntimeError:
        if isinstance(error, AgentRuntimeError):
            return error
        return AgentRuntimeError(
            "AGENT_OUTPUT_CONTRACT_INVALID",
            str(error),
            retryable=False,
            validation_errors=(str(error),),
        )

    @staticmethod
    def _failed_result(
        plan: AgentExecutionPlan, planning_run_id: UUID
    ) -> LegalAgentOrchestrationResult:
        return LegalAgentOrchestrationResult(
            plan_id=plan.id,
            status=plan.status,
            planning_run_id=planning_run_id,
            synthesis_run_id=None,
            artifact_id=None,
            review_package_id=None,
            step_results=(),
        )
