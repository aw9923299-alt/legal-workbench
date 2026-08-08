from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from legal_workbench.api.auth import RequestActor
from legal_workbench.api.dependencies import (
    get_correlation_id,
    get_idempotency_key,
    get_if_match_version,
    get_request_actor,
    get_uow_factory,
)
from legal_workbench.api.schemas.feishu_user import (
    FeishuCapabilityResponse,
    FeishuUserAuthorizationResponse,
    FeishuUserDisconnectResponse,
    FeishuUserOAuthCallbackResponse,
    ImportFeishuDocumentRequest,
    SearchFeishuDocumentsRequest,
    StartFeishuUserAuthorizationRequest,
    StartFeishuUserAuthorizationResponse,
    SubscribeFeishuFolderRequest,
)
from legal_workbench.application.feishu_capabilities import (
    CAPABILITY_LABELS,
    INITIAL_OAUTH_SCOPES,
    FeishuCapability,
    authorization_is_usable,
    project_capabilities,
)
from legal_workbench.application.feishu_scopes import FeishuScopeService
from legal_workbench.config import Settings, get_settings
from legal_workbench.domain.entities import FeishuDocumentSubscription
from legal_workbench.infrastructure.feishu_personal_runtime import (
    PersonalSyncRuntime,
    PersonalSyncRuntimeFactory,
)
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from legal_workbench.integrations.feishu_local_connector import LocalFeishuConnector

router = APIRouter(prefix="/integrations/feishu-user", tags=["feishu-user"])
oauth_callback_router = APIRouter(
    prefix="/integrations/feishu-user",
    tags=["feishu-user"],
)

USER_SCOPES = INITIAL_OAUTH_SCOPES


def _authorization_response(value: object) -> FeishuUserAuthorizationResponse:
    response = FeishuUserAuthorizationResponse.model_validate(value)
    projections = project_capabilities(response.scopes)
    usable = authorization_is_usable(projections)
    status = response.status
    if status.value == "permission_missing" and usable:
        status = type(response.status).CONNECTED
    return response.model_copy(
        update={
            "status": status,
            "missing_scopes": projections[
                FeishuCapability.CORE_IDENTITY
            ].missing_scopes,
            "capabilities": tuple(
                FeishuCapabilityResponse(
                    capability=capability,
                    label=CAPABILITY_LABELS[capability],
                    status=projection.status,
                    granted_scopes=projection.granted_scopes,
                    missing_scopes=projection.missing_scopes,
                )
                for capability, projection in projections.items()
            ),
            "usable": usable,
        }
    )


def _folder_subscription_payload(
    subscription: FeishuDocumentSubscription,
) -> dict[str, object]:
    return {
        "id": str(subscription.id),
        "authorizationId": str(subscription.authorization_id),
        "folderToken": subscription.folder_token,
        "recursive": subscription.recursive,
        "active": subscription.active,
        "version": subscription.version,
        "lastSyncedAt": subscription.last_synced_at,
        "lastErrorCode": subscription.last_error_code,
    }


async def get_feishu_user_runtime(
    settings: Annotated[Settings, Depends(get_settings)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> AsyncIterator[PersonalSyncRuntime]:
    factory = PersonalSyncRuntimeFactory(
        settings=settings,
        uow_factory=uow_factory,
    )
    async with factory.open() as runtime:
        yield runtime


@router.get("/status", response_model=list[FeishuUserAuthorizationResponse])
async def feishu_user_status(
    runtime: Annotated[PersonalSyncRuntime, Depends(get_feishu_user_runtime)],
) -> list[FeishuUserAuthorizationResponse]:
    return [
        _authorization_response(value)
        for value in await runtime.oauth.list_authorizations()
    ]


@router.post("/authorize", response_model=StartFeishuUserAuthorizationResponse)
async def authorize_feishu_user(
    body: StartFeishuUserAuthorizationRequest,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    runtime: Annotated[PersonalSyncRuntime, Depends(get_feishu_user_runtime)],
) -> StartFeishuUserAuthorizationResponse:
    result = await runtime.oauth.start_authorization(
        redirect_uri=body.redirect_uri,
        requested_by=actor.actor_id,
        scopes=USER_SCOPES,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    return StartFeishuUserAuthorizationResponse.model_validate(result)


@oauth_callback_router.get("/callback", response_model=FeishuUserOAuthCallbackResponse)
async def complete_feishu_user_authorization(
    state: Annotated[str, Query(min_length=1)],
    code: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PersonalSyncRuntime, Depends(get_feishu_user_runtime)],
) -> FeishuUserOAuthCallbackResponse:
    authorization = await runtime.oauth.complete_authorization(state=state, code=code)
    return FeishuUserOAuthCallbackResponse(
        authorization=_authorization_response(authorization)
    )


@router.post(
    "/{authorization_id}/revoke",
    response_model=FeishuUserDisconnectResponse,
)
async def revoke_feishu_user(
    authorization_id: UUID,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    runtime: Annotated[PersonalSyncRuntime, Depends(get_feishu_user_runtime)],
) -> FeishuUserDisconnectResponse:
    value = await runtime.oauth.disconnect(
        authorization_id,
        actor_id=actor.actor_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return FeishuUserDisconnectResponse(
        authorization_id=value.id,
        status=value.status,
    )


@router.post("/{authorization_id}/discover", response_model=list[dict[str, object]])
async def discover_feishu_user_scopes(
    authorization_id: UUID,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    _idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    runtime: Annotated[PersonalSyncRuntime, Depends(get_feishu_user_runtime)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> list[dict[str, object]]:
    await runtime.ensure_capability(
        authorization_id,
        FeishuCapability.CHAT_DISCOVERY,
    )
    service = FeishuScopeService(uow_factory)
    official_scopes = await service.discover_user_groups(
        authorization_id=authorization_id,
        client=runtime.user_client,
        actor_id=actor.actor_id,
        correlation_id=correlation_id,
    )
    local_scopes = await service.discover_local_p2p_chats(
        authorization_id=authorization_id,
        records=LocalFeishuConnector().read_messages(),
        actor_id=actor.actor_id,
        correlation_id=correlation_id,
    )
    scopes = tuple(
        {value.id: value for value in (*official_scopes, *local_scopes)}.values()
    )
    return [
        {
            "id": str(value.id),
            "externalScopeId": value.external_scope_id,
            "displayName": value.display_name,
            "status": value.status.value,
            "scopeType": value.scope_type.value,
        }
        for value in scopes
    ]


@router.post("/scopes/{scope_id}/sync", response_model=dict[str, object])
async def sync_feishu_user_scope(
    scope_id: UUID,
    _idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    runtime: Annotated[PersonalSyncRuntime, Depends(get_feishu_user_runtime)],
) -> dict[str, object]:
    result = await runtime.sync_scope(scope_id)
    return {
        "scopeId": str(result.scope_id),
        "ingestedCount": result.ingested_count,
        "startedAt": result.started_at,
        "completedAt": result.completed_at,
    }


@router.post("/documents/search", response_model=list[dict[str, object]])
async def search_feishu_user_documents(
    body: SearchFeishuDocumentsRequest,
    runtime: Annotated[PersonalSyncRuntime, Depends(get_feishu_user_runtime)],
) -> list[dict[str, object]]:
    await runtime.ensure_capability(
        body.authorization_id,
        FeishuCapability.DRIVE_SEARCH,
    )
    values, _next_page = await runtime.user_client.search_documents(
        authorization_id=body.authorization_id,
        query=body.query,
    )
    return list(values)


@router.post("/documents/{document_token}/import", response_model=dict[str, object])
async def import_feishu_user_document(
    document_token: str,
    body: ImportFeishuDocumentRequest,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    runtime: Annotated[PersonalSyncRuntime, Depends(get_feishu_user_runtime)],
) -> dict[str, object]:
    await runtime.ensure_capability(
        body.authorization_id,
        FeishuCapability.DOCUMENT_READ,
    )
    result = await runtime.document_sync.sync_document(
        authorization_id=body.authorization_id,
        document_token=document_token,
        document_type=body.document_type,
        title=body.title,
        source_url=body.source_url,
        actor_id=actor.actor_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return {
        "documentId": str(result.document_id),
        "documentVersionId": str(result.document_version_id),
        "createdVersion": result.created_version,
        "segmentCount": result.segment_count,
    }


@router.get("/folders/subscriptions", response_model=list[dict[str, object]])
async def list_feishu_folder_subscriptions(
    runtime: Annotated[PersonalSyncRuntime, Depends(get_feishu_user_runtime)],
    authorization_id: Annotated[UUID | None, Query()] = None,
) -> list[dict[str, object]]:
    values = await runtime.folder_service.list_subscriptions(
        authorization_id=authorization_id
    )
    return [_folder_subscription_payload(value) for value in values]


@router.post("/folders/{folder_token}/subscribe", response_model=dict[str, object])
async def subscribe_feishu_folder(
    folder_token: str,
    body: SubscribeFeishuFolderRequest,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    runtime: Annotated[PersonalSyncRuntime, Depends(get_feishu_user_runtime)],
) -> dict[str, object]:
    await runtime.ensure_capability(
        body.authorization_id,
        FeishuCapability.DRIVE_SEARCH,
    )
    value = await runtime.folder_service.subscribe(
        authorization_id=body.authorization_id,
        folder_token=folder_token,
        recursive=body.recursive,
        actor_id=actor.actor_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return _folder_subscription_payload(value)


@router.delete("/folders/{folder_token}/subscribe", response_model=dict[str, object])
async def unsubscribe_feishu_folder(
    folder_token: str,
    authorization_id: Annotated[UUID, Query()],
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    runtime: Annotated[PersonalSyncRuntime, Depends(get_feishu_user_runtime)],
) -> dict[str, object]:
    value = await runtime.folder_service.unsubscribe(
        authorization_id=authorization_id,
        folder_token=folder_token,
        expected_version=expected_version,
        actor_id=actor.actor_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return _folder_subscription_payload(value)
