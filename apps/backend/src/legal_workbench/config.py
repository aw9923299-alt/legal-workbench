from enum import StrEnum
from functools import lru_cache
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeEnvironment(StrEnum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class FeishuEventSourceMode(StrEnum):
    LONG_CONNECTION = "long_connection"
    WEBHOOK = "webhook"


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="LEGAL_WORKBENCH_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "法务工作台 API"
    environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    local_timezone: str = "Asia/Shanghai"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    database_url: str = Field(
        default=(
            "postgresql+psycopg://legal_workbench:legal_workbench@localhost:5432/legal_workbench"
        )
    )
    redis_url: str = "redis://localhost:6379/0"

    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_verification_token: str | None = None
    feishu_encrypt_key: str | None = None
    feishu_api_base_url: str = "https://open.feishu.cn/open-apis"
    feishu_request_timeout_seconds: int = 15
    feishu_event_source: FeishuEventSourceMode = FeishuEventSourceMode.LONG_CONNECTION
    feishu_reconnect_max_seconds: int = 30
    feishu_reconcile_window_minutes: int = 60
    feishu_reconcile_chat_ids: list[str] = Field(default_factory=list)
    feishu_tenant_key: str | None = None
    feishu_attachment_root: str = "/data/feishu-attachments"
    feishu_attachment_max_bytes: int = 50 * 1024 * 1024
    feishu_attachment_total_quota_bytes: int = 5 * 1024 * 1024 * 1024
    document_extraction_work_root: str = "/data/document-extractions"
    document_extraction_timeout_seconds: int = 30
    document_extraction_max_output_bytes: int = 5 * 1024 * 1024

    knowledge_root: str = "/data/knowledge"
    codex_runs_root: str = "/data/codex-runs"
    codex_command: str = "codex"
    codex_cli_version: str = Field(
        default="0.146.0",
        validation_alias="CODEX_CLI_VERSION",
    )
    codex_run_timeout_seconds: int = 900
    codex_sandbox_uid: int | None = None
    codex_sandbox_gid: int | None = None

    enable_real_feishu: bool = False
    enable_real_codex: bool = False
    enable_external_send: bool = False
    evaluation_fixture_path: str = (
        "apps/backend/tests/fixtures/evaluations/message_judgement_v1.json"
    )

    local_actor_id: str = "local-legal-user"
    session_secret: str = "development-only-change-me"
    session_cookie_name: str = "legal_workbench_session"
    session_ttl_seconds: int = 43200
    allow_development_actor_header: bool = False

    outbox_batch_size: int = 50
    outbox_lock_seconds: int = 60
    outbox_max_attempts: int = 8
    outbox_retry_base_seconds: int = 15
    outbox_retry_max_seconds: int = 3600
    outbox_worker_id: str = "local-outbox-worker"

    context_max_messages: int = 20
    context_max_text_characters: int = 20000
    context_max_single_message_characters: int = 8000
    context_max_attachments: int = 10
    context_max_attachment_segments: int = 100
    context_max_single_attachment_segment_characters: int = 4000
    context_builder_version: str = "2.0.0"
    context_selection_policy_version: str = "thread-v2"
    message_analysis_manual_review_threshold: float = 0.75
    message_analysis_retry_base_seconds: int = 30
    message_analysis_retry_max_seconds: int = 900
    agent_run_lease_seconds: int = 60
    analysis_recovery_interval_seconds: int = 30
    analysis_recovery_stale_seconds: int = 120
    analysis_recovery_batch_size: int = 100

    @property
    def codex_expected_version(self) -> str:
        """Compatibility name for the single CODEX_CLI_VERSION setting."""
        return self.codex_cli_version

    @field_validator("codex_sandbox_uid", "codex_sandbox_gid", mode="before")
    @classmethod
    def normalize_optional_process_ids(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("local_timezone")
    @classmethod
    def validate_local_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Local timezone must be a valid IANA timezone.") from exc
        return value

    @model_validator(mode="after")
    def validate_security_boundaries(self) -> Self:
        if self.enable_real_feishu:
            if self.feishu_event_source == FeishuEventSourceMode.LONG_CONNECTION and not (
                (self.feishu_app_id or "").strip() and (self.feishu_app_secret or "").strip()
            ):
                raise ValueError("Real Feishu long_connection mode requires app credentials.")
            if (
                self.feishu_event_source == FeishuEventSourceMode.WEBHOOK
                and not (self.feishu_verification_token or "").strip()
            ):
                raise ValueError("Real Feishu webhook mode requires a verification token.")
        if self.environment not in {
            RuntimeEnvironment.LOCAL,
            RuntimeEnvironment.DEVELOPMENT,
        } and (
            self.session_secret == "development-only-change-me"
            or len(self.session_secret.strip()) < 32
        ):
            raise ValueError(
                "Non-local environments require an explicit session secret of at least 32 "
                "characters."
            )
        if (
            self.environment == RuntimeEnvironment.PRODUCTION
            and self.allow_development_actor_header
        ):
            raise ValueError("Development actor headers cannot be enabled in production.")
        if not 0 <= self.message_analysis_manual_review_threshold <= 1:
            raise ValueError("Message analysis manual-review threshold must be between 0 and 1.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
