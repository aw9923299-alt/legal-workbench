from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_workbench.domain.enums import AgentRunStatus, FeishuMessageStatus
from legal_workbench.infrastructure.celery_app import celery_app
from legal_workbench.infrastructure.database import database_is_ready, get_session_factory
from legal_workbench.infrastructure.models import (
    AgentRunModel,
    FeishuMessageModel,
    IntegrationConnectionModel,
    MessageCandidateModel,
    OutboxDeadLetterModel,
    OutboxEventModel,
)
from legal_workbench.infrastructure.redis_client import get_redis_client, redis_is_ready


@dataclass(frozen=True, slots=True)
class ComponentStatus:
    status: str
    detail: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OperationalMetrics:
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
    pending_recovery: int
    disk_free_bytes: int | None
    disk_total_bytes: int | None
    attachment_bytes_used: int | None
    attachment_quota_bytes: int
    last_backup_at: datetime | None
    last_backup_status: str
    last_wake_check_at: datetime | None


@dataclass(frozen=True, slots=True)
class SystemStatusSnapshot:
    generated_at: datetime
    components: dict[str, ComponentStatus]
    metrics: OperationalMetrics | None


@dataclass(frozen=True, slots=True)
class LocalOperationsStatus:
    disk_component: ComponentStatus
    backup_component: ComponentStatus
    disk_free_bytes: int | None
    disk_total_bytes: int | None
    attachment_bytes_used: int | None
    last_backup_at: datetime | None
    last_backup_status: str
    last_wake_check_at: datetime | None


async def _pending_recovery_count(
    session: AsyncSession,
    *,
    now: datetime,
    stale_after_seconds: int,
) -> int:
    """Count only durable analysis work the recovery service can act on."""
    active_statuses = [
        AgentRunStatus.QUEUED,
        AgentRunStatus.PREPARING,
        AgentRunStatus.RUNNING,
        AgentRunStatus.VALIDATING,
    ]
    active_run_exists = exists(
        select(AgentRunModel.id).where(
            AgentRunModel.feishu_message_id == FeishuMessageModel.id,
            AgentRunModel.status.in_(active_statuses),
        )
    )
    missing_active_run = await session.scalar(
        select(func.count()).select_from(FeishuMessageModel).where(
            FeishuMessageModel.status == FeishuMessageStatus.QUEUED_FOR_ANALYSIS,
            ~active_run_exists,
        )
    )
    stale_cutoff = now - timedelta(seconds=stale_after_seconds)
    stale_active_run = await session.scalar(
        select(func.count()).select_from(AgentRunModel).where(
            AgentRunModel.feishu_message_id.is_not(None),
            or_(
                and_(
                    AgentRunModel.status == AgentRunStatus.QUEUED,
                    func.coalesce(
                        AgentRunModel.heartbeat_at,
                        AgentRunModel.updated_at,
                    )
                    < stale_cutoff,
                ),
                and_(
                    AgentRunModel.status.in_(
                        [AgentRunStatus.PREPARING, AgentRunStatus.RUNNING]
                    ),
                    func.coalesce(
                        AgentRunModel.heartbeat_at,
                        AgentRunModel.updated_at,
                    )
                    < stale_cutoff,
                    or_(
                        AgentRunModel.lease_expires_at.is_(None),
                        AgentRunModel.lease_expires_at <= now,
                    ),
                ),
            ),
        )
    )
    return int(missing_active_run or 0) + int(stale_active_run or 0)


class SystemStatusService:
    def __init__(
        self,
        *,
        operations_state_root: str | Path = "/data/operations",
        backup_root: str | Path = "/data/backups",
        attachment_root: str | Path = "/data/feishu-attachments",
        attachment_quota_bytes: int = 5 * 1024 * 1024 * 1024,
        minimum_disk_free_bytes: int = 5 * 1024 * 1024 * 1024,
        backup_max_age_hours: int = 36,
        analysis_recovery_stale_seconds: int = 120,
    ) -> None:
        self._operations_state_root = Path(operations_state_root)
        self._backup_root = Path(backup_root)
        self._attachment_root = Path(attachment_root)
        self._attachment_quota_bytes = attachment_quota_bytes
        self._minimum_disk_free_bytes = minimum_disk_free_bytes
        self._backup_max_age_hours = backup_max_age_hours
        self._analysis_recovery_stale_seconds = analysis_recovery_stale_seconds

    async def snapshot(self) -> SystemStatusSnapshot:
        now = datetime.now(UTC)
        database_ready, redis_ready = await asyncio.gather(
            database_is_ready(), redis_is_ready()
        )
        components = {
            "fastapi": ComponentStatus("normal", "API process is responding.", now),
            "postgresql": ComponentStatus(
                "normal" if database_ready else "unavailable",
                "PostgreSQL is reachable." if database_ready else "PostgreSQL is unreachable.",
                now,
            ),
            "redis": ComponentStatus(
                "normal" if redis_ready else "unavailable",
                "Redis broker is reachable." if redis_ready else "Redis broker is unreachable.",
                now,
            ),
        }
        if redis_ready:
            worker_ready = await asyncio.to_thread(self._worker_is_ready)
            scheduler_heartbeat = await self._scheduler_heartbeat()
            components["celery_worker"] = ComponentStatus(
                "normal" if worker_ready else "degraded",
                "Celery worker answered ping."
                if worker_ready
                else "No Celery worker answered within the health timeout.",
                now,
            )
            components["celery_scheduler"] = ComponentStatus(
                "normal" if scheduler_heartbeat else "degraded",
                "Recent scheduler heartbeat observed."
                if scheduler_heartbeat
                else "No recent scheduler heartbeat observed.",
                scheduler_heartbeat or now,
            )
        else:
            components["celery_worker"] = ComponentStatus(
                "unavailable", "Redis broker is unavailable.", now
            )
            components["celery_scheduler"] = ComponentStatus(
                "unavailable", "Redis broker is unavailable.", now
            )
        local_status = await asyncio.to_thread(self._local_operations_status, now)
        components["disk"] = local_status.disk_component
        components["backup"] = local_status.backup_component
        metrics = (
            await self._database_metrics(now=now, local_status=local_status)
            if database_ready
            else None
        )
        if database_ready:
            feishu = await self._feishu_component(now)
            components["feishu"] = feishu
        else:
            components["feishu"] = ComponentStatus(
                "unavailable", "Connection state cannot be read without PostgreSQL.", now
            )
        return SystemStatusSnapshot(
            generated_at=now,
            components=components,
            metrics=metrics,
        )

    @staticmethod
    def _worker_is_ready() -> bool:
        try:
            # A busy single-worker Mac can legitimately need more than 500 ms to
            # answer control-plane pings. Keep the probe bounded while avoiding
            # transient false degradation in the operational dashboard.
            inspector = celery_app.control.inspect(timeout=1.0)
            return bool(inspector.ping())
        except Exception:
            return False

    @staticmethod
    async def _scheduler_heartbeat() -> datetime | None:
        try:
            value = await get_redis_client().get("legal-workbench:scheduler-heartbeat")
            return datetime.fromisoformat(value) if value else None
        except Exception:
            return None

    async def _database_metrics(
        self,
        *,
        now: datetime,
        local_status: LocalOperationsStatus,
    ) -> OperationalMetrics:
        async with get_session_factory()() as session:
            outbox_pending = await session.scalar(
                select(func.count()).select_from(OutboxEventModel).where(
                    OutboxEventModel.published_at.is_(None),
                    OutboxEventModel.dead_lettered_at.is_(None),
                )
            )
            agent_queued = await session.scalar(
                select(func.count()).select_from(AgentRunModel).where(
                    AgentRunModel.status.in_(
                        [
                            AgentRunStatus.QUEUED,
                            AgentRunStatus.PREPARING,
                            AgentRunStatus.RUNNING,
                            AgentRunStatus.VALIDATING,
                        ]
                    )
                )
            )
            failed_runs = await session.scalar(
                select(func.count()).select_from(AgentRunModel).where(
                    AgentRunModel.status.in_(
                        [AgentRunStatus.FAILED, AgentRunStatus.TIMED_OUT]
                    )
                )
            )
            agent_dead_letters = await session.scalar(
                select(func.count()).select_from(AgentRunModel).where(
                    AgentRunModel.status == AgentRunStatus.DEAD_LETTER
                )
            )
            outbox_dead_letters = await session.scalar(
                select(func.count()).select_from(OutboxDeadLetterModel).where(
                    OutboxDeadLetterModel.requeued_at.is_(None)
                )
            )
            last_message_at = await session.scalar(
                select(func.max(FeishuMessageModel.created_at))
            )
            last_completed_run_at = await session.scalar(
                select(func.max(AgentRunModel.finished_at)).where(
                    AgentRunModel.status.in_(
                        [
                            AgentRunStatus.COMPLETED,
                            AgentRunStatus.NEEDS_MORE_INFORMATION,
                        ]
                    )
                )
            )
            last_reconcile_at = await session.scalar(
                select(func.max(IntegrationConnectionModel.last_reconcile_at))
            )
            last_candidate_at = await session.scalar(
                select(func.max(MessageCandidateModel.created_at))
            )
            last_agent_run_update_at = await session.scalar(
                select(func.max(AgentRunModel.updated_at))
            )
            last_outbox_failure_at = await session.scalar(
                select(func.max(OutboxEventModel.dead_lettered_at))
            )
            pending_recovery = await _pending_recovery_count(
                session,
                now=now,
                stale_after_seconds=self._analysis_recovery_stale_seconds,
            )
        return OperationalMetrics(
            outbox_pending=int(outbox_pending or 0),
            agent_queued=int(agent_queued or 0),
            failed_runs=int(failed_runs or 0),
            agent_dead_letters=int(agent_dead_letters or 0),
            outbox_dead_letters=int(outbox_dead_letters or 0),
            last_message_at=last_message_at,
            last_completed_run_at=last_completed_run_at,
            last_reconcile_at=last_reconcile_at,
            last_candidate_at=last_candidate_at,
            last_agent_run_update_at=last_agent_run_update_at,
            last_outbox_failure_at=last_outbox_failure_at,
            pending_recovery=pending_recovery,
            disk_free_bytes=local_status.disk_free_bytes,
            disk_total_bytes=local_status.disk_total_bytes,
            attachment_bytes_used=local_status.attachment_bytes_used,
            attachment_quota_bytes=self._attachment_quota_bytes,
            last_backup_at=local_status.last_backup_at,
            last_backup_status=local_status.last_backup_status,
            last_wake_check_at=local_status.last_wake_check_at,
        )

    def _local_operations_status(self, now: datetime) -> LocalOperationsStatus:
        disk_free: int | None = None
        disk_total: int | None = None
        attachment_bytes: int | None = None
        try:
            disk_path = self._attachment_root
            while not disk_path.exists() and disk_path != disk_path.parent:
                disk_path = disk_path.parent
            usage = shutil.disk_usage(disk_path)
            disk_free = usage.free
            disk_total = usage.total
            attachment_bytes = _directory_bytes(self._attachment_root)
            degraded = (
                disk_free < self._minimum_disk_free_bytes
                or attachment_bytes > self._attachment_quota_bytes
            )
            disk_component = ComponentStatus(
                "degraded" if degraded else "normal",
                (
                    "Disk space or attachment quota requires attention."
                    if degraded
                    else "Disk space and attachment quota are within configured limits."
                ),
                now,
            )
        except OSError:
            disk_component = ComponentStatus(
                "unavailable", "Disk status could not be read.", now
            )
        backup = _read_state_json(self._operations_state_root / "backup-status.json")
        backup_status = str(backup.get("status", "unknown"))
        if backup_status == "succeeded":
            last_backup_at = _parse_datetime(backup.get("completedAt"))
            backup_file_name = backup.get("fileName")
            backup_size = backup.get("sizeBytes")
        else:
            last_backup_at = _parse_datetime(backup.get("lastSuccessfulAt"))
            backup_file_name = backup.get("lastSuccessfulFileName")
            backup_size = backup.get("lastSuccessfulSizeBytes")
        backup_file_valid = _backup_file_matches(
            self._backup_root,
            file_name=backup_file_name,
            expected_size=backup_size,
        )
        backup_stale = (
            last_backup_at is not None
            and now - last_backup_at > timedelta(hours=self._backup_max_age_hours)
        )
        effective_backup_status = backup_status
        if backup_status == "succeeded" and not backup_file_valid:
            effective_backup_status = "missing"
        elif backup_status == "succeeded" and backup_stale:
            effective_backup_status = "stale"
        if (
            effective_backup_status == "succeeded"
            and last_backup_at is not None
        ):
            backup_component = ComponentStatus(
                "normal", "A recent PostgreSQL backup completed successfully.", last_backup_at
            )
        elif effective_backup_status == "unknown":
            backup_component = ComponentStatus(
                "unknown", "No PostgreSQL backup result has been recorded.", now
            )
        else:
            backup_component = ComponentStatus(
                "degraded",
                (
                    "The latest PostgreSQL backup failed, is missing, or is older "
                    "than the configured limit."
                ),
                _parse_datetime(backup.get("failedAt")) or last_backup_at or now,
            )
        wake = _read_state_json(self._operations_state_root / "wake-status.json")
        return LocalOperationsStatus(
            disk_component=disk_component,
            backup_component=backup_component,
            disk_free_bytes=disk_free,
            disk_total_bytes=disk_total,
            attachment_bytes_used=attachment_bytes,
            last_backup_at=last_backup_at,
            last_backup_status=effective_backup_status,
            last_wake_check_at=_parse_datetime(wake.get("completedAt")),
        )

    @staticmethod
    async def _feishu_component(now: datetime) -> ComponentStatus:
        async with get_session_factory()() as session:
            connection = await session.scalar(
                select(IntegrationConnectionModel)
                .where(IntegrationConnectionModel.integration_type == "feishu")
                .order_by(IntegrationConnectionModel.updated_at.desc())
                .limit(1)
            )
        if connection is None:
            return ComponentStatus("not_configured", "No Feishu connection row exists.", now)
        mapped = {
            "connected": "normal",
            "starting": "degraded",
            "degraded": "degraded",
            "disabled": "not_configured",
            "disconnected": "unavailable",
            "failed": "unavailable",
        }
        return ComponentStatus(
            mapped.get(connection.status.value, "degraded"),
            connection.last_error_message or f"Feishu is {connection.status.value}.",
            connection.updated_at,
        )


def _read_state_json(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        return {"status": "unknown"}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unreadable"}
    return value if isinstance(value, dict) else {"status": "unreadable"}


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _directory_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for base, _directories, files in os.walk(root, followlinks=False):
        for name in files:
            path = Path(base) / name
            try:
                if not path.is_symlink():
                    total += path.stat().st_size
            except OSError:
                continue
    return total


def _backup_file_matches(
    root: Path,
    *,
    file_name: object,
    expected_size: object,
) -> bool:
    if (
        not isinstance(file_name, str)
        or not file_name
        or Path(file_name).name != file_name
        or isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size < 1
    ):
        return False
    candidate = root / file_name
    try:
        if (
            not candidate.is_file()
            or candidate.is_symlink()
            or candidate.stat().st_size != expected_size
        ):
            return False
        with candidate.open("rb") as stream:
            return stream.read(5) == b"PGDMP"
    except OSError:
        return False
