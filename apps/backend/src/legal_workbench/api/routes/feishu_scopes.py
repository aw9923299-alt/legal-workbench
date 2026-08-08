from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from legal_workbench.api.auth import RequestActor
from legal_workbench.api.dependencies import (
    get_correlation_id,
    get_idempotency_key,
    get_if_match_version,
    get_request_actor,
    get_uow_factory,
)
from legal_workbench.api.schemas.feishu_scopes import (
    ChangeFeishuScopeRequest,
    DeferredFeishuCompensationResponse,
    FeishuScopeResponse,
    RegisterFeishuScopeRequest,
)
from legal_workbench.application.feishu_scopes import FeishuScopeService
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/settings/feishu-scopes", tags=["feishu-scopes"])


def get_feishu_scope_service(
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> FeishuScopeService:
    return FeishuScopeService(uow_factory)


@router.get("", response_model=list[FeishuScopeResponse])
async def list_feishu_scopes(
    service: Annotated[FeishuScopeService, Depends(get_feishu_scope_service)],
) -> list[FeishuScopeResponse]:
    return [
        FeishuScopeResponse.model_validate(value)
        for value in await service.list_scopes()
    ]


@router.post(
    "",
    response_model=FeishuScopeResponse,
)
async def register_feishu_scope(
    body: RegisterFeishuScopeRequest,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    service: Annotated[FeishuScopeService, Depends(get_feishu_scope_service)],
) -> FeishuScopeResponse:
    scope = await service.register_known_chat(
        chat_id=body.chat_id,
        display_name=body.display_name,
        actor_id=actor.actor_id,
        actor_source=actor.identity_source,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        identity_type=body.identity_type,
        scope_type=body.scope_type,
        authorization_id=body.authorization_id,
        backfill_days=body.backfill_days,
    )
    return FeishuScopeResponse.model_validate(scope)


@router.patch("/{scope_id}", response_model=FeishuScopeResponse)
async def change_feishu_scope(
    scope_id: UUID,
    body: ChangeFeishuScopeRequest,
    request: Request,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    service: Annotated[FeishuScopeService, Depends(get_feishu_scope_service)],
) -> FeishuScopeResponse:
    scope = await service.change_scope(
        scope_id=scope_id,
        expected_version=expected_version,
        action=body.action,
        sync_mode=body.sync_mode,
        actor_id=actor.actor_id,
        actor_source=actor.identity_source,
        correlation_id=get_correlation_id(request),
        idempotency_key=idempotency_key,
    )
    return FeishuScopeResponse.model_validate(scope)


@router.post(
    "/{scope_id}/compensate",
    response_model=DeferredFeishuCompensationResponse,
)
async def compensate_feishu_scope(
    scope_id: UUID,
    request: Request,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    service: Annotated[FeishuScopeService, Depends(get_feishu_scope_service)],
) -> DeferredFeishuCompensationResponse:
    result = await service.defer_compensation(
        scope_id=scope_id,
        expected_version=expected_version,
        actor_id=actor.actor_id,
        actor_source=actor.identity_source,
        correlation_id=get_correlation_id(request),
        idempotency_key=idempotency_key,
    )
    return DeferredFeishuCompensationResponse.model_validate(result)
