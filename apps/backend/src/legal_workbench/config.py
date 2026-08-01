from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="LEGAL_WORKBENCH_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "法务工作台 API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    database_url: str = Field(
        default="postgresql+psycopg://legal_workbench:legal_workbench@localhost:5432/legal_workbench"
    )
    redis_url: str = "redis://localhost:6379/0"

    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_verification_token: str | None = None
    feishu_encrypt_key: str | None = None

    knowledge_root: str = "/data/knowledge"
    codex_runs_root: str = "/data/codex-runs"
    codex_command: str = "codex"
    codex_run_timeout_seconds: int = 900

    enable_real_feishu: bool = False
    enable_real_codex: bool = False
    enable_external_send: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
