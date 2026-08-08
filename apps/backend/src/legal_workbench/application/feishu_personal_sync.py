from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from legal_workbench.application.commands import IngestFeishuEventCommand
from legal_workbench.application.feishu_documents import extract_feishu_document_links
from legal_workbench.application.message_analysis_policy import MessageAnalysisPolicy
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.application.results import FeishuEventIngestedResult
from legal_workbench.domain.entities import FeishuSyncCheckpoint, IntegrationScope
from legal_workbench.domain.enums import (
    IntegrationIdentityType,
    IntegrationScopeStatus,
    IntegrationSyncMode,
)
from legal_workbench.domain.errors import DomainValidationError
from legal_workbench.integrations.feishu_user_client import UserMessagePage


class IngestionHandler(Protocol):
    async def execute(
        self, command: IngestFeishuEventCommand
    ) -> FeishuEventIngestedResult: ...


class NativeDocumentLinkSync(Protocol):
    async def sync_document(
        self,
        *,
        authorization_id: UUID,
        document_token: str,
        document_type: str,
        title: str | None,
        source_url: str,
        source_message_id: UUID | None = None,
    ) -> object: ...


class PersonalMessageClient(Protocol):
    async def list_messages(
        self,
        *,
        authorization_id: UUID,
        chat_id: str,
        start_time: datetime,
        end_time: datetime,
        page_token: str | None,
    ) -> UserMessagePage: ...


@dataclass(frozen=True, slots=True)
class PersonalSyncResult:
    scope_id: UUID
    ingested_count: int
    started_at: datetime
    completed_at: datetime


def _message_timestamp(raw_message: dict[str, object]) -> str:
    return str(raw_message.get("update_time") or raw_message.get("create_time") or "0")


def _sender_payload(raw_message: dict[str, object]) -> dict[str, object]:
    sender = raw_message.get("sender")
    sender_object = sender if isinstance(sender, dict) else {}
    sender_id = str(sender_object.get("id") or "")
    id_type = str(sender_object.get("id_type") or "open_id")
    return {
        "sender_id": {id_type: sender_id},
        "sender_type": str(sender_object.get("sender_type") or "user"),
    }


class UserMessageIngestionAdapter:
    def __init__(self, handler: IngestionHandler) -> None:
        self._handler = handler

    async def ingest(
        self,
        *,
        raw_message: dict[str, object],
        tenant_key: str,
        authorization_open_id: str,
        analysis_disposition: str,
        analysis_policy_version: str = "feishu-personal-analysis-v1",
        analysis_reasons: tuple[str, ...] = (),
        correlation_id: str,
    ) -> FeishuEventIngestedResult:
        message_id = str(raw_message.get("message_id") or "").strip()
        if not message_id:
            raise DomainValidationError("A synchronized Feishu message ID is required.")
        message_type = str(
            raw_message.get("msg_type") or raw_message.get("message_type") or "unknown"
        )
        body = raw_message.get("body")
        body_object = body if isinstance(body, dict) else {}
        content = body_object.get("content", raw_message.get("content", {}))
        timestamp = _message_timestamp(raw_message)
        updated = str(raw_message.get("update_time") or "")
        created = str(raw_message.get("create_time") or "")
        is_edit = bool(updated and created and updated != created)
        event_type = (
            "im.message.message_edited_v1" if is_edit else "im.message.receive_v1"
        )
        event_id = f"uat:{tenant_key}:{message_id}:{timestamp}"
        payload: dict[str, object] = {
            "schema": "2.0",
            "source": "user_history_sync",
            "analysis_disposition": analysis_disposition,
            "analysis_policy_version": analysis_policy_version,
            "analysis_reasons": list(analysis_reasons),
            "authorization_open_id": authorization_open_id,
            "header": {
                "event_id": event_id,
                "event_type": event_type,
                "tenant_key": tenant_key,
            },
            "event": {
                "sender": _sender_payload(raw_message),
                "message": {
                    "message_id": message_id,
                    "chat_id": raw_message.get("chat_id"),
                    "thread_id": raw_message.get("thread_id"),
                    "parent_id": raw_message.get("parent_id"),
                    "root_id": raw_message.get("root_id"),
                    "message_type": message_type,
                    "content": content,
                    "mentions": raw_message.get("mentions", []),
                    "create_time": raw_message.get("create_time"),
                    "update_time": raw_message.get("update_time"),
                },
            },
        }
        return await self._handler.execute(
            IngestFeishuEventCommand(
                actor_id="feishu-user-sync",
                correlation_id=correlation_id,
                event_id=event_id,
                event_type=event_type,
                tenant_key=tenant_key,
                app_id=None,
                schema_version="2.0",
                raw_payload=payload,
            )
        )


class PersonalMessageSyncService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        user_client: PersonalMessageClient,
        ingestion_adapter: UserMessageIngestionAdapter,
        overlap: timedelta = timedelta(minutes=5),
        clock: object = lambda: datetime.now(UTC),
        analysis_policy: MessageAnalysisPolicy | None = None,
        document_sync: NativeDocumentLinkSync | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._user_client = user_client
        self._ingestion_adapter = ingestion_adapter
        self._overlap = overlap
        self._clock = clock
        self._analysis_policy = analysis_policy or MessageAnalysisPolicy()
        self._document_sync = document_sync

    async def sync_scope(
        self,
        *,
        scope: IntegrationScope,
        tenant_key: str,
        authorization_open_id: str = "",
    ) -> PersonalSyncResult:
        if (
            scope.status != IntegrationScopeStatus.ALLOWED
            or scope.sync_mode == IntegrationSyncMode.DISABLED
            or scope.identity_type != IntegrationIdentityType.USER
            or scope.authorization_id is None
        ):
            raise DomainValidationError("Only an allowed Feishu user scope can synchronize.")
        now = self._clock()  # type: ignore[operator]
        if not isinstance(now, datetime):
            raise RuntimeError("Clock must return a datetime")
        ingested_count = 0
        async with self._uow_factory() as uow:
            checkpoint = await uow.feishu_personal_sync.get_checkpoint_for_update(
                authorization_id=scope.authorization_id,
                scope_id=scope.id,
            )
            if checkpoint is None:
                checkpoint = FeishuSyncCheckpoint(
                    id=uuid4(),
                    authorization_id=scope.authorization_id,
                    scope_id=scope.id,
                )
                await uow.feishu_personal_sync.add_checkpoint(checkpoint)
            checkpoint.last_started_at = now
            start_time = (
                checkpoint.watermark - self._overlap
                if checkpoint.watermark is not None
                else now - timedelta(days=scope.backfill_days)
            )
            page_token: str | None = None
            try:
                while True:
                    page = await self._user_client.list_messages(
                        authorization_id=scope.authorization_id,
                        chat_id=scope.external_scope_id,
                        start_time=start_time,
                        end_time=now,
                        page_token=page_token,
                    )
                    for raw_message in page.items:
                        decision = self._analysis_policy.decide(
                            raw_message=raw_message,
                            scope=scope,
                            self_open_id=authorization_open_id,
                        )
                        ingested = await self._ingestion_adapter.ingest(
                            raw_message=raw_message,
                            tenant_key=tenant_key,
                            authorization_open_id=authorization_open_id,
                            analysis_disposition=decision.disposition,
                            analysis_policy_version=decision.policy_version,
                            analysis_reasons=decision.reasons,
                            correlation_id=f"feishu-user-sync:{scope.id}:{_message_timestamp(raw_message)}",
                        )
                        if self._document_sync is not None and ingested.message_id is not None:
                            body = raw_message.get("body")
                            body_object = body if isinstance(body, dict) else {}
                            content = str(
                                body_object.get("content", raw_message.get("content", ""))
                            )
                            for link in extract_feishu_document_links(content):
                                if link.document_type != "docx":
                                    continue
                                await self._document_sync.sync_document(
                                    authorization_id=scope.authorization_id,
                                    document_token=link.token,
                                    document_type=link.document_type,
                                    title=None,
                                    source_url=link.url,
                                    source_message_id=ingested.message_id,
                                )
                        ingested_count += 1
                    page_token = page.next_page_token
                    checkpoint.page_token = page_token
                    if page_token is None:
                        break
                checkpoint.succeed(watermark=now, now=now)
                await uow.feishu_personal_sync.save_checkpoint(checkpoint)
                await uow.commit()
            except Exception:
                checkpoint.fail(error_code="sync_failed", now=now)
                checkpoint.page_token = None
                await uow.feishu_personal_sync.save_checkpoint(checkpoint)
                await uow.commit()
                raise
        return PersonalSyncResult(
            scope_id=scope.id,
            ingested_count=ingested_count,
            started_at=now,
            completed_at=self._clock(),  # type: ignore[operator]
        )
