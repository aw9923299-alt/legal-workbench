import asyncio
from typing import Any
from uuid import UUID

from legal_workbench.agents.codex_cli import CodexCliRuntime
from legal_workbench.agents.definitions import build_message_judgement_definition
from legal_workbench.agents.runtime import AgentRuntimeError, DisabledAgentRuntime
from legal_workbench.application.analysis_recovery import AnalysisRecoveryService
from legal_workbench.application.context_snapshots import ContextSnapshotBuilder
from legal_workbench.application.message_analysis import (
    AnalyseFeishuMessageCommand,
    AnalyseFeishuMessageHandler,
    MessageAnalysisError,
)
from legal_workbench.config import get_settings
from legal_workbench.infrastructure.celery_app import celery_app
from legal_workbench.infrastructure.outbox import OutboxDispatcher
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory


@celery_app.task(name="system.ping")  # type: ignore[untyped-decorator]
def ping(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "ok", "payload": payload or {}}


@celery_app.task(name="outbox.publish")  # type: ignore[untyped-decorator]
def publish_outbox() -> dict[str, int]:
    count = asyncio.run(OutboxDispatcher().publish_batch())
    return {"claimed": count}


@celery_app.task(name="analysis.recover")  # type: ignore[untyped-decorator]
def recover_analysis() -> dict[str, int]:
    settings = get_settings()
    result = asyncio.run(
        AnalysisRecoveryService(
            SqlAlchemyUnitOfWorkFactory(),
            stale_after_seconds=settings.analysis_recovery_stale_seconds,
            batch_size=settings.analysis_recovery_batch_size,
        ).recover()
    )
    return {
        "missingRunsRequeued": result.missing_runs_requeued,
        "staleRunsRequeued": result.stale_runs_requeued,
        "deadLettered": result.dead_lettered,
    }


async def _analyse_feishu_message(
    message_id: UUID,
    *,
    actor_id: str,
    actor_source: str,
    correlation_id: str,
    force_new_run: bool,
    recover_interrupted_run: bool,
    worker_id: str | None,
) -> dict[str, str | bool | None]:
    settings = get_settings()
    uow_factory = SqlAlchemyUnitOfWorkFactory()
    runtime = (
        CodexCliRuntime(
            runs_root=settings.codex_runs_root,
        )
        if settings.enable_real_codex
        else DisabledAgentRuntime()
    )
    handler = AnalyseFeishuMessageHandler(
        uow_factory,
        runtime,
        ContextSnapshotBuilder(
            uow_factory,
            max_messages=settings.context_max_messages,
            max_text_characters=settings.context_max_text_characters,
            max_single_message_characters=(
                settings.context_max_single_message_characters
            ),
            max_attachments=settings.context_max_attachments,
            builder_version=settings.context_builder_version,
            selection_policy_version=settings.context_selection_policy_version,
        ),
        runs_root=settings.codex_runs_root,
        manual_review_threshold=settings.message_analysis_manual_review_threshold,
        lease_seconds=settings.agent_run_lease_seconds,
        default_definition=build_message_judgement_definition(
            timeout_seconds=settings.codex_run_timeout_seconds
        ),
    )
    result = await handler.execute(
        AnalyseFeishuMessageCommand(
            message_id=message_id,
            actor_id=actor_id,
            actor_source=actor_source,
            correlation_id=correlation_id,
            force_new_run=force_new_run,
            recover_interrupted_run=recover_interrupted_run,
            worker_id=worker_id,
        )
    )
    return {
        "messageId": str(result.message_id),
        "agentRunId": str(result.agent_run_id),
        "status": result.status.value,
        "candidateId": str(result.candidate_id) if result.candidate_id else None,
        "idempotentReplay": result.idempotent_replay,
    }


@celery_app.task(
    bind=True,
    name="feishu.process_message",
    max_retries=2,
)  # type: ignore[untyped-decorator]
def process_feishu_message(
    task: Any,
    message_id: str,
    actor_id: str = "feishu-connector",
    actor_source: str = "integration",
    correlation_id: str = "",
    *,
    force_new_run: bool = False,
    recover_interrupted_run: bool = False,
) -> dict[str, str | bool | None]:
    settings = get_settings()
    correlation = correlation_id or f"feishu-analysis:{message_id}"
    parsed_message_id = UUID(message_id)
    try:
        recover_interrupted = bool(
            recover_interrupted_run
            or int(task.request.retries)
            or (task.request.delivery_info or {}).get("redelivered", False)
        )
        return asyncio.run(
            _analyse_feishu_message(
                parsed_message_id,
                actor_id=actor_id,
                actor_source=actor_source,
                correlation_id=correlation,
                force_new_run=force_new_run,
                recover_interrupted_run=recover_interrupted,
                worker_id=str(getattr(task.request, "hostname", "") or "celery-worker"),
            )
        )
    except (AgentRuntimeError, MessageAnalysisError) as exc:
        if not exc.retryable:
            raise
        retries = int(task.request.retries)
        countdown = min(
            settings.message_analysis_retry_base_seconds * (2**retries),
            settings.message_analysis_retry_max_seconds,
        )
        raise task.retry(exc=exc, countdown=countdown) from exc
    except Exception as exc:
        # Short database transactions can fail before or after the external
        # process. A redelivery is marked as recovery so an interrupted RUNNING
        # row is converted into the next auditable attempt instead of remaining
        # stuck indefinitely.
        retries = int(task.request.retries)
        countdown = min(
            settings.message_analysis_retry_base_seconds * (2**retries),
            settings.message_analysis_retry_max_seconds,
        )
        raise task.retry(exc=exc, countdown=countdown) from exc
