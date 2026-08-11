import asyncio
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from legal_workbench.agents.codex_cli import CodexCliRuntime
from legal_workbench.agents.codex_health import CodexRuntimeHealthChecker
from legal_workbench.agents.definitions import build_message_judgement_definition
from legal_workbench.agents.runtime import AgentRuntimeError, DisabledAgentRuntime
from legal_workbench.application.analysis_recovery import AnalysisRecoveryService
from legal_workbench.application.context_snapshots import ContextSnapshotBuilder
from legal_workbench.application.document_extraction import DocumentExtractionService
from legal_workbench.application.evaluations import (
    EvaluationFixtureCase,
    RealCodexEvaluationExecutor,
)
from legal_workbench.application.knowledge import KnowledgeRetrievalService
from legal_workbench.application.legal_agent_orchestrator import (
    LegalAgentOrchestrator,
    LegalAgentTrigger,
)
from legal_workbench.application.legal_context import LegalContextBuilder
from legal_workbench.application.matter_continuity import MatterContinuityResolver
from legal_workbench.application.message_analysis import (
    AnalyseFeishuMessageCommand,
    AnalyseFeishuMessageHandler,
    MessageAnalysisError,
)
from legal_workbench.application.setup import execute_codex_setup_check
from legal_workbench.application.token_budget import KnowledgeBudget
from legal_workbench.config import get_settings
from legal_workbench.domain.errors import DomainValidationError
from legal_workbench.infrastructure.celery_app import celery_app
from legal_workbench.infrastructure.feishu_personal_runtime import (
    PersonalSyncRuntimeFactory,
)
from legal_workbench.infrastructure.outbox import OutboxDispatcher
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from legal_workbench.integrations.document_extractors import (
    IsolatedExtractionProcessRunner,
)


class _CodexSmokeExecutor:
    def __init__(self, runtime: CodexCliRuntime) -> None:
        self._executor = RealCodexEvaluationExecutor(runtime)

    async def execute(self, *, check_run_id: UUID) -> tuple[str | None, str | None]:
        text = "请判断这条合成测试消息是否属于合同审核请求。"
        execution = await self._executor.execute(
            EvaluationFixtureCase(
                case_key="setup_contract_smoke",
                case_version=1,
                input_payload={
                    "messageId": "setup-smoke-contract-001",
                    "messageType": "text",
                    "text": text,
                },
                expected_output={
                    "legalRelevance": "relevant",
                    "messageRole": "new_request",
                    "candidateCreated": True,
                    "category": "contract",
                    "deadlines": [],
                    "facts": [],
                    "inferences": [],
                    "missingInformation": [],
                },
                content_hash=sha256(text.encode()).hexdigest(),
            ),
            evaluation_run_id=check_run_id,
        )
        return execution.runtime_version, execution.failure_code


@celery_app.task(name="system.ping")  # type: ignore[untyped-decorator]
def ping(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "ok", "payload": payload or {}}


@celery_app.task(name="system.scheduler_heartbeat")  # type: ignore[untyped-decorator]
def scheduler_heartbeat() -> dict[str, str]:
    from datetime import UTC, datetime

    from redis import Redis

    value = datetime.now(UTC).isoformat()
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        client.set("legal-workbench:scheduler-heartbeat", value, ex=90)
    finally:
        client.close()
    return {"heartbeatAt": value}


@celery_app.task(name="outbox.publish")  # type: ignore[untyped-decorator]
def publish_outbox() -> dict[str, int]:
    count = asyncio.run(OutboxDispatcher().publish_batch())
    return {"claimed": count}


async def _orchestrate_legal_agents(
    payload: dict[str, object], correlation_id: str
) -> dict[str, object]:
    orchestrator = _build_legal_agent_orchestrator()
    work_item_id = payload.get("workItemId")
    analysis_date_value = payload.get("analysisEffectiveDate")
    historical_value = payload.get("historicalAsOf")
    result = await orchestrator.execute(
        LegalAgentTrigger(
            matter_id=UUID(str(payload["matterId"])),
            work_item_id=UUID(str(work_item_id)) if work_item_id else None,
            context_snapshot_id=UUID(str(payload["contextSnapshotId"])),
            objective=str(payload["objective"]),
            actor_id=str(payload.get("actorId") or "local-legal-user"),
            correlation_id=correlation_id,
            idempotency_key=str(payload["idempotencyKey"]),
            special_requirements=(
                str(payload["specialRequirements"])
                if payload.get("specialRequirements")
                else None
            ),
            specialist_only=(
                str(payload["specialistOnly"])
                if payload.get("specialistOnly")
                else None
            ),
            jurisdiction=str(payload.get("jurisdiction") or "CN"),
            analysis_effective_date=(
                date.fromisoformat(str(analysis_date_value))
                if analysis_date_value
                else None
            ),
            historical_as_of=(
                date.fromisoformat(str(historical_value)) if historical_value else None
            ),
        )
    )
    return {
        "planId": str(result.plan_id),
        "status": result.status.value,
        "planningRunId": str(result.planning_run_id) if result.planning_run_id else None,
        "synthesisRunId": str(result.synthesis_run_id) if result.synthesis_run_id else None,
        "artifactId": str(result.artifact_id) if result.artifact_id else None,
        "reviewPackageId": (
            str(result.review_package_id) if result.review_package_id else None
        ),
        "idempotentReplay": result.idempotent_replay,
        "correlationId": correlation_id,
    }


def _build_legal_agent_orchestrator() -> LegalAgentOrchestrator:
    settings = get_settings()
    uow_factory = SqlAlchemyUnitOfWorkFactory()
    runtime = (
        CodexCliRuntime(runs_root=settings.codex_runs_root)
        if settings.enable_real_codex
        else DisabledAgentRuntime()
    )
    return LegalAgentOrchestrator(
        uow_factory,
        runtime,
        LegalContextBuilder(
            KnowledgeRetrievalService(
                uow_factory,
                default_budget=KnowledgeBudget(
                    max_chunks=settings.legal_knowledge_max_chunks,
                    max_tokens=settings.legal_knowledge_max_tokens,
                    max_single_chunk_tokens=(
                        settings.legal_knowledge_max_single_chunk_tokens
                    ),
                ),
            )
        ),
        runs_root=settings.codex_runs_root,
        lease_seconds=settings.agent_run_lease_seconds,
        worker_id="legal-agent-worker",
        timeout_seconds=settings.codex_run_timeout_seconds,
        analysis_date_provider=lambda: datetime.now(
            ZoneInfo(settings.local_timezone)
        ).date(),
    )


@celery_app.task(name="legal_agents.orchestrate")  # type: ignore[untyped-decorator]
def orchestrate_legal_agents(
    payload: dict[str, object], correlation_id: str = ""
) -> dict[str, object]:
    correlation = correlation_id or str(payload.get("correlationId") or "")
    return asyncio.run(_orchestrate_legal_agents(payload, correlation))


async def _rerun_legal_agent_step(
    payload: dict[str, object], correlation_id: str
) -> dict[str, object]:
    result = await _build_legal_agent_orchestrator().rerun_step(
        plan_id=UUID(str(payload["planId"])),
        step_id=str(payload["stepId"]),
        actor_id=str(payload.get("actorId") or "local-legal-user"),
        correlation_id=correlation_id,
    )
    return {
        "planId": str(result.plan_id),
        "status": result.status.value,
        "synthesisRunId": str(result.synthesis_run_id) if result.synthesis_run_id else None,
        "artifactId": str(result.artifact_id) if result.artifact_id else None,
        "reviewPackageId": (
            str(result.review_package_id) if result.review_package_id else None
        ),
        "correlationId": correlation_id,
    }


@celery_app.task(name="legal_agents.rerun_step")  # type: ignore[untyped-decorator]
def rerun_legal_agent_step(
    payload: dict[str, object], correlation_id: str = ""
) -> dict[str, object]:
    return asyncio.run(_rerun_legal_agent_step(payload, correlation_id))


async def _recover_legal_agents(
    payload: dict[str, object], correlation_id: str
) -> dict[str, object]:
    result = await _build_legal_agent_orchestrator().recover(
        plan_id=UUID(str(payload["planId"])),
        correlation_id=correlation_id,
    )
    return {
        "planId": str(result.plan_id),
        "status": result.status.value,
        "planningRunId": str(result.planning_run_id) if result.planning_run_id else None,
        "synthesisRunId": str(result.synthesis_run_id) if result.synthesis_run_id else None,
        "artifactId": str(result.artifact_id) if result.artifact_id else None,
        "reviewPackageId": (
            str(result.review_package_id) if result.review_package_id else None
        ),
        "correlationId": correlation_id,
    }


@celery_app.task(name="legal_agents.recover")  # type: ignore[untyped-decorator]
def recover_legal_agents(
    payload: dict[str, object], correlation_id: str = ""
) -> dict[str, object]:
    return asyncio.run(_recover_legal_agents(payload, correlation_id))


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
        "legalRunsRequeued": result.legal_runs_requeued,
        "legalDeadLettered": result.legal_dead_lettered,
    }


async def _sync_personal_feishu_scopes() -> dict[str, object]:
    settings = get_settings()
    if not settings.enable_real_feishu:
        return {"state": "not_executed", "scopeCount": 0, "failedScopeIds": []}
    uow_factory = SqlAlchemyUnitOfWorkFactory()
    factory = PersonalSyncRuntimeFactory(
        settings=settings,
        uow_factory=uow_factory,
    )
    try:
        async with factory.open() as runtime:
            return await runtime.sync_all_eligible_scopes()
    except DomainValidationError:
        return {
            "state": "not_executed",
            "scopeCount": 0,
            "failedScopeIds": [],
            "errorCode": "feishu_app_credentials_missing",
        }


@celery_app.task(name="feishu.sync_personal")  # type: ignore[untyped-decorator]
def sync_personal_feishu() -> dict[str, object]:
    return asyncio.run(_sync_personal_feishu_scopes())


@celery_app.task(name="setup.codex_check")  # type: ignore[untyped-decorator]
def run_codex_setup_check(
    check_run_id: str,
    correlation_id: str = "",
) -> dict[str, str | None]:
    settings = get_settings()
    runtime = CodexCliRuntime(runs_root=settings.codex_runs_root)
    result = asyncio.run(
        execute_codex_setup_check(
            check_run_id=UUID(check_run_id),
            uow_factory=SqlAlchemyUnitOfWorkFactory(),
            health_checker=CodexRuntimeHealthChecker(
                command=settings.codex_command,
                expected_version=settings.codex_expected_version,
                runs_root=settings.codex_runs_root,
                auth_home=settings.codex_auth_home,
            ),
            real_runtime_enabled=settings.enable_real_codex,
            smoke_executor=(_CodexSmokeExecutor(runtime) if settings.enable_real_codex else None),
        )
    )
    return {
        "checkRunId": str(result.id),
        "state": result.state,
        "errorCode": result.error_code,
        "runtimeVersion": result.runtime_version,
        "correlationId": correlation_id or result.correlation_id,
    }


@celery_app.task(
    bind=True,
    name="document.extract",
    max_retries=2,
)  # type: ignore[untyped-decorator]
def extract_document_attachment(
    task: Any,
    attachment_id: str,
    correlation_id: str = "",
) -> dict[str, str | None]:
    settings = get_settings()
    try:
        result = asyncio.run(
            DocumentExtractionService(
                SqlAlchemyUnitOfWorkFactory(),
                IsolatedExtractionProcessRunner(
                    attachment_root=Path(settings.feishu_attachment_root),
                    work_root=Path(settings.document_extraction_work_root),
                    max_file_bytes=settings.feishu_attachment_max_bytes,
                    timeout_seconds=settings.document_extraction_timeout_seconds,
                    max_output_bytes=settings.document_extraction_max_output_bytes,
                ),
            ).execute(UUID(attachment_id))
        )
        return {
            "attachmentId": str(result.attachment_id),
            "extractionId": str(result.extraction_id),
            "status": result.status.value,
            "errorCode": result.error_code,
            "correlationId": correlation_id or None,
        }
    except Exception as exc:
        retries = int(task.request.retries)
        raise task.retry(exc=exc, countdown=min(15 * (2**retries), 300)) from exc


async def _analyse_feishu_message(
    message_id: UUID,
    *,
    actor_id: str,
    actor_source: str,
    correlation_id: str,
    force_new_run: bool,
    override_recalled: bool,
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
            max_single_message_characters=(settings.context_max_single_message_characters),
            max_attachments=settings.context_max_attachments,
            max_attachment_segments=settings.context_max_attachment_segments,
            max_single_attachment_segment_characters=(
                settings.context_max_single_attachment_segment_characters
            ),
            builder_version=settings.context_builder_version,
            selection_policy_version=settings.context_selection_policy_version,
            matter_continuity_resolver=MatterContinuityResolver(),
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
            override_recalled=override_recalled,
            recover_interrupted_run=recover_interrupted_run,
            worker_id=worker_id,
        )
    )
    return {
        "messageId": str(result.message_id),
        "agentRunId": str(result.agent_run_id) if result.agent_run_id else None,
        "status": result.status.value if result.status else "no_op",
        "candidateId": str(result.candidate_id) if result.candidate_id else None,
        "idempotentReplay": result.idempotent_replay,
        "noOpReason": result.no_op_reason,
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
    override_recalled: bool = False,
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
                override_recalled=override_recalled,
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
