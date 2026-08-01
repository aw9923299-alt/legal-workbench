from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from legal_workbench.agents.codex_health import CodexRuntimeHealthChecker
from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.config import Settings, get_settings

router = APIRouter(prefix="/system", tags=["system"])


class CodexHealthResponse(ApiModel):
    enabled: bool
    status: str
    executable: str | None
    detected_version: str | None
    expected_version: str | None
    authentication: str
    runtime_directory_writable: bool
    detail: str


class SystemHealthResponse(ApiModel):
    generated_at: datetime
    codex: CodexHealthResponse


@router.get("/health", response_model=SystemHealthResponse)
async def system_health(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SystemHealthResponse:
    health = await CodexRuntimeHealthChecker(
        command=settings.codex_command,
        expected_version=settings.codex_expected_version,
        runs_root=settings.codex_runs_root,
    ).check()
    return SystemHealthResponse(
        generated_at=datetime.now(UTC),
        codex=CodexHealthResponse(
            enabled=settings.enable_real_codex,
            status=health.status.value,
            executable=health.executable,
            detected_version=health.detected_version,
            expected_version=health.expected_version,
            authentication=health.authentication,
            runtime_directory_writable=health.runtime_directory_writable,
            detail=health.detail,
        ),
    )
