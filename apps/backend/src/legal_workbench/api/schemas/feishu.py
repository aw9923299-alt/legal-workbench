from datetime import datetime
from uuid import UUID

from pydantic import Field

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.domain.enums import (
    AgentRunStatus,
    CandidateStatus,
    DocumentExtractionStatus,
    FeishuMessageStatus,
)


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


class FeishuMessageSummaryResponse(ApiModel):
    id: UUID
    message_id: str
    tenant_key: str | None
    chat_id: str | None
    thread_id: str | None
    parent_message_id: str | None
    root_message_id: str | None
    sender_id: str | None
    sender_type: str | None
    message_type: str
    plain_text: str | None
    sent_at: datetime | None
    edited_at: datetime | None
    recalled_at: datetime | None
    status: FeishuMessageStatus
    unsupported_reason: str | None
    analysis_attempts: int
    failure_code: str | None
    failure_message: str | None
    agent_run_id: UUID | None
    agent_status: AgentRunStatus | None
    candidate_id: UUID | None
    candidate_status: CandidateStatus | None
    confidence: float | None
    suggested_category: str | None
    suggested_deadline: str | None


class FeishuMessageVersionResponse(ApiModel):
    id: UUID
    revision: int
    event_id: UUID
    plain_text: str
    structured_content: dict[str, object]
    attachments: list[dict[str, object]]
    content_hash: str
    edited_at: datetime | None
    recalled_at: datetime | None
    is_recalled: bool
    created_at: datetime


class FeishuAttachmentResponse(ApiModel):
    id: UUID
    file_key: str
    file_name: str
    mime_type: str | None
    size: int | None
    sha256: str | None
    download_status: str
    download_error: str | None
    authorized_for_analysis: bool
    extraction_status: DocumentExtractionStatus
    extractor_version: str | None
    page_count: int | None
    character_count: int | None
    extraction_error_code: str | None


class SetAttachmentAuthorizationRequest(ApiModel):
    authorized: bool


class SetAttachmentAuthorizationResponse(FeishuAttachmentResponse):
    idempotent_replay: bool


class CandidateRevisionResponse(ApiModel):
    id: UUID
    candidate_id: UUID
    revision: int
    agent_run_id: UUID
    analysis_payload: dict[str, object]
    created_at: datetime
    superseded_at: datetime | None
    superseded_by: UUID | None


class FeishuMessageDetailResponse(FeishuMessageSummaryResponse):
    structured_content: dict[str, object]
    raw_payload: dict[str, object]
    context_messages: list[FeishuMessageSummaryResponse]
    versions: list[FeishuMessageVersionResponse]
    attachments: list[FeishuAttachmentResponse]
    candidate_revisions: list[CandidateRevisionResponse]
