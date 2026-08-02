import hmac
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from legal_workbench.api.dependencies import (
    get_actor_id,
    get_correlation_id,
    get_idempotency_key,
    get_uow_factory,
)
from legal_workbench.api.schemas.feishu import (
    FeishuConnectionResponse,
    FeishuEventIngestedResponse,
    OperationAcceptedResponse,
    ReconcileRequest,
    ReconcileResponse,
)
from legal_workbench.application.commands import IngestFeishuEventCommand
from legal_workbench.application.feishu_handlers import IngestFeishuEventHandler
from legal_workbench.application.feishu_operations import FeishuOperationsService
from legal_workbench.config import FeishuEventSourceMode, get_settings
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/integrations/feishu", tags=["feishu"])
logger = structlog.get_logger(__name__)


@router.post("/events")
async def receive_feishu_event(
    request: Request,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> dict[str, Any] | FeishuEventIngestedResponse:
    settings = get_settings()
    if not settings.enable_real_feishu:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Real Feishu event ingestion is disabled by configuration.",
        )
    if settings.feishu_event_source != FeishuEventSourceMode.WEBHOOK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Webhook intake is not active while long_connection mode is selected.",
        )
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Feishu event payload must be an object.")
    if "encrypt" in payload:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Encrypted Feishu event payloads are not enabled in this deployment.",
        )
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str):
            raise HTTPException(status_code=400, detail="Feishu challenge is missing.")
        _verify_token(payload)
        return {"challenge": challenge}

    header = payload.get("header")
    if not isinstance(header, dict):
        raise HTTPException(status_code=400, detail="Feishu event header is missing.")
    _verify_token(payload)
    event_id = str(header.get("event_id") or "").strip()
    event_type = str(header.get("event_type") or "").strip()
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Feishu event_id and event_type are required.")
    result = await IngestFeishuEventHandler(uow_factory).execute(
        IngestFeishuEventCommand(
            actor_id="feishu-connector",
            correlation_id=get_correlation_id(request),
            event_id=event_id,
            event_type=event_type,
            tenant_key=str(header.get("tenant_key") or "") or None,
            app_id=str(header.get("app_id") or "") or None,
            schema_version=str(payload.get("schema") or "") or None,
            raw_payload=payload,
        )
    )
    await FeishuOperationsService(
        settings=settings, uow_factory=uow_factory
    ).record_event_received()
    return FeishuEventIngestedResponse.model_validate(result)


@router.get("/status", response_model=FeishuConnectionResponse)
async def get_feishu_status(
    actor_id: Annotated[str, Depends(get_actor_id)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> FeishuConnectionResponse:
    del actor_id
    connection = await FeishuOperationsService(
        settings=get_settings(), uow_factory=uow_factory
    ).get_connection()
    return FeishuConnectionResponse.model_validate(connection)


@router.post("/reconnect", response_model=OperationAcceptedResponse)
async def reconnect_feishu(
    request: Request,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> OperationAcceptedResponse:
    await FeishuOperationsService(
        settings=get_settings(), uow_factory=uow_factory
    ).request_reconnect(
        actor_id=actor_id,
        correlation_id=get_correlation_id(request),
        idempotency_key=idempotency_key,
    )
    return OperationAcceptedResponse()


@router.post("/reconcile", response_model=ReconcileResponse)
async def reconcile_feishu(
    body: ReconcileRequest,
    request: Request,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> ReconcileResponse:
    result = await FeishuOperationsService(
        settings=get_settings(), uow_factory=uow_factory
    ).reconcile(
        actor_id=actor_id,
        correlation_id=get_correlation_id(request),
        idempotency_key=idempotency_key,
        window_minutes=body.window_minutes,
    )
    return ReconcileResponse.model_validate(result)


def _verify_token(payload: dict[str, object]) -> None:
    settings = get_settings()
    expected = settings.feishu_verification_token
    if not expected:
        logger.warning("feishu_verification_failed", reason="token_not_configured")
        raise HTTPException(
            status_code=403,
            detail="Plain Feishu callbacks require verification-token validation.",
        )
    header = payload.get("header")
    actual: object = payload.get("token")
    if isinstance(header, dict):
        actual = header.get("token") or actual
    if not isinstance(actual, str) or not hmac.compare_digest(actual, expected):
        logger.warning("feishu_verification_failed", reason="token_mismatch")
        raise HTTPException(status_code=403, detail="Invalid Feishu verification token.")
