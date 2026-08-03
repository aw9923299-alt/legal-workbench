from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, status

from legal_workbench.agents.codex_health import CodexRuntimeHealthChecker
from legal_workbench.api.auth import RequestActor
from legal_workbench.api.dependencies import (
    get_correlation_id,
    get_idempotency_key,
    get_request_actor,
    get_uow_factory,
)
from legal_workbench.api.schemas.setup import (
    CodexCheckRequestedResponse,
    FeishuValidateRequest,
    SetupActionResponse,
    SetupStatusResponse,
)
from legal_workbench.application.setup import SetupService
from legal_workbench.config import Settings, get_settings
from legal_workbench.infrastructure.secrets import LocalSecretProvider
from legal_workbench.infrastructure.system_status import SystemStatusService
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/setup", tags=["setup"])


async def _basic_services() -> dict[str, str]:
    snapshot = await SystemStatusService().snapshot()
    mapping = {
        "api": "fastapi",
        "postgresql": "postgresql",
        "redis": "redis",
        "worker": "celery_worker",
        "scheduler": "celery_scheduler",
    }
    return {
        public: (
            "ready" if snapshot.components[internal].status == "normal" else "runtime_unreachable"
        )
        for public, internal in mapping.items()
    }


def get_setup_service(
    settings: Annotated[Settings, Depends(get_settings)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> SetupService:
    return SetupService(
        uow_factory,
        settings=settings,
        secret_provider=LocalSecretProvider(Path(settings.setup_secret_root)),
        codex_health_checker=CodexRuntimeHealthChecker(
            command=settings.codex_command,
            expected_version=settings.codex_expected_version,
            runs_root=settings.codex_runs_root,
        ),
        basic_services_probe=_basic_services,
    )


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    service: Annotated[SetupService, Depends(get_setup_service)],
) -> SetupStatusResponse:
    return SetupStatusResponse.model_validate(
        await service.get_status(correlation_id=correlation_id)
    )


async def _defer_feishu(
    *,
    action: str,
    actor: RequestActor,
    correlation_id: str,
    service: SetupService,
    credentials_supplied: bool = False,
) -> SetupActionResponse:
    result = await service.defer_feishu_action(
        action=action,
        actor_id=actor.actor_id,
        actor_source=actor.identity_source,
        correlation_id=correlation_id,
        credentials_supplied=credentials_supplied,
    )
    return SetupActionResponse.model_validate(result)


@router.post("/feishu/validate", response_model=SetupActionResponse)
async def validate_feishu(
    payload: FeishuValidateRequest,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    service: Annotated[SetupService, Depends(get_setup_service)],
) -> SetupActionResponse:
    # Values remain request-local and are intentionally not persisted while the
    # real Feishu phase is deferred.
    supplied = bool(payload.app_id or payload.app_secret)
    return await _defer_feishu(
        action="validate",
        actor=actor,
        correlation_id=correlation_id,
        service=service,
        credentials_supplied=supplied,
    )


@router.post("/feishu/start", response_model=SetupActionResponse)
async def start_feishu(
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    service: Annotated[SetupService, Depends(get_setup_service)],
) -> SetupActionResponse:
    return await _defer_feishu(
        action="start", actor=actor, correlation_id=correlation_id, service=service
    )


@router.post("/feishu/stop", response_model=SetupActionResponse)
async def stop_feishu(
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    service: Annotated[SetupService, Depends(get_setup_service)],
) -> SetupActionResponse:
    return await _defer_feishu(
        action="stop", actor=actor, correlation_id=correlation_id, service=service
    )


async def _request_codex(
    *,
    check_kind: str,
    actor: RequestActor,
    correlation_id: str,
    idempotency_key: str,
    service: SetupService,
) -> CodexCheckRequestedResponse:
    result = await service.request_codex_check(
        check_kind=check_kind,
        actor_id=actor.actor_id,
        actor_source=actor.identity_source,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return CodexCheckRequestedResponse.model_validate(result)


@router.post(
    "/codex/validate",
    response_model=CodexCheckRequestedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def validate_codex(
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    service: Annotated[SetupService, Depends(get_setup_service)],
) -> CodexCheckRequestedResponse:
    return await _request_codex(
        check_kind="validate",
        actor=actor,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        service=service,
    )


@router.post(
    "/codex/smoke-test",
    response_model=CodexCheckRequestedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def smoke_test_codex(
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    service: Annotated[SetupService, Depends(get_setup_service)],
) -> CodexCheckRequestedResponse:
    return await _request_codex(
        check_kind="smoke_test",
        actor=actor,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        service=service,
    )
