from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from legal_workbench.domain.common import (
    utc_now,
)
from legal_workbench.domain.enums import (
    IntegrationCheckStatus,
    IntegrationIdentityType,
    IntegrationScopeStatus,
    IntegrationScopeType,
    IntegrationSyncMode,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    InvalidStateTransitionError,
)


@dataclass(slots=True)
class SystemSetting:
    id: UUID
    key: str
    value: object
    value_type: str
    updated_by: str
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(cls, *, key: str, value: object, updated_by: str) -> SystemSetting:
        normalized = key.strip()
        if not normalized or not updated_by.strip():
            raise DomainValidationError("Setting key and actor are required.")
        if isinstance(value, bool):
            value_type = "boolean"
        elif isinstance(value, int | float):
            value_type = "number"
        elif isinstance(value, dict | list):
            value_type = "json"
        else:
            value_type = "string"
        return cls(
            id=uuid4(),
            key=normalized,
            value=value,
            value_type=value_type,
            updated_by=updated_by.strip(),
        )


@dataclass(slots=True)
class IntegrationCredential:
    id: UUID
    provider: str
    credential_kind: str
    secret_ref: str | None
    configured: bool
    masked_hint: str | None = None
    last_validated_at: datetime | None = None
    last_validation_status: str | None = None
    last_error_code: str | None = None
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.credential_kind.strip():
            raise DomainValidationError("Integration credential identity is required.")
        if self.configured and not self.secret_ref:
            raise DomainValidationError("Configured credentials require a secret reference.")


@dataclass(slots=True)
class IntegrationScope:
    id: UUID
    provider: str
    external_scope_id: str
    display_name: str | None
    status: IntegrationScopeStatus = IntegrationScopeStatus.UNAPPROVED
    sync_mode: IntegrationSyncMode = IntegrationSyncMode.DISABLED
    identity_type: IntegrationIdentityType = IntegrationIdentityType.APP
    scope_type: IntegrationScopeType = IntegrationScopeType.GROUP
    authorization_id: UUID | None = None
    backfill_days: int = 7
    high_value_legal: bool = False
    last_message_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_compensated_at: datetime | None = None
    last_compensation_status: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.external_scope_id.strip():
            raise DomainValidationError("Integration scope identity is required.")
        if self.identity_type == IntegrationIdentityType.USER and self.authorization_id is None:
            raise DomainValidationError("A user scope requires an authorization.")
        if self.backfill_days not in {7, 30, 90}:
            raise DomainValidationError("Scope backfill must be 7, 30 or 90 days.")

    def allow(
        self,
        *,
        sync_mode: IntegrationSyncMode,
        actor_id: str,
        now: datetime | None = None,
    ) -> None:
        if sync_mode == IntegrationSyncMode.DISABLED:
            raise DomainValidationError("An allowed scope requires an active sync mode.")
        changed_at = now or utc_now()
        self.status = IntegrationScopeStatus.ALLOWED
        self.sync_mode = sync_mode
        self.approved_by = actor_id
        self.approved_at = changed_at
        self.updated_at = changed_at
        self.version += 1

    def exclude(self, *, now: datetime | None = None) -> None:
        changed_at = now or utc_now()
        self.status = IntegrationScopeStatus.EXCLUDED
        self.sync_mode = IntegrationSyncMode.DISABLED
        self.updated_at = changed_at
        self.version += 1

    def pause(self, *, now: datetime | None = None) -> None:
        if self.status != IntegrationScopeStatus.ALLOWED:
            raise InvalidStateTransitionError("Only an allowed scope can be paused.")
        changed_at = now or utc_now()
        self.status = IntegrationScopeStatus.PAUSED
        self.sync_mode = IntegrationSyncMode.DISABLED
        self.updated_at = changed_at
        self.version += 1

    def resume(
        self,
        *,
        sync_mode: IntegrationSyncMode,
        actor_id: str,
        now: datetime | None = None,
    ) -> None:
        if self.status != IntegrationScopeStatus.PAUSED:
            raise InvalidStateTransitionError("Only a paused scope can be resumed.")
        self.allow(sync_mode=sync_mode, actor_id=actor_id, now=now)

    def record_deferred_compensation(self, *, now: datetime | None = None) -> None:
        changed_at = now or utc_now()
        self.last_compensated_at = changed_at
        self.last_compensation_status = "not_executed"
        self.updated_at = changed_at
        self.version += 1


@dataclass(slots=True)
class IntegrationCheckRun:
    id: UUID
    provider: str
    check_kind: str
    status: IntegrationCheckStatus
    requested_by: str
    correlation_id: str
    started_at: datetime
    state: str = "pending"
    error_code: str | None = None
    detail: str | None = None
    runtime_version: str | None = None
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)

    def start(self, *, now: datetime | None = None) -> None:
        if self.status != IntegrationCheckStatus.PENDING:
            raise InvalidStateTransitionError("Only a pending integration check can start.")
        self.status = IntegrationCheckStatus.RUNNING
        self.started_at = now or utc_now()

    def finish(
        self,
        *,
        state: str,
        error_code: str | None,
        detail: str,
        runtime_version: str | None = None,
        now: datetime | None = None,
    ) -> None:
        if self.status not in {IntegrationCheckStatus.PENDING, IntegrationCheckStatus.RUNNING}:
            raise InvalidStateTransitionError("Integration check is already final.")
        self.status = (
            IntegrationCheckStatus.COMPLETED
            if error_code is None
            else IntegrationCheckStatus.FAILED
        )
        self.state = state
        self.error_code = error_code
        self.detail = detail
        self.runtime_version = runtime_version
        self.finished_at = now or utc_now()
