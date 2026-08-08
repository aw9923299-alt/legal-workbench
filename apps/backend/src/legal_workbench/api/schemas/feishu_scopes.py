from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.domain.enums import (
    IntegrationIdentityType,
    IntegrationScopeStatus,
    IntegrationScopeType,
    IntegrationSyncMode,
)


class FeishuScopeResponse(ApiModel):
    id: UUID
    provider: str
    external_scope_id: str
    display_name: str | None
    status: IntegrationScopeStatus
    sync_mode: IntegrationSyncMode
    identity_type: IntegrationIdentityType
    scope_type: IntegrationScopeType
    authorization_id: UUID | None
    backfill_days: int
    high_value_legal: bool
    last_message_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    last_compensated_at: datetime | None
    last_compensation_status: str | None
    approved_by: str | None
    approved_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class RegisterFeishuScopeRequest(ApiModel):
    chat_id: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=240)
    identity_type: IntegrationIdentityType = IntegrationIdentityType.APP
    scope_type: IntegrationScopeType = IntegrationScopeType.GROUP
    authorization_id: UUID | None = None
    backfill_days: int = Field(default=7)


class ChangeFeishuScopeRequest(ApiModel):
    action: Literal["allow", "exclude", "pause", "resume"]
    sync_mode: IntegrationSyncMode | None = None


class DeferredFeishuCompensationResponse(ApiModel):
    scope: FeishuScopeResponse
    state: Literal["not_executed"]
    error_code: str
    message: str
    correlation_id: str
    idempotent_replay: bool
