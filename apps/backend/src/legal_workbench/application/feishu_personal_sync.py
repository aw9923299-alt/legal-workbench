from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from legal_workbench.application.commands import IngestFeishuEventCommand
from legal_workbench.application.feishu_documents import extract_feishu_document_links
from legal_workbench.application.message_analysis_policy import (
    POLICY_VERSION,
    MessageAnalysisPolicy,
)
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.application.results import FeishuEventIngestedResult
from legal_workbench.domain.entities import FeishuSyncCheckpoint, IntegrationScope
from legal_workbench.domain.enums import (
    IntegrationIdentityType,
    IntegrationScopeStatus,
    IntegrationSyncMode,
)
from legal_workbench.domain.errors import DomainValidationError
from legal_workbench.integrations.feishu_local_connector import LocalFeishuRecord
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


class PersonalAttachmentSync(Protocol):
    async def download_attachments(self, message_id: UUID) -> None: ...


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

    async def list_thread_messages(
        self,
        *,
        authorization_id: UUID,
        thread_id: str,
        page_token: str | None,
    ) -> UserMessagePage: ...


@dataclass(frozen=True, slots=True)
class PersonalSyncResult:
    scope_id: UUID
    ingested_count: int
    claimed_at: datetime
    window_start: datetime
    window_end: datetime
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class _SyncLease:
    owner: str
    fence: int
    claimed_at: datetime
    window_start: datetime
    window_end: datetime


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
        analysis_policy_version: str = POLICY_VERSION,
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
        event_id = (
            f"uat:{tenant_key}:{message_id}:{timestamp}:{analysis_policy_version}"
        )
        payload: dict[str, object] = {
            "schema": "2.0",
            "source": "user_history_sync",
            "source_channel": "user_api",
            "provenance": {
                "connector": "official_user_api",
                "externalMessageId": message_id,
            },
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


class LocalMessageIngestionAdapter:
    def __init__(self, handler: IngestionHandler) -> None:
        self._handler = handler

    async def ingest(
        self,
        *,
        record: LocalFeishuRecord,
        tenant_key: str,
        analysis_disposition: str,
        correlation_id: str,
    ) -> FeishuEventIngestedResult:
        account_hash = hashlib.sha256(record.account_id.encode("utf-8")).hexdigest()[:16]
        event_id = (
            f"local:{account_hash}:{record.chat_id}:{record.message_id}:"
            f"{record.version}:{POLICY_VERSION}"
        )
        payload: dict[str, object] = {
            "schema": "2.0-local",
            "source": "local_feishu_connector",
            "source_channel": "local_client",
            "analysis_disposition": analysis_disposition,
            "analysis_policy_version": POLICY_VERSION,
            "provenance": {
                "connector": "local_feishu",
                "databasePathHash": record.database_path_hash,
                "contentHash": hashlib.sha256(
                    json.dumps(
                        record.content,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            },
            "header": {
                "event_id": event_id,
                "event_type": "im.message.receive_v1",
                "tenant_key": tenant_key,
            },
            "event": {
                "sender": {
                    "sender_id": {"open_id": record.sender_id or ""},
                    "sender_type": "user",
                },
                "message": {
                    "message_id": record.message_id,
                    "chat_id": record.chat_id,
                    "thread_id": record.thread_id,
                    "parent_id": record.parent_id,
                    "root_id": record.root_id,
                    "message_type": record.message_type,
                    "content": record.content,
                    "create_time": record.create_time,
                    "update_time": record.update_time,
                    "mentions": [],
                },
            },
        }
        return await self._handler.execute(
            IngestFeishuEventCommand(
                actor_id="feishu-local-connector",
                correlation_id=correlation_id,
                event_id=event_id,
                event_type="im.message.receive_v1",
                tenant_key=tenant_key,
                app_id=None,
                schema_version="2.0-local",
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
        attachment_sync: PersonalAttachmentSync | None = None,
        lease_duration: timedelta = timedelta(minutes=5),
    ) -> None:
        self._uow_factory = uow_factory
        self._user_client = user_client
        self._ingestion_adapter = ingestion_adapter
        self._overlap = overlap
        self._clock = clock
        self._analysis_policy = analysis_policy or MessageAnalysisPolicy()
        self._document_sync = document_sync
        self._attachment_sync = attachment_sync
        self._lease_duration = lease_duration

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
        lease = await self._claim_lease(scope)
        ingested_count = 0
        seen_message_ids: set[str] = set()
        fetched_thread_ids: set[str] = set()
        page_token: str | None = None
        try:
            while True:
                page = await self._user_client.list_messages(
                    authorization_id=scope.authorization_id,
                    chat_id=scope.external_scope_id,
                    start_time=lease.window_start,
                    end_time=lease.window_end,
                    page_token=page_token,
                )
                for raw_message in page.items:
                    ingested_count += await self._ingest_raw_message(
                        raw_message=raw_message,
                        scope=scope,
                        tenant_key=tenant_key,
                        authorization_open_id=authorization_open_id,
                        seen_message_ids=seen_message_ids,
                    )
                thread_ids = {
                    str(value.get("thread_id") or "").strip() for value in page.items
                }
                for thread_id in sorted(thread_ids - {""} - fetched_thread_ids):
                    thread_page_token: str | None = None
                    while True:
                        thread_page = await self._user_client.list_thread_messages(
                            authorization_id=scope.authorization_id,
                            thread_id=thread_id,
                            page_token=thread_page_token,
                        )
                        for raw_message in thread_page.items:
                            ingested_count += await self._ingest_raw_message(
                                raw_message=raw_message,
                                scope=scope,
                                tenant_key=tenant_key,
                                authorization_open_id=authorization_open_id,
                                seen_message_ids=seen_message_ids,
                            )
                        thread_page_token = thread_page.next_page_token
                        await self._renew_lease(
                            scope=scope,
                            lease=lease,
                            page_token=page_token,
                        )
                        if thread_page_token is None:
                            break
                    fetched_thread_ids.add(thread_id)
                page_token = page.next_page_token
                await self._renew_lease(
                    scope=scope,
                    lease=lease,
                    page_token=page_token,
                )
                if page_token is None:
                    break
            await self._succeed_lease(scope=scope, lease=lease)
        except Exception:
            await self._fail_lease(scope=scope, lease=lease)
            raise
        return PersonalSyncResult(
            scope_id=scope.id,
            ingested_count=ingested_count,
            claimed_at=lease.claimed_at,
            window_start=lease.window_start,
            window_end=lease.window_end,
            completed_at=self._clock_now(),
        )

    def _clock_now(self) -> datetime:
        now = self._clock()  # type: ignore[operator]
        if not isinstance(now, datetime):
            raise RuntimeError("Clock must return a datetime")
        return now

    async def _claim_lease(self, scope: IntegrationScope) -> _SyncLease:
        authorization_id = scope.authorization_id
        if authorization_id is None:
            raise DomainValidationError("A user authorization is required for sync.")
        now = self._clock_now()
        owner = uuid4().hex
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation="feishu_personal_sync_lease",
                key=f"{authorization_id}:{scope.id}",
            )
            checkpoint = await uow.feishu_personal_sync.get_checkpoint_for_update(
                authorization_id=authorization_id,
                scope_id=scope.id,
            )
            created = checkpoint is None
            if checkpoint is None:
                checkpoint = FeishuSyncCheckpoint(
                    id=uuid4(),
                    authorization_id=authorization_id,
                    scope_id=scope.id,
                )
            fence = checkpoint.claim(
                owner=owner,
                expires_at=now + self._lease_duration,
                now=now,
            )
            window_start = (
                checkpoint.watermark - self._overlap
                if checkpoint.watermark is not None
                else now - timedelta(days=scope.backfill_days)
            )
            if created:
                await uow.feishu_personal_sync.add_checkpoint(checkpoint)
            else:
                await uow.feishu_personal_sync.save_checkpoint(checkpoint)
            await uow.commit()
        return _SyncLease(
            owner=owner,
            fence=fence,
            claimed_at=now,
            window_start=window_start,
            window_end=now,
        )

    async def _renew_lease(
        self,
        *,
        scope: IntegrationScope,
        lease: _SyncLease,
        page_token: str | None,
    ) -> None:
        authorization_id = scope.authorization_id
        assert authorization_id is not None
        now = self._clock_now()
        async with self._uow_factory() as uow:
            checkpoint = await uow.feishu_personal_sync.get_checkpoint_for_update(
                authorization_id=authorization_id,
                scope_id=scope.id,
            )
            if checkpoint is None:
                raise DomainValidationError("sync_lease_lost")
            checkpoint.renew(
                owner=lease.owner,
                fence=lease.fence,
                page_token=page_token,
                expires_at=now + self._lease_duration,
                now=now,
            )
            await uow.feishu_personal_sync.save_checkpoint(checkpoint)
            await uow.commit()

    async def _succeed_lease(
        self, *, scope: IntegrationScope, lease: _SyncLease
    ) -> None:
        authorization_id = scope.authorization_id
        assert authorization_id is not None
        now = self._clock_now()
        async with self._uow_factory() as uow:
            checkpoint = await uow.feishu_personal_sync.get_checkpoint_for_update(
                authorization_id=authorization_id,
                scope_id=scope.id,
            )
            if checkpoint is None:
                raise DomainValidationError("sync_lease_lost")
            checkpoint.succeed(
                owner=lease.owner,
                fence=lease.fence,
                watermark=lease.window_end,
                now=now,
            )
            await uow.feishu_personal_sync.save_checkpoint(checkpoint)
            await uow.commit()

    async def _fail_lease(
        self, *, scope: IntegrationScope, lease: _SyncLease
    ) -> None:
        authorization_id = scope.authorization_id
        assert authorization_id is not None
        now = self._clock_now()
        try:
            async with self._uow_factory() as uow:
                checkpoint = await uow.feishu_personal_sync.get_checkpoint_for_update(
                    authorization_id=authorization_id,
                    scope_id=scope.id,
                )
                if checkpoint is None:
                    return
                checkpoint.fail(
                    owner=lease.owner,
                    fence=lease.fence,
                    error_code="sync_failed",
                    now=now,
                )
                await uow.feishu_personal_sync.save_checkpoint(checkpoint)
                await uow.commit()
        except DomainValidationError as exc:
            if str(exc) != "sync_lease_lost":
                raise

    async def _ingest_raw_message(
        self,
        *,
        raw_message: dict[str, object],
        scope: IntegrationScope,
        tenant_key: str,
        authorization_open_id: str,
        seen_message_ids: set[str],
    ) -> int:
        external_message_id = str(raw_message.get("message_id") or "").strip()
        if not external_message_id or external_message_id in seen_message_ids:
            return 0
        seen_message_ids.add(external_message_id)
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
            correlation_id=(
                f"feishu-user-sync:{scope.id}:{_message_timestamp(raw_message)}"
            ),
        )
        if self._document_sync is not None and ingested.message_id is not None:
            authorization_id = scope.authorization_id
            assert authorization_id is not None
            body = raw_message.get("body")
            body_object = body if isinstance(body, dict) else {}
            content = str(body_object.get("content", raw_message.get("content", "")))
            for link in extract_feishu_document_links(content):
                if link.document_type != "docx":
                    continue
                await self._document_sync.sync_document(
                    authorization_id=authorization_id,
                    document_token=link.token,
                    document_type=link.document_type,
                    title=None,
                    source_url=link.url,
                    source_message_id=ingested.message_id,
                )
        if self._attachment_sync is not None and ingested.message_id is not None:
            await self._attachment_sync.download_attachments(ingested.message_id)
        return 1
