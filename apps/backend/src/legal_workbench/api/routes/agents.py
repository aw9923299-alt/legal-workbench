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
    AgentRunResponse,
    AgentRunSourceResponse,
    ContextSnapshotSummaryResponse,
    FeishuMessageSourceResponse,
    MessageAnalysisRequestedResponse,
    MessageAnalysisResponse,
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
from legal_workbench.domain.enums import AgentRunStatus, FeishuMessageStatus
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(tags=["agent-runs"])


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
        raw_stdout=run.raw_stdout,
        raw_stderr=run.raw_stderr,
        prompt_snapshot=run.prompt_snapshot,
        working_directory=run.working_directory,
        started_at=run.started_at,
        heartbeat_at=run.heartbeat_at,
        finished_at=run.finished_at,
        timeout_at=run.timeout_at,
        attempt_number=run.attempt_number,
        max_attempts=run.max_attempts,
        failure_code=run.failure_code,
        failure_message=run.failure_message,
        correlation_id=run.correlation_id,
        created_by=run.created_by,
        created_at=run.created_at,
        updated_at=run.updated_at,
        version=run.version,
        sources=[AgentRunSourceResponse.model_validate(source) for source in details.sources],
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
                participant_ids=snapshot.participant_ids,
                content_hash=snapshot.content_hash,
                truncated=bool(snapshot.content.get("truncated", False)),
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
            actor_source=actor.identity_source,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            force_new_run=force_new_run,
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
) -> MessageAnalysisRequestedResponse:
    return await _request_analysis(
        message_id=message_id,
        force_new_run=False,
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
) -> MessageAnalysisRequestedResponse:
    return await _request_analysis(
        message_id=message_id,
        force_new_run=True,
        request=request,
        response=response,
        actor=actor,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )
