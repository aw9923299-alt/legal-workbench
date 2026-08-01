from datetime import datetime
from uuid import UUID

from pydantic import Field

from legal_workbench.api.schemas.base import ApiModel


class FeishuEventIngestedResponse(ApiModel):
    event_id: UUID
    message_id: UUID | None
    duplicate: bool


class FeishuConnectionResponse(ApiModel):
    integration_type: str
    connection_mode: str
    status: str
    last_connected_at: datetime | None
    last_disconnected_at: datetime | None
    last_event_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    reconnect_count: int
    last_reconcile_at: datetime | None
    last_reconcile_status: str | None
    last_reconcile_message: str | None
    updated_at: datetime


class ReconcileRequest(ApiModel):
    window_minutes: int | None = Field(default=None, ge=1, le=1440)


class ReconcileResponse(ApiModel):
    status: str
    window_minutes: int
    ingested: int
    duplicates: int
    message: str


class OperationAcceptedResponse(ApiModel):
    accepted: bool = True
