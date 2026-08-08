from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, SecretStr

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.domain.enums import SetupState


class SetupComponentResponse(ApiModel):
    state: SetupState
    message: str
    correlation_id: str
    error_code: str | None = None


class MaskedCredentialResponse(ApiModel):
    configured: bool
    app_id_masked: str | None
    secret_masked: str | None
    last_validation_status: str | None
    last_error_code: str | None


class FeishuSetupResponse(ApiModel):
    credentials: MaskedCredentialResponse
    permissions: SetupComponentResponse
    scopes: SetupComponentResponse
    connection: SetupComponentResponse
    test_message: SetupComponentResponse
    manual_unread_acceptance: SetupComponentResponse
    event_source: str
    receive_direct_messages: bool
    group_mentions_only: bool
    configured_group_all_messages: bool
    allowed_scope_count: int
    excluded_scope_count: int


class CodexSetupResponse(ApiModel):
    cli: SetupComponentResponse
    version: SetupComponentResponse
    authentication: SetupComponentResponse
    smoke_test: SetupComponentResponse
    expected_version: str
    detected_version: str | None


class SetupStepResponse(ApiModel):
    number: int
    key: str
    title: str
    component: SetupComponentResponse


class SetupStatusResponse(ApiModel):
    generated_at: datetime
    correlation_id: str
    overall_state: SetupState
    basic_services: dict[str, str]
    feishu: FeishuSetupResponse
    codex: CodexSetupResponse
    steps: list[SetupStepResponse]


class FeishuValidateRequest(ApiModel):
    app_id: str | None = Field(default=None, max_length=160)
    app_secret: SecretStr | None = None


class SetupActionResponse(ApiModel):
    state: SetupState
    message: str
    correlation_id: str
    error_code: str | None = None


class CodexCheckRequestedResponse(ApiModel):
    check_run_id: UUID
    state: SetupState
    message: str
    correlation_id: str
    idempotent_replay: bool = False
