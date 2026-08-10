import re
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from legal_workbench.api.auth import RequestActor
from legal_workbench.api.dependencies import (
    get_correlation_id,
    get_idempotency_key,
    get_request_actor,
    get_uow_factory,
)
from legal_workbench.api.schemas.agents import (
    AgentExecutionPlanResponse,
    AgentPlanStepResponse,
    AgentRunOperationResponse,
    AgentRunResponse,
    AgentRunSourceResponse,
    AgentRunStatusEventResponse,
    ContextSnapshotSummaryResponse,
    FeishuMessageSourceResponse,
    LegalAgentRequest,
    LegalAgentRequestAcceptedResponse,
    LegalAgentStepRerunAcceptedResponse,
    MessageAnalysisRequestedResponse,
    MessageAnalysisResponse,
)
from legal_workbench.application.agent_operations import (
    CancelAgentRunCommand,
    CancelAgentRunHandler,
)
from legal_workbench.application.legal_agent_requests import (
    RequestLegalAgentOrchestrationCommand,
    RequestLegalAgentOrchestrationHandler,
    RequestLegalAgentStepRerunCommand,
    RequestLegalAgentStepRerunHandler,
)
from legal_workbench.application.message_analysis import (
    RequestFeishuMessageAnalysisCommand,
    RequestFeishuMessageAnalysisHandler,
)
from legal_workbench.application.queries import (
    AgentRunDetails,
    AgentRunQueryService,
    FeishuMessageAnalysisDetails,
    FeishuMessageAnalysisQueryService,
)
from legal_workbench.domain.entities import AgentExecutionPlan
from legal_workbench.domain.enums import AgentRunStatus, FeishuMessageStatus
from legal_workbench.domain.errors import EntityNotFoundError
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(tags=["agent-runs"])

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s\"']+"),
    re.compile(r"(?i)((?:api|access|secret)[_-]?key\s*[:=]\s*)[^\s\"']+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def _redact_runtime_text(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda match: f"{match.group(1) if match.lastindex else ''}[REDACTED]",
            redacted,
        )
    return redacted


def _run_response(details: AgentRunDetails) -> AgentRunResponse:
    run = details.run
    return AgentRunResponse(
        id=run.id,
        agent_key=details.definition.key,
        agent_version=details.definition.version,
        feishu_message_id=run.feishu_message_id,
        context_snapshot_id=run.context_snapshot_id,
        status=run.status,
        objective=run.objective,
        input_payload=run.input_payload,
        output_payload=run.output_payload,
        raw_stdout=_redact_runtime_text(run.raw_stdout),
        raw_stderr=_redact_runtime_text(run.raw_stderr),
        prompt_snapshot=run.prompt_snapshot,
        working_directory=f"[runtime]/{Path(run.working_directory).name}",
        started_at=run.started_at,
        heartbeat_at=run.heartbeat_at,
        finished_at=run.finished_at,
        timeout_at=run.timeout_at,
        attempt_number=run.attempt_number,
        max_attempts=run.max_attempts,
        failure_code=run.failure_code,
        failure_message=run.failure_message,
        runtime_version=run.runtime_version,
        agent_definition_version=run.agent_definition_version,
        prompt_version=run.prompt_version,
        validation_errors=run.validation_errors,
        repair_attempted=run.repair_attempted,
        token_usage=run.token_usage,
        worker_id=run.worker_id,
        lease_expires_at=run.lease_expires_at,
        correlation_id=run.correlation_id,
        created_by=run.created_by,
        created_at=run.created_at,
        updated_at=run.updated_at,
        version=run.version,
        sources=[AgentRunSourceResponse.model_validate(source) for source in details.sources],
        status_events=[
            AgentRunStatusEventResponse.model_validate(value) for value in details.status_events
        ],
        candidate_id=details.candidate.id if details.candidate else None,
        matter_id=run.matter_id,
        work_item_id=run.work_item_id,
        execution_plan_id=run.execution_plan_id,
        plan_step_id=run.plan_step_id,
        parent_run_id=run.parent_run_id,
        retry_of_run_id=run.retry_of_run_id,
        dependency_run_ids=run.dependency_run_ids,
        run_role=run.run_role,
    )


async def _plan_response(
    plan: AgentExecutionPlan,
    uow_factory: SqlAlchemyUnitOfWorkFactory,
) -> AgentExecutionPlanResponse:
    execution_plan = plan
    async with uow_factory() as uow:
        runs = list(await uow.agent_runs.list_by_plan(execution_plan.id))
    run_query = AgentRunQueryService(uow_factory)
    run_responses = [_run_response(await run_query.get(run.id)) for run in runs]
    return AgentExecutionPlanResponse(
        id=execution_plan.id,
        matter_id=execution_plan.matter_id,
        work_item_id=execution_plan.work_item_id,
        objective=execution_plan.objective,
        status=execution_plan.status,
        task_types=execution_plan.task_types,
        synthesis_strategy=execution_plan.synthesis_strategy,
        missing_information=execution_plan.missing_information,
        requires_user_input=execution_plan.requires_user_input,
        correlation_id=execution_plan.correlation_id,
        analysis_effective_date=execution_plan.analysis_effective_date,
        historical_as_of=execution_plan.historical_as_of,
        planning_run_id=execution_plan.planning_run_id,
        synthesis_run_id=execution_plan.synthesis_run_id,
        steps=[AgentPlanStepResponse.model_validate(step) for step in execution_plan.steps],
        agent_runs=run_responses,
        created_at=execution_plan.created_at,
        updated_at=execution_plan.updated_at,
    )


@router.post(
    "/matters/{matter_id}/legal-agent-plans",
    response_model=LegalAgentRequestAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_legal_agent_plan(
    matter_id: UUID,
    body: LegalAgentRequest,
    request: Request,
    response: Response,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> LegalAgentRequestAcceptedResponse:
    result = await RequestLegalAgentOrchestrationHandler(uow_factory).execute(
        RequestLegalAgentOrchestrationCommand(
            matter_id=matter_id,
            work_item_id=body.work_item_id,
            context_snapshot_id=body.context_snapshot_id,
            objective=body.objective,
            special_requirements=body.special_requirements,
            specialist_only=body.specialist_only,
            jurisdiction=body.jurisdiction,
            historical_as_of=body.historical_as_of,
            actor_id=actor.actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return LegalAgentRequestAcceptedResponse(
        request_id=result.request_id,
        matter_id=result.matter_id,
        context_snapshot_id=result.context_snapshot_id,
        idempotent_replay=result.idempotent_replay,
    )


@router.get(
    "/matters/{matter_id}/legal-agent-plans",
    response_model=list[AgentExecutionPlanResponse],
)
async def list_legal_agent_plans(
    matter_id: UUID,
    _: Annotated[RequestActor, Depends(get_request_actor)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[AgentExecutionPlanResponse]:
    async with uow_factory() as uow:
        if await uow.matters.get(matter_id) is None:
            raise EntityNotFoundError("Legal matter was not found.")
        plans = list(await uow.agent_execution_plans.list_by_matter(matter_id, limit=limit))
    return [await _plan_response(plan, uow_factory) for plan in plans]


@router.get(
    "/legal-agent-plans/{plan_id}",
    response_model=AgentExecutionPlanResponse,
)
async def get_legal_agent_plan(
    plan_id: UUID,
    _: Annotated[RequestActor, Depends(get_request_actor)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> AgentExecutionPlanResponse:
    async with uow_factory() as uow:
        plan = await uow.agent_execution_plans.get(plan_id)
    if plan is None:
        raise EntityNotFoundError("Agent execution plan was not found.")
    return await _plan_response(plan, uow_factory)


@router.post(
    "/legal-agent-plans/{plan_id}/steps/{step_id}/rerun",
    response_model=LegalAgentStepRerunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_legal_agent_step_rerun(
    plan_id: UUID,
    step_id: str,
    request: Request,
    response: Response,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> LegalAgentStepRerunAcceptedResponse:
    result = await RequestLegalAgentStepRerunHandler(uow_factory).execute(
        RequestLegalAgentStepRerunCommand(
            plan_id=plan_id,
            step_id=step_id,
            actor_id=actor.actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return LegalAgentStepRerunAcceptedResponse(
        request_id=result.request_id,
        plan_id=result.plan_id,
        step_id=result.step_id,
        idempotent_replay=result.idempotent_replay,
    )


def _analysis_response(details: FeishuMessageAnalysisDetails) -> MessageAnalysisResponse:
    snapshot = details.snapshot
    run_details = (
        AgentRunDetails(
            run=details.run,
            definition=details.definition,
            sources=details.sources,
        )
        if details.run is not None and details.definition is not None
        else None
    )
    retryable_statuses = {
        FeishuMessageStatus.ANALYSIS_FAILED,
        FeishuMessageStatus.DEAD_LETTER,
        FeishuMessageStatus.CANDIDATE_CREATED,
        FeishuMessageStatus.IGNORED,
    }
    return MessageAnalysisResponse(
        message=FeishuMessageSourceResponse(
            id=details.message.id,
            message_id=details.message.message_id,
            sender_id=details.message.sender_id,
            message_type=details.message.message_type,
            content=details.message.content,
            create_time=details.message.create_time,
        ),
        message_status=details.message.status,
        context_snapshot=(
            ContextSnapshotSummaryResponse(
                id=snapshot.id,
                snapshot_version=snapshot.snapshot_version,
                message_ids=snapshot.message_ids,
                attachment_ids=snapshot.attachment_ids,
                included_segments=snapshot.included_segments,
                excluded_segments=snapshot.excluded_segments,
                participant_ids=snapshot.participant_ids,
                content_hash=snapshot.content_hash,
                truncated=bool(snapshot.content.get("truncated", False)),
                truncation_reason=snapshot.truncation_reason,
                original_size=snapshot.original_size,
                included_size=snapshot.included_size,
                builder_version=snapshot.builder_version,
                selection_policy_version=snapshot.selection_policy_version,
                created_at=snapshot.created_at,
            )
            if snapshot
            else None
        ),
        agent_run=_run_response(run_details) if run_details else None,
        analysis_result=details.run.output_payload if details.run else None,
        candidate_id=details.candidate.id if details.candidate else None,
        failure_code=(details.run.failure_code if details.run else details.message.failure_code),
        failure_message=(
            details.run.failure_message if details.run else details.message.failure_message
        ),
        can_retry=details.message.status in retryable_statuses,
    )


@router.get("/agent-runs", response_model=list[AgentRunResponse])
async def list_agent_runs(
    _: Annotated[RequestActor, Depends(get_request_actor)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    run_status: Annotated[AgentRunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AgentRunResponse]:
    details = await AgentRunQueryService(uow_factory).list(status=run_status, limit=limit)
    return [_run_response(value) for value in details]


@router.get("/agent-runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(
    run_id: UUID,
    _: Annotated[RequestActor, Depends(get_request_actor)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> AgentRunResponse:
    return _run_response(await AgentRunQueryService(uow_factory).get(run_id))


@router.post(
    "/agent-runs/{run_id}/retry",
    response_model=MessageAnalysisRequestedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_agent_run(
    run_id: UUID,
    request: Request,
    response: Response,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    override_recalled: bool = False,
) -> MessageAnalysisRequestedResponse:
    details = await AgentRunQueryService(uow_factory).get(run_id)
    if details.run.feishu_message_id is None:
        from legal_workbench.domain.errors import InvalidStateTransitionError

        raise InvalidStateTransitionError("This AgentRun has no source message to retry.")
    return await _request_analysis(
        message_id=details.run.feishu_message_id,
        force_new_run=True,
        override_recalled=override_recalled,
        request=request,
        response=response,
        actor=actor,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )


@router.post("/agent-runs/{run_id}/cancel", response_model=AgentRunOperationResponse)
async def cancel_agent_run(
    run_id: UUID,
    request: Request,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> AgentRunOperationResponse:
    result = await CancelAgentRunHandler(uow_factory).execute(
        CancelAgentRunCommand(
            run_id=run_id,
            actor_id=actor.actor_id,
            actor_source=actor.identity_source,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
        )
    )
    return AgentRunOperationResponse(
        run_id=result.run_id,
        status=result.status,
        idempotent_replay=result.idempotent_replay,
    )


@router.get("/feishu/messages/{message_id}/analysis", response_model=MessageAnalysisResponse)
async def get_feishu_message_analysis(
    message_id: UUID,
    _: Annotated[RequestActor, Depends(get_request_actor)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> MessageAnalysisResponse:
    return _analysis_response(await FeishuMessageAnalysisQueryService(uow_factory).get(message_id))


async def _request_analysis(
    *,
    message_id: UUID,
    force_new_run: bool,
    override_recalled: bool,
    request: Request,
    response: Response,
    actor: RequestActor,
    idempotency_key: str,
    uow_factory: SqlAlchemyUnitOfWorkFactory,
) -> MessageAnalysisRequestedResponse:
    result = await RequestFeishuMessageAnalysisHandler(uow_factory).execute(
        RequestFeishuMessageAnalysisCommand(
            message_id=message_id,
            actor_id=actor.actor_id,
            actor_source="user",
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            force_new_run=force_new_run,
            override_recalled=override_recalled,
            authenticated_identity_source=actor.identity_source,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return MessageAnalysisRequestedResponse(
        message_id=result.message_id,
        message_status=result.status,
        idempotent_replay=result.idempotent_replay,
    )


@router.post(
    "/feishu/messages/{message_id}/analyse",
    response_model=MessageAnalysisRequestedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def analyse_feishu_message(
    message_id: UUID,
    request: Request,
    response: Response,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    override_recalled: bool = False,
) -> MessageAnalysisRequestedResponse:
    return await _request_analysis(
        message_id=message_id,
        force_new_run=False,
        override_recalled=override_recalled,
        request=request,
        response=response,
        actor=actor,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )


@router.post(
    "/feishu/messages/{message_id}/retry-analysis",
    response_model=MessageAnalysisRequestedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_feishu_message_analysis(
    message_id: UUID,
    request: Request,
    response: Response,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    override_recalled: bool = False,
) -> MessageAnalysisRequestedResponse:
    return await _request_analysis(
        message_id=message_id,
        force_new_run=True,
        override_recalled=override_recalled,
        request=request,
        response=response,
        actor=actor,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )
