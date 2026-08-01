from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from legal_workbench.application.commands import IngestFeishuEventCommand
from legal_workbench.application.feishu_handlers import IngestFeishuEventHandler
from legal_workbench.application.idempotency import request_hash, require_matching_replay
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.config import Settings
from legal_workbench.domain.entities import AuditEvent, IdempotencyRecord, IntegrationConnection
from legal_workbench.domain.enums import (
    AttachmentDownloadStatus,
    IntegrationConnectionMode,
    IntegrationConnectionStatus,
)
from legal_workbench.integrations.feishu_client import FeishuApiClient, FeishuApiError
from legal_workbench.integrations.feishu_event_sources import (
    EventSourceHealth,
    EventSourceStatus,
)


def _connection_mode(settings: Settings) -> IntegrationConnectionMode:
    return IntegrationConnectionMode(settings.feishu_event_source.value)


def _connection_status(status: EventSourceStatus) -> IntegrationConnectionStatus:
    return IntegrationConnectionStatus(status.value)


def _safe_file_name(value: str) -> str:
    base = Path(value).name.strip() or "attachment"
    return re.sub(r"[^\w.()\-\u4e00-\u9fff]+", "_", base)[:240]


def _seconds_to_millis(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return f"{text}000" if len(text) <= 10 else text


class FeishuOperationsService:
    def __init__(
        self,
        *,
        settings: Settings,
        uow_factory: UnitOfWorkFactory,
        client: FeishuApiClient | None = None,
    ) -> None:
        self._settings = settings
        self._uow_factory = uow_factory
        self._client = client or FeishuApiClient(settings)

    async def get_connection(self) -> IntegrationConnection:
        mode = _connection_mode(self._settings)
        async with self._uow_factory() as uow:
            existing = await uow.feishu.get_connection(
                integration_type="feishu", connection_mode=mode
            )
        if existing is not None:
            return existing
        return IntegrationConnection(
            id=uuid4(),
            integration_type="feishu",
            connection_mode=mode,
            status=(
                IntegrationConnectionStatus.DISCONNECTED
                if self._settings.enable_real_feishu
                else IntegrationConnectionStatus.DISABLED
            ),
        )

    async def persist_health(self, health: EventSourceHealth) -> IntegrationConnection:
        connection = await self.get_connection()
        connection.status = _connection_status(health.status)
        connection.last_connected_at = health.last_connected_at
        connection.last_disconnected_at = health.last_disconnected_at
        connection.last_event_at = health.last_event_at
        connection.last_error_code = health.last_error_code
        connection.last_error_message = health.last_error_message
        connection.reconnect_count = health.reconnect_count
        connection.updated_at = datetime.now(UTC)
        async with self._uow_factory() as uow:
            await uow.feishu.save_connection(connection)
            await uow.commit()
        return connection

    async def record_event_received(self) -> None:
        connection = await self.get_connection()
        now = datetime.now(UTC)
        connection.status = IntegrationConnectionStatus.CONNECTED
        connection.last_connected_at = connection.last_connected_at or now
        connection.last_event_at = now
        connection.updated_at = connection.last_event_at
        async with self._uow_factory() as uow:
            await uow.feishu.save_connection(connection)
            await uow.commit()

    async def request_reconnect(
        self, *, actor_id: str, correlation_id: str, idempotency_key: str
    ) -> None:
        connection = await self.get_connection()
        connection.status = IntegrationConnectionStatus.STARTING
        connection.last_error_code = "MANUAL_RECONNECT_REQUESTED"
        connection.last_error_message = "Manual reconnect requested through the API."
        connection.updated_at = datetime.now(UTC)
        digest = request_hash({"operation": "feishu_reconnect"})
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation="feishu_reconnect", key=idempotency_key
            )
            replay = require_matching_replay(
                await uow.idempotency.get(
                    operation="feishu_reconnect", key=idempotency_key
                ),
                expected_hash=digest,
                idempotency_key=idempotency_key,
            )
            if replay is not None:
                return
            await uow.feishu.save_connection(connection)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="integration_connection",
                    aggregate_id=connection.id,
                    event_type="feishu_reconnect_requested",
                    actor_id=actor_id,
                    actor_source="authenticated_user",
                    payload={"connectionMode": connection.connection_mode.value},
                    correlation_id=correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation="feishu_reconnect",
                    idempotency_key=idempotency_key,
                    request_hash=digest,
                    response_payload={"accepted": True},
                )
            )
            await uow.commit()

    async def reconcile(
        self,
        *,
        actor_id: str,
        correlation_id: str,
        idempotency_key: str,
        window_minutes: int | None = None,
    ) -> dict[str, object]:
        window = max(1, min(window_minutes or self._settings.feishu_reconcile_window_minutes, 1440))
        digest = request_hash({"operation": "feishu_reconcile", "windowMinutes": window})
        async with self._uow_factory() as uow:
            existing_record = require_matching_replay(
                await uow.idempotency.get(
                    operation="feishu_reconcile", key=idempotency_key
                ),
                expected_hash=digest,
                idempotency_key=idempotency_key,
            )
        if existing_record is not None:
            return dict(existing_record.response_payload)
        now = datetime.now(UTC)
        start = now - timedelta(minutes=window)
        ingested = 0
        duplicates = 0
        status = "local_only"
        detail = "Remote reconciliation was not attempted."

        if self._settings.enable_real_feishu and self._settings.feishu_reconcile_chat_ids:
            status = "completed"
            detail = "Configured chat windows were queried; PostgreSQL absorbed duplicates."
            for chat_id in self._settings.feishu_reconcile_chat_ids:
                items = await self._client.list_chat_messages(
                    chat_id=chat_id, start_time=start, end_time=now
                )
                for item in items:
                    payload, event_id, event_type = await self._reconcile_payload(chat_id, item)
                    ingest_result = await IngestFeishuEventHandler(
                        self._uow_factory
                    ).execute(
                        IngestFeishuEventCommand(
                            actor_id=actor_id,
                            correlation_id=correlation_id,
                            event_id=event_id,
                            event_type=event_type,
                            tenant_key=self._settings.feishu_tenant_key,
                            app_id=self._settings.feishu_app_id,
                            schema_version="2.0-reconcile",
                            raw_payload=payload,
                        )
                    )
                    if ingest_result.duplicate:
                        duplicates += 1
                    else:
                        ingested += 1
        elif self._settings.enable_real_feishu:
            status = "partial"
            detail = "No FEISHU_RECONCILE_CHAT_IDS configured; only database recovery is available."

        connection = await self.get_connection()
        connection.last_reconcile_at = now
        connection.last_reconcile_status = status
        connection.last_reconcile_message = detail
        connection.updated_at = now
        reconcile_result: dict[str, object] = {
            "status": status,
            "windowMinutes": window,
            "ingested": ingested,
            "duplicates": duplicates,
            "message": detail,
        }
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation="feishu_reconcile", key=idempotency_key
            )
            concurrent_replay = require_matching_replay(
                await uow.idempotency.get(
                    operation="feishu_reconcile", key=idempotency_key
                ),
                expected_hash=digest,
                idempotency_key=idempotency_key,
            )
            if concurrent_replay is not None:
                return dict(concurrent_replay.response_payload)
            await uow.feishu.save_connection(connection)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="integration_connection",
                    aggregate_id=connection.id,
                    event_type="feishu_reconcile_completed",
                    actor_id=actor_id,
                    actor_source="authenticated_user",
                    payload={
                        "status": status,
                        "windowMinutes": window,
                        "chatCount": len(self._settings.feishu_reconcile_chat_ids),
                        "ingested": ingested,
                        "duplicates": duplicates,
                    },
                    correlation_id=correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation="feishu_reconcile",
                    idempotency_key=idempotency_key,
                    request_hash=digest,
                    response_payload=reconcile_result,
                )
            )
            await uow.commit()
        return reconcile_result

    async def download_attachments(self, message_id: UUID) -> None:
        if not self._settings.enable_real_feishu:
            return
        async with self._uow_factory() as uow:
            message = await uow.feishu.get_message_by_id(message_id)
            attachments = list(await uow.feishu.list_pending_attachments(message_id))
        if message is None:
            return
        for attachment in attachments:
            attachment.download_status = AttachmentDownloadStatus.DOWNLOADING
            attachment.updated_at = datetime.now(UTC)
            async with self._uow_factory() as uow:
                await uow.feishu.save_attachment(attachment)
                await uow.commit()
            try:
                resource_type = "image" if message.message_type == "image" else "file"
                content, mime_type, size = await self._client.download_message_resource(
                    message_id=message.message_id,
                    file_key=attachment.file_key,
                    resource_type=resource_type,
                )
                if len(content) > self._settings.feishu_attachment_max_bytes:
                    raise FeishuApiError("Attachment exceeds the configured download limit.")
                directory = (
                    Path(self._settings.feishu_attachment_root).resolve()
                    / (message.tenant_key or "default")
                    / str(message.id)
                )
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                target = directory / f"{attachment.id}-{_safe_file_name(attachment.file_name)}"
                target.write_bytes(content)
                target.chmod(0o600)
                attachment.sha256 = sha256(content).hexdigest()
                attachment.local_path = str(target)
                attachment.mime_type = attachment.mime_type or mime_type
                attachment.size = attachment.size or size
                attachment.download_status = AttachmentDownloadStatus.DOWNLOADED
                attachment.download_error = None
            except Exception as exc:
                attachment.download_status = AttachmentDownloadStatus.FAILED
                attachment.download_error = str(exc)[:1000]
            attachment.updated_at = datetime.now(UTC)
            async with self._uow_factory() as uow:
                await uow.feishu.save_attachment(attachment)
                await uow.commit()

    async def _reconcile_payload(
        self, chat_id: str, item: dict[str, object]
    ) -> tuple[dict[str, object], str, str]:
        message_id = str(item.get("message_id") or "").strip()
        if not message_id:
            raise FeishuApiError("Reconciled message omitted message_id.")
        tenant_key = self._settings.feishu_tenant_key or ""
        async with self._uow_factory() as uow:
            existing = await uow.feishu.get_message(
                tenant_key=tenant_key, message_id=message_id
            )
        event_type = (
            "im.message.message_edited_v1"
            if existing is not None
            else "im.message.receive_v1"
        )
        update_time = _seconds_to_millis(item.get("update_time"))
        create_time = _seconds_to_millis(item.get("create_time"))
        sender = item.get("sender")
        sender_object = sender if isinstance(sender, dict) else {}
        sender_id = str(sender_object.get("id") or sender_object.get("open_id") or "")
        message = dict(item)
        message["chat_id"] = chat_id
        message["message_type"] = str(
            item.get("message_type") or item.get("msg_type") or "unknown"
        )
        message["create_time"] = create_time
        message["update_time"] = update_time
        reconcile_event_id = (
            f"reconcile:{tenant_key}:{message_id}:{update_time or create_time or '0'}"
        )
        payload: dict[str, object] = {
            "schema": "2.0-reconcile",
            "header": {
                "event_id": reconcile_event_id,
                "event_type": event_type,
                "tenant_key": tenant_key,
                "app_id": self._settings.feishu_app_id or "",
                "create_time": create_time or update_time,
            },
            "event": {
                "sender": {
                    "sender_id": {"open_id": sender_id},
                    "sender_type": str(sender_object.get("sender_type") or "user"),
                },
                "message": message,
            },
        }
        header = payload["header"]
        assert isinstance(header, dict)
        return payload, str(header["event_id"]), event_type
