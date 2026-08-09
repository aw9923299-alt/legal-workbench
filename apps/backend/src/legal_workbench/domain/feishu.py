from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar
from uuid import UUID

from legal_workbench.domain.common import (
    require_aware,
    utc_now,
)
from legal_workbench.domain.enums import (
    AttachmentDownloadStatus,
    DocumentExtractionStatus,
    FeishuEventStatus,
    FeishuMessageStatus,
    FeishuTokenRotationPhase,
    FeishuUserAuthorizationStatus,
    IntegrationConnectionMode,
    IntegrationConnectionStatus,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    InvalidStateTransitionError,
)


@dataclass(slots=True)
class FeishuRawEvent:
    id: UUID
    event_id: str
    event_type: str
    tenant_key: str | None
    app_id: str | None
    schema_version: str | None
    raw_payload: dict[str, object]
    payload_hash: str
    status: FeishuEventStatus = FeishuEventStatus.RECEIVED
    received_at: datetime = field(default_factory=utc_now)
    processed_at: datetime | None = None
    last_error: str | None = None
    source_channel: str = "app_event"
    provenance: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class IntegrationConnection:
    id: UUID
    integration_type: str
    connection_mode: IntegrationConnectionMode
    status: IntegrationConnectionStatus
    last_connected_at: datetime | None = None
    last_disconnected_at: datetime | None = None
    last_event_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    reconnect_count: int = 0
    last_reconcile_at: datetime | None = None
    last_reconcile_status: str | None = None
    last_reconcile_message: str | None = None
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class FeishuOAuthAttempt:
    id: UUID
    state_hash: str
    code_verifier_ref: str
    redirect_uri: str
    scopes: tuple[str, ...]
    requested_by: str
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        require_aware(self.expires_at, field_name="OAuth attempt expiry")
        if len(self.state_hash) != 64 or not self.code_verifier_ref:
            raise DomainValidationError("OAuth attempt metadata is invalid.")

    def consume(self, *, now: datetime | None = None) -> None:
        consumed_at = now or utc_now()
        if self.used_at is not None:
            raise InvalidStateTransitionError("OAuth state was already consumed.")
        if consumed_at >= self.expires_at:
            raise InvalidStateTransitionError("OAuth state has expired.")
        self.used_at = consumed_at


@dataclass(slots=True)
class FeishuUserAuthorization:
    id: UUID
    open_id: str
    union_id: str | None
    tenant_key: str
    display_name: str | None
    scopes: tuple[str, ...]
    access_token_ref: str
    refresh_token_ref: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    token_version: int
    status: FeishuUserAuthorizationStatus
    last_refreshed_at: datetime | None = None
    last_error_code: str | None = None
    pending_token_version: int | None = None
    pending_token_bundle_ref: str | None = None
    rotation_owner: str | None = None
    rotation_expires_at: datetime | None = None
    rotation_phase: FeishuTokenRotationPhase = FeishuTokenRotationPhase.IDLE
    rotation_request_started_at: datetime | None = None
    rotation_fence: int = 0
    rotation_result_written_at: datetime | None = None
    rotation_reauth_reason: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        require_aware(self.access_expires_at, field_name="User access token expiry")
        require_aware(self.refresh_expires_at, field_name="User refresh token expiry")
        if not self.open_id.strip() or not self.tenant_key.strip():
            raise DomainValidationError("Feishu user identity is required.")
        if not self.access_token_ref or not self.refresh_token_ref or self.token_version < 1:
            raise DomainValidationError("Feishu user token references are invalid.")
        if self.pending_token_version is not None and (
            self.pending_token_version <= self.token_version
            or not self.pending_token_bundle_ref
            or not self.rotation_owner
            or self.rotation_expires_at is None
        ):
            raise DomainValidationError("Pending Feishu token generation is invalid.")
        if self.rotation_fence < 0:
            raise DomainValidationError("Feishu token rotation fence is invalid.")
        for field_name, value in (
            ("rotation request start", self.rotation_request_started_at),
            ("rotation result write", self.rotation_result_written_at),
        ):
            if value is not None:
                require_aware(value, field_name=field_name)

    def rotate(
        self,
        *,
        access_token_ref: str,
        refresh_token_ref: str,
        access_expires_at: datetime,
        refresh_expires_at: datetime,
        scopes: tuple[str, ...],
        now: datetime | None = None,
    ) -> None:
        changed_at = now or utc_now()
        require_aware(access_expires_at, field_name="User access token expiry")
        require_aware(refresh_expires_at, field_name="User refresh token expiry")
        self.access_token_ref = access_token_ref
        self.refresh_token_ref = refresh_token_ref
        self.access_expires_at = access_expires_at
        self.refresh_expires_at = refresh_expires_at
        self.scopes = scopes
        self.token_version += 1
        self.status = FeishuUserAuthorizationStatus.CONNECTED
        self.last_refreshed_at = changed_at
        self.last_error_code = None
        self.updated_at = changed_at

    def clear_pending_rotation(self) -> None:
        self.pending_token_version = None
        self.pending_token_bundle_ref = None
        self.rotation_owner = None
        self.rotation_expires_at = None


@dataclass(slots=True)
class FeishuSyncCheckpoint:
    id: UUID
    authorization_id: UUID
    scope_id: UUID
    watermark: datetime | None = None
    page_token: str | None = None
    consecutive_failures: int = 0
    last_error_code: str | None = None
    last_started_at: datetime | None = None
    last_succeeded_at: datetime | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    lease_fence: int = 0
    updated_at: datetime = field(default_factory=utc_now)

    def claim(
        self,
        *,
        owner: str,
        expires_at: datetime,
        now: datetime,
    ) -> int:
        require_aware(expires_at, field_name="Sync lease expiry")
        require_aware(now, field_name="Sync lease claim time")
        if (
            self.lease_owner is not None
            and self.lease_expires_at is not None
            and self.lease_expires_at > now
        ):
            raise DomainValidationError("sync_lease_active")
        self.lease_owner = owner
        self.lease_expires_at = expires_at
        self.lease_fence += 1
        self.last_started_at = now
        self.updated_at = now
        return self.lease_fence

    def renew(
        self,
        *,
        owner: str,
        fence: int,
        page_token: str | None,
        expires_at: datetime,
        now: datetime,
    ) -> None:
        self._require_lease(owner=owner, fence=fence, now=now)
        require_aware(expires_at, field_name="Sync lease expiry")
        self.page_token = page_token
        self.lease_expires_at = expires_at
        self.updated_at = now

    def succeed(
        self,
        *,
        owner: str,
        fence: int,
        watermark: datetime,
        now: datetime,
    ) -> None:
        self._require_lease(owner=owner, fence=fence, now=now)
        require_aware(watermark, field_name="Sync checkpoint watermark")
        self.watermark = watermark
        self.page_token = None
        self.consecutive_failures = 0
        self.last_error_code = None
        self.last_succeeded_at = now
        self.lease_owner = None
        self.lease_expires_at = None
        self.updated_at = now

    def fail(
        self,
        *,
        owner: str,
        fence: int,
        error_code: str,
        now: datetime,
    ) -> None:
        self._require_lease(owner=owner, fence=fence, now=now)
        self.consecutive_failures += 1
        self.last_error_code = error_code
        self.page_token = None
        self.lease_owner = None
        self.lease_expires_at = None
        self.updated_at = now

    def _require_lease(self, *, owner: str, fence: int, now: datetime) -> None:
        require_aware(now, field_name="Sync lease check time")
        if (
            self.lease_owner != owner
            or self.lease_fence != fence
            or self.lease_expires_at is None
            or self.lease_expires_at <= now
        ):
            raise DomainValidationError("sync_lease_lost")


@dataclass(frozen=True, slots=True)
class FeishuMessageVersion:
    id: UUID
    feishu_message_id: UUID
    event_id: UUID
    revision: int
    raw_payload: dict[str, object]
    content_hash: str
    plain_text: str
    structured_content: dict[str, object]
    attachments: list[dict[str, object]]
    edited_at: datetime | None = None
    recalled_at: datetime | None = None
    is_recalled: bool = False
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class MessageAttachment:
    id: UUID
    feishu_message_id: UUID
    message_version_id: UUID
    file_key: str
    file_name: str
    mime_type: str | None
    size: int | None
    download_status: AttachmentDownloadStatus
    sha256: str | None = None
    local_path: str | None = None
    download_error: str | None = None
    authorized_for_analysis: bool = False
    extraction_status: DocumentExtractionStatus = DocumentExtractionStatus.NOT_REQUESTED
    extractor_version: str | None = None
    page_count: int | None = None
    character_count: int | None = None
    extraction_error_code: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


FeishuAttachment = MessageAttachment


@dataclass(slots=True)
class FeishuMessage:
    id: UUID
    event_id: UUID
    tenant_key: str | None
    message_id: str
    chat_id: str | None
    thread_id: str | None
    root_id: str | None
    parent_id: str | None
    sender_id: str | None
    sender_type: str | None
    message_type: str
    content: dict[str, object]
    mentions: list[dict[str, object]]
    create_time: datetime | None
    update_time: datetime | None
    raw_message: dict[str, object]
    status: FeishuMessageStatus = FeishuMessageStatus.RECEIVED
    context_snapshot_id: UUID | None = None
    last_agent_run_id: UUID | None = None
    analysis_attempts: int = 0
    failure_code: str | None = None
    failure_message: str | None = None
    version: int = 1
    plain_text: str | None = None
    structured_content: dict[str, object] = field(default_factory=dict)
    attachments: list[dict[str, object]] = field(default_factory=list)
    content_hash: str | None = None
    edited_at: datetime | None = None
    recalled_at: datetime | None = None
    unsupported_reason: str | None = None
    analysis_disposition: str = "analyze"
    analysis_policy_version: str = "legacy-app-event-v1"
    analysis_reasons: list[str] = field(default_factory=list)
    detected_document_links: list[dict[str, str]] = field(default_factory=list)
    source_channel: str = "app_event"
    source_channels: list[str] = field(default_factory=lambda: ["app_event"])
    provenance: dict[str, object] = field(default_factory=dict)

    _TRANSITIONS: ClassVar[dict[FeishuMessageStatus, set[FeishuMessageStatus]]] = {
        FeishuMessageStatus.RECEIVED: {FeishuMessageStatus.QUEUED_FOR_ANALYSIS},
        FeishuMessageStatus.QUEUED_FOR_ANALYSIS: {
            FeishuMessageStatus.CONTEXT_PREPARED,
            FeishuMessageStatus.ANALYSIS_FAILED,
            FeishuMessageStatus.DEAD_LETTER,
        },
        FeishuMessageStatus.CONTEXT_PREPARED: {
            FeishuMessageStatus.AGENT_QUEUED,
            FeishuMessageStatus.ANALYSIS_FAILED,
        },
        FeishuMessageStatus.AGENT_QUEUED: {
            FeishuMessageStatus.ANALYSING,
            FeishuMessageStatus.ANALYSIS_FAILED,
        },
        FeishuMessageStatus.ANALYSING: {
            FeishuMessageStatus.CANDIDATE_CREATED,
            FeishuMessageStatus.IGNORED,
            FeishuMessageStatus.ANALYSIS_FAILED,
        },
        FeishuMessageStatus.ANALYSIS_FAILED: {
            FeishuMessageStatus.QUEUED_FOR_ANALYSIS,
            FeishuMessageStatus.DEAD_LETTER,
        },
        FeishuMessageStatus.CANDIDATE_CREATED: {
            FeishuMessageStatus.QUEUED_FOR_ANALYSIS,
        },
        FeishuMessageStatus.IGNORED: {FeishuMessageStatus.QUEUED_FOR_ANALYSIS},
        FeishuMessageStatus.DEAD_LETTER: {FeishuMessageStatus.QUEUED_FOR_ANALYSIS},
    }

    def transition_to(
        self,
        target: FeishuMessageStatus,
        *,
        failure_code: str | None = None,
        failure_message: str | None = None,
    ) -> None:
        if target not in self._TRANSITIONS[self.status]:
            raise InvalidStateTransitionError(
                f"FeishuMessage cannot transition from {self.status.value} to {target.value}."
            )
        if target in {
            FeishuMessageStatus.ANALYSIS_FAILED,
            FeishuMessageStatus.DEAD_LETTER,
        } and (not failure_code or not failure_message):
            raise DomainValidationError("A failure code and failure message are required.")
        self.status = target
        self.failure_code = failure_code
        self.failure_message = failure_message
        if target == FeishuMessageStatus.ANALYSING:
            self.analysis_attempts += 1
        self.version += 1
