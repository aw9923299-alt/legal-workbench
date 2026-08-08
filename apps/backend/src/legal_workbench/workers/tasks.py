import asyncio
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

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
from legal_workbench.application.feishu_documents import (
    FeishuDocumentSyncService,
    FeishuFolderSubscriptionService,
    FeishuFolderSyncService,
)
from legal_workbench.application.feishu_handlers import IngestFeishuEventHandler
from legal_workbench.application.feishu_personal_sync import (
    PersonalMessageSyncService,
    UserMessageIngestionAdapter,
)
from legal_workbench.application.feishu_user_auth import FeishuUserTokenProvider
from legal_workbench.application.message_analysis import (
    AnalyseFeishuMessageCommand,
    AnalyseFeishuMessageHandler,
    MessageAnalysisError,
)
from legal_workbench.application.setup import execute_codex_setup_check
from legal_workbench.config import get_settings
from legal_workbench.infrastructure.celery_app import celery_app
from legal_workbench.infrastructure.outbox import OutboxDispatcher
from legal_workbench.infrastructure.secrets import LocalSecretProvider
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from legal_workbench.integrations.document_extractors import (
    IsolatedExtractionProcessRunner,
)
from legal_workbench.integrations.feishu_user_client import FeishuUserClient
from legal_workbench.integrations.feishu_user_oauth import FeishuOAuthHttpClient


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


async def _sync_personal_feishu_scopes() -> dict[str, object]:
    settings = get_settings()
    if not settings.enable_real_feishu:
        return {"state": "not_executed", "scopeCount": 0, "failedScopeIds": []}
    uow_factory = SqlAlchemyUnitOfWorkFactory()
    secret_provider = LocalSecretProvider(settings.setup_secret_root)
    async with uow_factory() as uow:
        app_id_setting = await uow.setup.get_setting("feishu.app_id")
        credential = await uow.setup.get_credential(
            provider="feishu", credential_kind="app_secret"
        )
        scopes = await uow.setup.list_scopes(provider="feishu")
        authorizations = await uow.feishu_user_authorizations.list_authorizations()
        folder_subscriptions = (
            await uow.documents.list_feishu_document_subscriptions(active_only=True)
        )
    app_id = (
        str(app_id_setting.value)
        if app_id_setting is not None
        else str(settings.feishu_app_id or "")
    ).strip()
    app_secret = str(settings.feishu_app_secret or "").strip()
    if not app_secret and credential and credential.secret_ref:
        app_secret = secret_provider.read(credential.secret_ref)
    if not app_id or not app_secret:
        return {
            "state": "not_executed",
            "scopeCount": 0,
            "failedScopeIds": [],
            "errorCode": "feishu_app_credentials_missing",
        }
    authorizations_by_id = {value.id: value for value in authorizations}
    eligible = [
        value
        for value in scopes
        if value.identity_type.value == "user"
        and value.status.value == "allowed"
        and value.authorization_id in authorizations_by_id
    ]
    failed: list[str] = []
    failed_folder_subscriptions: list[str] = []
    ingested = 0
    synchronized_documents = 0
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.feishu_request_timeout_seconds)
    ) as http_client:
        oauth_client = FeishuOAuthHttpClient(
            app_id=app_id,
            app_secret=app_secret,
            http_client=http_client,
            base_url=settings.feishu_api_base_url.removesuffix("/open-apis"),
        )
        user_client = FeishuUserClient(
            token_provider=FeishuUserTokenProvider(
                uow_factory,
                oauth_client=oauth_client,
                secret_provider=secret_provider,
            ),
            http_client=http_client,
            base_url=settings.feishu_api_base_url,
        )
        service = PersonalMessageSyncService(
            uow_factory,
            user_client=user_client,
            ingestion_adapter=UserMessageIngestionAdapter(
                IngestFeishuEventHandler(uow_factory)
            ),
            overlap=timedelta(minutes=settings.feishu_user_sync_overlap_minutes),
            document_sync=FeishuDocumentSyncService(
                uow_factory,
                client=user_client,
            ),
        )
        folder_service = FeishuFolderSubscriptionService(
            uow_factory,
            folder_sync=FeishuFolderSyncService(
                client=user_client,
                document_sync=FeishuDocumentSyncService(
                    uow_factory,
                    client=user_client,
                ),
            ),
        )
        for scope in eligible:
            assert scope.authorization_id is not None
            authorization = authorizations_by_id[scope.authorization_id]
            try:
                result = await service.sync_scope(
                    scope=scope,
                    tenant_key=authorization.tenant_key,
                    authorization_open_id=authorization.open_id,
                )
                ingested += result.ingested_count
            except Exception:
                failed.append(str(scope.id))
        for subscription in folder_subscriptions:
            try:
                folder_result = await folder_service.sync_subscription(subscription.id)
                synchronized_documents += folder_result.discovered_documents
            except Exception:
                failed_folder_subscriptions.append(str(subscription.id))
    return {
        "state": (
            "partial" if failed or failed_folder_subscriptions else "completed"
        ),
        "scopeCount": len(eligible),
        "ingestedCount": ingested,
        "failedScopeIds": failed,
        "folderSubscriptionCount": len(folder_subscriptions),
        "synchronizedDocumentCount": synchronized_documents,
        "failedFolderSubscriptionIds": failed_folder_subscriptions,
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
