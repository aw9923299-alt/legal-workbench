from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select

from legal_workbench.domain.enums import AgentRunStatus
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


@dataclass(frozen=True, slots=True)
class SystemStatusSnapshot:
    generated_at: datetime
    components: dict[str, ComponentStatus]
    metrics: OperationalMetrics | None


class SystemStatusService:
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
        metrics = await self._database_metrics() if database_ready else None
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

    @staticmethod
    async def _database_metrics() -> OperationalMetrics:
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
