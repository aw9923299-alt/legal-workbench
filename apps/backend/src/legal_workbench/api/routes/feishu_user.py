from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated
from uuid import UUID

import httpx
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
    FeishuUserAuthorizationResponse,
    FeishuUserDisconnectResponse,
    FeishuUserOAuthCallbackResponse,
    ImportFeishuDocumentRequest,
    SearchFeishuDocumentsRequest,
    StartFeishuUserAuthorizationRequest,
    StartFeishuUserAuthorizationResponse,
    SubscribeFeishuFolderRequest,
)
from legal_workbench.application.feishu_documents import (
    FeishuDocumentSyncService,
    FeishuFolderSubscriptionService,
    FeishuFolderSyncService,
)
from legal_workbench.application.feishu_handlers import IngestFeishuEventHandler
from legal_workbench.application.feishu_operations import FeishuOperationsService
from legal_workbench.application.feishu_personal_sync import (
    PersonalMessageSyncService,
    PersonalSyncResult,
    UserMessageIngestionAdapter,
)
from legal_workbench.application.feishu_scopes import FeishuScopeService
from legal_workbench.application.feishu_user_auth import (
    FeishuOAuthService,
    FeishuUserTokenProvider,
)
from legal_workbench.config import Settings, get_settings
from legal_workbench.domain.entities import FeishuDocumentSubscription
from legal_workbench.domain.errors import DomainValidationError, EntityNotFoundError
from legal_workbench.infrastructure.secrets import LocalSecretProvider
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from legal_workbench.integrations.feishu_local_connector import LocalFeishuConnector
from legal_workbench.integrations.feishu_user_client import FeishuUserClient
from legal_workbench.integrations.feishu_user_oauth import FeishuOAuthHttpClient

router = APIRouter(prefix="/integrations/feishu-user", tags=["feishu-user"])

USER_SCOPES = (
    "offline_access",
    "contact:user.base:readonly",
    "im:message:readonly",
    "im:message:get_as_user",
    "im:message.p2p_msg:get_as_user",
    "im:message.group_msg:get_as_user",
    "im:chat:read",
    "im:chat:readonly",
    "drive:drive.search:readonly",
    "drive:drive.metadata:readonly",
    "drive:drive:readonly",
    "docs:document.content:read",
)


@dataclass(slots=True)
class FeishuUserRuntime:
    oauth: FeishuOAuthService
    user_client: FeishuUserClient


@dataclass(slots=True)
class _AuthorizedUserResourceClient:
    user_client: FeishuUserClient
    authorization_id: UUID

    async def download_message_resource(
        self,
        *,
        message_id: str,
        file_key: str,
        resource_type: str,
    ) -> tuple[bytes, str, int]:
        return await self.user_client.download_message_resource(
            authorization_id=self.authorization_id,
            message_id=message_id,
            file_key=file_key,
            resource_type=resource_type,
        )


def _authorization_response(value: object) -> FeishuUserAuthorizationResponse:
    response = FeishuUserAuthorizationResponse.model_validate(value)
    granted = set(response.scopes)
    return response.model_copy(
        update={
            "missing_scopes": tuple(
                scope for scope in USER_SCOPES if scope not in granted
            )
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


def _folder_subscription_service(
    *,
    uow_factory: SqlAlchemyUnitOfWorkFactory,
    user_client: FeishuUserClient,
) -> FeishuFolderSubscriptionService:
    document_sync = FeishuDocumentSyncService(uow_factory, client=user_client)
    return FeishuFolderSubscriptionService(
        uow_factory,
        folder_sync=FeishuFolderSyncService(
            client=user_client,
            document_sync=document_sync,
        ),
    )


async def get_feishu_user_runtime(
    settings: Annotated[Settings, Depends(get_settings)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> AsyncIterator[FeishuUserRuntime]:
    secret_provider = LocalSecretProvider(settings.setup_secret_root)
    async with uow_factory() as uow:
        app_id_setting = await uow.setup.get_setting("feishu.app_id")
        credential = await uow.setup.get_credential(
            provider="feishu", credential_kind="app_secret"
        )
    app_id = (
        str(app_id_setting.value)
        if app_id_setting is not None
        else str(settings.feishu_app_id or "")
    ).strip()
    app_secret = str(settings.feishu_app_secret or "").strip()
    if not app_secret and credential and credential.secret_ref:
        app_secret = secret_provider.read(credential.secret_ref)
    if not app_id or not app_secret:
        raise DomainValidationError(
            "Configure the existing Feishu App ID and App Secret before User OAuth."
        )
    timeout = httpx.Timeout(settings.feishu_request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        oauth_client = FeishuOAuthHttpClient(
            app_id=app_id,
            app_secret=app_secret,
            http_client=http_client,
            base_url=settings.feishu_api_base_url.removesuffix("/open-apis"),
        )
        token_provider = FeishuUserTokenProvider(
            uow_factory,
            oauth_client=oauth_client,
            secret_provider=secret_provider,
            required_scopes=USER_SCOPES,
        )
        yield FeishuUserRuntime(
            oauth=FeishuOAuthService(
                uow_factory,
                oauth_client=oauth_client,
                secret_provider=secret_provider,
                app_id=app_id,
                required_scopes=USER_SCOPES,
            ),
            user_client=FeishuUserClient(
                token_provider=token_provider,
                http_client=http_client,
                base_url=settings.feishu_api_base_url,
            ),
        )


@router.get("/status", response_model=list[FeishuUserAuthorizationResponse])
async def feishu_user_status(
    runtime: Annotated[FeishuUserRuntime, Depends(get_feishu_user_runtime)],
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
    runtime: Annotated[FeishuUserRuntime, Depends(get_feishu_user_runtime)],
) -> StartFeishuUserAuthorizationResponse:
    result = await runtime.oauth.start_authorization(
        redirect_uri=body.redirect_uri,
        requested_by=actor.actor_id,
        scopes=USER_SCOPES,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    return StartFeishuUserAuthorizationResponse.model_validate(result)


@router.get("/callback", response_model=FeishuUserOAuthCallbackResponse)
async def complete_feishu_user_authorization(
    state: Annotated[str, Query(min_length=1)],
    code: Annotated[str, Query(min_length=1)],
    runtime: Annotated[FeishuUserRuntime, Depends(get_feishu_user_runtime)],
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
    runtime: Annotated[FeishuUserRuntime, Depends(get_feishu_user_runtime)],
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
    runtime: Annotated[FeishuUserRuntime, Depends(get_feishu_user_runtime)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> list[dict[str, object]]:
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
    runtime: Annotated[FeishuUserRuntime, Depends(get_feishu_user_runtime)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    async with uow_factory() as uow:
        scope = await uow.setup.get_scope(scope_id)
        if scope is None:
            raise EntityNotFoundError("Feishu scope was not found.")
        if scope.authorization_id is None:
            raise DomainValidationError("Feishu scope is not bound to a user authorization.")
        authorization = await uow.feishu_user_authorizations.get_authorization(
            scope.authorization_id
        )
        if authorization is None:
            raise EntityNotFoundError("Feishu user authorization was not found.")
    service = PersonalMessageSyncService(
        uow_factory,
        user_client=runtime.user_client,
        ingestion_adapter=UserMessageIngestionAdapter(
            IngestFeishuEventHandler(uow_factory)
        ),
        overlap=timedelta(minutes=settings.feishu_user_sync_overlap_minutes),
        document_sync=FeishuDocumentSyncService(
            uow_factory,
            client=runtime.user_client,
        ),
        attachment_sync=FeishuOperationsService(
            settings=settings,
            uow_factory=uow_factory,
            client=_AuthorizedUserResourceClient(
                user_client=runtime.user_client,
                authorization_id=scope.authorization_id,
            ),
            unavailable_under_user_identity=True,
        ),
    )
    result: PersonalSyncResult = await service.sync_scope(
        scope=scope,
        tenant_key=authorization.tenant_key,
        authorization_open_id=authorization.open_id,
    )
    return {
        "scopeId": str(result.scope_id),
        "ingestedCount": result.ingested_count,
        "startedAt": result.started_at,
        "completedAt": result.completed_at,
    }


@router.post("/documents/search", response_model=list[dict[str, object]])
async def search_feishu_user_documents(
    body: SearchFeishuDocumentsRequest,
    runtime: Annotated[FeishuUserRuntime, Depends(get_feishu_user_runtime)],
) -> list[dict[str, object]]:
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
    runtime: Annotated[FeishuUserRuntime, Depends(get_feishu_user_runtime)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> dict[str, object]:
    result = await FeishuDocumentSyncService(
        uow_factory,
        client=runtime.user_client,
    ).sync_document(
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
    runtime: Annotated[FeishuUserRuntime, Depends(get_feishu_user_runtime)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    authorization_id: Annotated[UUID | None, Query()] = None,
) -> list[dict[str, object]]:
    values = await _folder_subscription_service(
        uow_factory=uow_factory,
        user_client=runtime.user_client,
    ).list_subscriptions(authorization_id=authorization_id)
    return [_folder_subscription_payload(value) for value in values]


@router.post("/folders/{folder_token}/subscribe", response_model=dict[str, object])
async def subscribe_feishu_folder(
    folder_token: str,
    body: SubscribeFeishuFolderRequest,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    runtime: Annotated[FeishuUserRuntime, Depends(get_feishu_user_runtime)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> dict[str, object]:
    value = await _folder_subscription_service(
        uow_factory=uow_factory,
        user_client=runtime.user_client,
    ).subscribe(
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
    runtime: Annotated[FeishuUserRuntime, Depends(get_feishu_user_runtime)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> dict[str, object]:
    value = await _folder_subscription_service(
        uow_factory=uow_factory,
        user_client=runtime.user_client,
    ).unsubscribe(
        authorization_id=authorization_id,
        folder_token=folder_token,
        expected_version=expected_version,
        actor_id=actor.actor_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return _folder_subscription_payload(value)
