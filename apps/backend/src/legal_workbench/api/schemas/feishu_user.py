from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.application.feishu_capabilities import (
    FeishuCapability,
    FeishuCapabilityStatus,
)
from legal_workbench.domain.enums import FeishuUserAuthorizationStatus


class StartFeishuUserAuthorizationRequest(ApiModel):
    redirect_uri: str = Field(min_length=1, max_length=2000)


class StartFeishuUserAuthorizationResponse(ApiModel):
    authorization_url: str
    state: str
    expires_at: datetime


class FeishuCapabilityResponse(ApiModel):
    capability: FeishuCapability
    label: str
    status: FeishuCapabilityStatus
    granted_scopes: tuple[str, ...] = ()
    missing_scopes: tuple[str, ...] = ()


class FeishuUserAuthorizationResponse(ApiModel):
    id: UUID
    open_id: str
    tenant_key: str
    display_name: str | None
    scopes: tuple[str, ...]
    missing_scopes: tuple[str, ...] = ()
    capabilities: tuple[FeishuCapabilityResponse, ...] = ()
    usable: bool = False
    access_expires_at: datetime
    refresh_expires_at: datetime
    status: FeishuUserAuthorizationStatus
    last_refreshed_at: datetime | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime


class FeishuUserOAuthCallbackResponse(ApiModel):
    authorization: FeishuUserAuthorizationResponse


class FeishuUserDisconnectResponse(ApiModel):
    authorization_id: UUID
    status: FeishuUserAuthorizationStatus


class SearchFeishuDocumentsRequest(ApiModel):
    authorization_id: UUID
    query: str = Field(min_length=1, max_length=500)


class ImportFeishuDocumentRequest(ApiModel):
    authorization_id: UUID
    document_type: str = Field(pattern="^(docx|wiki)$")
    title: str | None = Field(default=None, max_length=500)
    source_url: str = Field(min_length=1, max_length=2000)


class SubscribeFeishuFolderRequest(ApiModel):
    authorization_id: UUID
    recursive: bool = False
