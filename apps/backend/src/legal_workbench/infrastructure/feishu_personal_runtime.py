from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

import httpx

from legal_workbench.application.automatic_analysis_gate import AutomaticAnalysisGate
from legal_workbench.application.feishu_capabilities import (
    CORE_IDENTITY_SCOPES,
    FeishuCapability,
    FeishuCapabilityStatus,
    project_capabilities,
    require_capability,
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
from legal_workbench.application.feishu_user_auth import (
    FeishuOAuthService,
    FeishuUserTokenProvider,
)
from legal_workbench.application.message_analysis_policy import MessageAnalysisPolicy
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.config import Settings
from legal_workbench.domain.enums import (
    IntegrationIdentityType,
    IntegrationScopeStatus,
)
from legal_workbench.domain.errors import DomainValidationError, EntityNotFoundError
from legal_workbench.infrastructure.secrets import LocalSecretProvider
from legal_workbench.integrations.feishu_user_client import FeishuUserClient
from legal_workbench.integrations.feishu_user_oauth import FeishuOAuthHttpClient


class _AuthorizedUserResourceClient:
    def __init__(
        self,
        user_client: FeishuUserClient,
        authorization_id: UUID,
    ) -> None:
        self._user_client = user_client
        self._authorization_id = authorization_id

    async def download_message_resource(
        self,
        *,
        message_id: str,
        file_key: str,
        resource_type: str,
    ) -> tuple[bytes, str, int]:
        return await self._user_client.download_message_resource(
            authorization_id=self._authorization_id,
            message_id=message_id,
            file_key=file_key,
            resource_type=resource_type,
        )


class PersonalSyncRuntime:
    """Shared manual/scheduled facade over one personal-sync composition."""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        oauth: FeishuOAuthService,
        user_client: FeishuUserClient,
        message_sync_factory: Callable[
            [UUID, tuple[str, ...]], PersonalMessageSyncService
        ],
        document_sync: FeishuDocumentSyncService,
        folder_service: FeishuFolderSubscriptionService,
    ) -> None:
        self._uow_factory = uow_factory
        self.oauth = oauth
        self.user_client = user_client
        self._message_sync_factory = message_sync_factory
        self.document_sync = document_sync
        self.folder_service = folder_service

    async def sync_scope(self, scope_id: UUID) -> PersonalSyncResult:
        async with self._uow_factory() as uow:
            scope = await uow.setup.get_scope(scope_id)
            if scope is None:
                raise EntityNotFoundError("Feishu scope was not found.")
            if scope.authorization_id is None:
                raise DomainValidationError(
                    "Feishu scope is not bound to a user authorization."
                )
            authorization = await uow.feishu_user_authorizations.get_authorization(
                scope.authorization_id
            )
            if authorization is None:
                raise EntityNotFoundError("Feishu user authorization was not found.")
            require_capability(
                authorization.scopes,
                FeishuCapability.MESSAGE_HISTORY,
            )
        service = self._message_sync_factory(
            scope.authorization_id,
            authorization.scopes,
        )
        return await service.sync_scope(
            scope=scope,
            tenant_key=authorization.tenant_key,
            authorization_open_id=authorization.open_id,
        )

    async def sync_all_eligible_scopes(self) -> dict[str, object]:
        async with self._uow_factory() as uow:
            scopes = await uow.setup.list_scopes(provider="feishu")
            authorizations = (
                await uow.feishu_user_authorizations.list_authorizations()
            )
            folder_subscriptions = (
                await uow.documents.list_feishu_document_subscriptions(
                    active_only=True
                )
            )
        authorization_ids = {value.id for value in authorizations}
        eligible = [
            value
            for value in scopes
            if value.identity_type == IntegrationIdentityType.USER
            and value.status == IntegrationScopeStatus.ALLOWED
            and value.authorization_id in authorization_ids
        ]
        failed: list[str] = []
        failed_folder_subscriptions: list[str] = []
        ingested = 0
        synchronized_documents = 0
        for scope in eligible:
            try:
                result = await self.sync_scope(scope.id)
                ingested += result.ingested_count
            except Exception:
                failed.append(str(scope.id))
        for subscription in folder_subscriptions:
            try:
                authorization = next(
                    value
                    for value in authorizations
                    if value.id == subscription.authorization_id
                )
                require_capability(
                    authorization.scopes,
                    FeishuCapability.DRIVE_SEARCH,
                )
                require_capability(
                    authorization.scopes,
                    FeishuCapability.DOCUMENT_READ,
                )
                folder_result = await self.folder_service.sync_subscription(
                    subscription.id
                )
                synchronized_documents += folder_result.discovered_documents
            except Exception:
                failed_folder_subscriptions.append(str(subscription.id))
        return {
            "state": (
                "partial" if failed or failed_folder_subscriptions else "completed"
            ),
            "scopeCount": len(eligible),
            "ingestedCount": ingested,
            "failedScopeIds": failed,
            "folderSubscriptionCount": len(folder_subscriptions),
            "synchronizedDocumentCount": synchronized_documents,
            "failedFolderSubscriptionIds": failed_folder_subscriptions,
        }

    async def ensure_capability(
        self,
        authorization_id: UUID,
        capability: FeishuCapability,
        *,
        allow_partial: bool = False,
    ) -> None:
        async with self._uow_factory() as uow:
            authorization = await uow.feishu_user_authorizations.get_authorization(
                authorization_id
            )
        if authorization is None:
            raise EntityNotFoundError("Feishu user authorization was not found.")
        require_capability(
            authorization.scopes,
            capability,
            allow_partial=allow_partial,
        )


class PersonalSyncRuntimeFactory:
    def __init__(
        self,
        *,
        settings: Settings,
        uow_factory: UnitOfWorkFactory,
        required_scopes: tuple[str, ...] = CORE_IDENTITY_SCOPES,
    ) -> None:
        self._settings = settings
        self._uow_factory = uow_factory
        self._required_scopes = required_scopes

    async def _app_credentials(
        self, secret_provider: LocalSecretProvider
    ) -> tuple[str, str]:
        async with self._uow_factory() as uow:
            app_id_setting = await uow.setup.get_setting("feishu.app_id")
            credential = await uow.setup.get_credential(
                provider="feishu",
                credential_kind="app_secret",
            )
        app_id = (
            str(app_id_setting.value)
            if app_id_setting is not None
            else str(self._settings.feishu_app_id or "")
        ).strip()
        app_secret = str(self._settings.feishu_app_secret or "").strip()
        if not app_secret and credential is not None and credential.secret_ref:
            app_secret = secret_provider.read(credential.secret_ref)
        if not app_id or not app_secret:
            raise DomainValidationError(
                "Configure the existing Feishu App ID and App Secret before User OAuth."
            )
        return app_id, app_secret

    async def resolve_app_credentials(self) -> tuple[str, str]:
        """Resolve the single persisted app credential source for host processes."""
        return await self._app_credentials(
            LocalSecretProvider(self._settings.setup_secret_root)
        )

    @asynccontextmanager
    async def open(self) -> AsyncIterator[PersonalSyncRuntime]:
        secret_provider = LocalSecretProvider(self._settings.setup_secret_root)
        app_id, app_secret = await self._app_credentials(secret_provider)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._settings.feishu_request_timeout_seconds)
        ) as http_client:
            oauth_client = FeishuOAuthHttpClient(
                app_id=app_id,
                app_secret=app_secret,
                http_client=http_client,
                base_url=self._settings.feishu_api_base_url.removesuffix(
                    "/open-apis"
                ),
            )
            token_provider = FeishuUserTokenProvider(
                self._uow_factory,
                oauth_client=oauth_client,
                secret_provider=secret_provider,
                required_scopes=self._required_scopes,
            )
            user_client = FeishuUserClient(
                token_provider=token_provider,
                http_client=http_client,
                base_url=self._settings.feishu_api_base_url,
            )
            oauth = FeishuOAuthService(
                self._uow_factory,
                oauth_client=oauth_client,
                secret_provider=secret_provider,
                app_id=app_id,
                required_scopes=self._required_scopes,
            )
            analysis_gate = AutomaticAnalysisGate()
            ingestion_adapter = UserMessageIngestionAdapter(
                IngestFeishuEventHandler(self._uow_factory)
            )
            document_sync = FeishuDocumentSyncService(
                self._uow_factory,
                client=user_client,
            )

            def build_message_sync(
                authorization_id: UUID,
                granted_scopes: tuple[str, ...],
            ) -> PersonalMessageSyncService:
                capabilities = project_capabilities(granted_scopes)
                document_enabled = (
                    capabilities[FeishuCapability.DOCUMENT_READ].status
                    == FeishuCapabilityStatus.READY
                )
                attachment_status = capabilities[
                    FeishuCapability.ATTACHMENT_READ
                ].status
                metadata_only_reason = (
                    None
                    if attachment_status
                    in {
                        FeishuCapabilityStatus.READY,
                        FeishuCapabilityStatus.PARTIAL,
                    }
                    else "attachment_read_permission_missing"
                )
                return PersonalMessageSyncService(
                    self._uow_factory,
                    user_client=user_client,
                    ingestion_adapter=ingestion_adapter,
                    overlap=timedelta(
                        minutes=self._settings.feishu_user_sync_overlap_minutes
                    ),
                    analysis_policy=MessageAnalysisPolicy(),
                    document_sync=document_sync if document_enabled else None,
                    attachment_sync=FeishuOperationsService(
                        settings=self._settings,
                        uow_factory=self._uow_factory,
                        client=_AuthorizedUserResourceClient(
                            user_client,
                            authorization_id,
                        ),
                        unavailable_under_user_identity=True,
                        force_metadata_only_reason=metadata_only_reason,
                        analysis_gate=analysis_gate,
                    ),
                )

            folder_service = FeishuFolderSubscriptionService(
                self._uow_factory,
                folder_sync=FeishuFolderSyncService(
                    client=user_client,
                    document_sync=document_sync,
                ),
            )
            yield PersonalSyncRuntime(
                uow_factory=self._uow_factory,
                oauth=oauth,
                user_client=user_client,
                message_sync_factory=build_message_sync,
                document_sync=document_sync,
                folder_service=folder_service,
            )
