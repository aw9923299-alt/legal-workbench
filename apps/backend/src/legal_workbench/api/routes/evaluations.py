from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from legal_workbench.api.auth import RequestActor
from legal_workbench.api.dependencies import (
    get_correlation_id,
    get_idempotency_key,
    get_request_actor,
    get_uow_factory,
)
from legal_workbench.api.schemas.evaluations import (
    EvaluationRunResponse,
    RunEvaluationRequest,
)
from legal_workbench.application.evaluations import (
    EvaluationRunReport,
    EvaluationService,
    RunEvaluationCommand,
)
from legal_workbench.config import Settings, get_settings
from legal_workbench.domain.errors import DomainValidationError

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


def get_evaluation_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EvaluationService:
    return EvaluationService(
        get_uow_factory(),
        # Real Codex credentials belong only to a dedicated Worker/Runner. The API process
        # never instantiates CodexCliRuntime; the CLI runner is the explicit real path today.
        real_executor=None,
        real_runtime_enabled=settings.enable_real_codex,
    )


def _response(report: EvaluationRunReport) -> EvaluationRunResponse:
    return EvaluationRunResponse.model_validate(
        {
            **{
                "id": report.run.id,
                "suiteKey": report.run.suite_key,
                "suiteVersion": report.run.suite_version,
                "runtimeType": report.run.runtime_type,
                "agentKey": report.run.agent_key,
                "agentDefinitionVersion": report.run.agent_definition_version,
                "status": report.run.status,
                "requestedBy": report.run.requested_by,
                "correlationId": report.run.correlation_id,
                "allowRealRuntime": report.run.allow_real_runtime,
                "startedAt": report.run.started_at,
                "finishedAt": report.run.finished_at,
                "metrics": report.run.metrics or None,
                "failureCode": report.run.failure_code,
            },
            "results": report.results,
        }
    )


@router.post("/runs", response_model=EvaluationRunResponse)
async def run_evaluation(
    payload: RunEvaluationRequest,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationRunResponse:
    if payload.suite_key != "message_judgement_v1":
        raise DomainValidationError(
            "The requested evaluation suite is not available.",
            details={"suiteKey": payload.suite_key},
        )
    report = await service.run(
        RunEvaluationCommand(
            fixture_path=settings.evaluation_fixture_path,
            runtime_type=payload.runtime_type,
            allow_real_runtime=payload.allow_real_runtime,
            actor_id=actor.actor_id,
            actor_source=actor.identity_source,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
    )
    return _response(report)


@router.get("/runs/{run_id}", response_model=EvaluationRunResponse)
async def get_evaluation_run(
    run_id: UUID,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationRunResponse:
    return _response(await service.get_report(run_id))
