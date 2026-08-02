from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request

from legal_workbench.agents.codex_health import CodexRuntimeHealthChecker
from legal_workbench.api.auth import RequestActor
from legal_workbench.api.dependencies import (
    get_correlation_id,
    get_idempotency_key,
    get_request_actor,
    get_uow_factory,
)
from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.application.analysis_recovery import AnalysisRecoveryService
from legal_workbench.config import Settings, get_settings
from legal_workbench.domain.entities import AuditEvent, IdempotencyRecord
from legal_workbench.infrastructure.system_status import SystemStatusService
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/system", tags=["system"])


class ComponentHealthResponse(ApiModel):
    status: str
    detail: str
    updated_at: datetime


class CodexHealthResponse(ApiModel):
    enabled: bool
    status: str
    executable: str | None
    detected_version: str | None
    expected_version: str | None
    authentication: str
    runtime_directory_writable: bool
    detail: str


class SystemMetricsResponse(ApiModel):
    outbox_pending: int
    agent_queued: int
    failed_runs: int
    agent_dead_letters: int
    outbox_dead_letters: int
    last_message_at: datetime | None
    last_completed_run_at: datetime | None
    last_reconcile_at: datetime | None
    last_candidate_at: datetime | None
    last_agent_run_update_at: datetime | None
    last_outbox_failure_at: datetime | None


class SystemHealthResponse(ApiModel):
    generated_at: datetime
    components: dict[str, ComponentHealthResponse]
    metrics: SystemMetricsResponse | None
    codex: CodexHealthResponse


class RecoverPendingJobsResponse(ApiModel):
    missing_runs_requeued: int
    stale_runs_requeued: int
    dead_lettered: int
    idempotent_replay: bool = False


async def collect_system_health(settings: Settings) -> SystemHealthResponse:
    snapshot = await SystemStatusService().snapshot()
    health = await CodexRuntimeHealthChecker(
        command=settings.codex_command,
        expected_version=settings.codex_expected_version,
        runs_root=settings.codex_runs_root,
    ).check()
    components = {
        key: ComponentHealthResponse.model_validate(value)
        for key, value in snapshot.components.items()
    }
    cli_status = "normal" if health.executable and health.detected_version else "unavailable"
    if health.status.value == "version_mismatch":
        cli_status = "degraded"
    components["codex_cli"] = ComponentHealthResponse(
        status=cli_status,
        detail=health.detail,
        updated_at=snapshot.generated_at,
    )
    components["codex_auth"] = ComponentHealthResponse(
        status=(
            "normal"
            if health.status.value == "available"
            else "not_configured"
            if not settings.enable_real_codex or health.status.value == "unauthenticated"
            else "unavailable"
        ),
        detail=health.authentication,
        updated_at=snapshot.generated_at,
    )
    return SystemHealthResponse(
        generated_at=snapshot.generated_at,
        components=components,
        metrics=(
            SystemMetricsResponse.model_validate(snapshot.metrics)
            if snapshot.metrics
            else None
        ),
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


@router.get("/health", response_model=SystemHealthResponse)
async def system_health(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SystemHealthResponse:
    return await collect_system_health(settings)


@router.get("/metrics", response_model=SystemMetricsResponse | None)
async def system_metrics() -> SystemMetricsResponse | None:
    snapshot = await SystemStatusService().snapshot()
    return (
        SystemMetricsResponse.model_validate(snapshot.metrics)
        if snapshot.metrics
        else None
    )


@router.post("/recover-pending-jobs", response_model=RecoverPendingJobsResponse)
async def recover_pending_jobs(
    request: Request,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    settings: Annotated[Settings, Depends(get_settings)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> RecoverPendingJobsResponse:
    operation = "recover_pending_analysis_jobs"
    request_hash = hashlib.sha256(b"recover-pending-analysis-jobs-v1").hexdigest()
    async with uow_factory() as uow:
        await uow.lock_idempotency(operation=operation, key=idempotency_key)
        replay = await uow.idempotency.get(operation=operation, key=idempotency_key)
        if replay is not None:
            return RecoverPendingJobsResponse.model_validate(
                {**replay.response_payload, "idempotentReplay": True}
            )
    result = await AnalysisRecoveryService(
        uow_factory,
        stale_after_seconds=settings.analysis_recovery_stale_seconds,
        batch_size=settings.analysis_recovery_batch_size,
    ).recover()
    payload: dict[str, object] = {
        "missingRunsRequeued": result.missing_runs_requeued,
        "staleRunsRequeued": result.stale_runs_requeued,
        "deadLettered": result.dead_lettered,
    }
    async with uow_factory() as uow:
        await uow.lock_idempotency(operation=operation, key=idempotency_key)
        replay = await uow.idempotency.get(operation=operation, key=idempotency_key)
        if replay is None:
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="system",
                    aggregate_id=uuid4(),
                    event_type="analysis_recovery_triggered",
                    actor_id=actor.actor_id,
                    actor_source=actor.identity_source,
                    payload=payload,
                    correlation_id=get_correlation_id(request),
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=operation,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_payload=payload,
                )
            )
            await uow.commit()
        else:
            payload = replay.response_payload
    return RecoverPendingJobsResponse.model_validate(payload)
