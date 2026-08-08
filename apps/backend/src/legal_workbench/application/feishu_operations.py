from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID, uuid4

from legal_workbench.application.automatic_analysis_gate import AutomaticAnalysisGate
from legal_workbench.application.commands import IngestFeishuEventCommand
from legal_workbench.application.feishu_handlers import IngestFeishuEventHandler
from legal_workbench.application.idempotency import request_hash, require_matching_replay
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.config import Settings
from legal_workbench.domain.entities import (
    AuditEvent,
    IdempotencyRecord,
    IntegrationConnection,
    OutboxEvent,
)
from legal_workbench.domain.enums import (
    AttachmentDownloadStatus,
    DocumentExtractionStatus,
    IntegrationConnectionMode,
    IntegrationConnectionStatus,
)
from legal_workbench.domain.errors import (
    InvalidStateTransitionError,
    StorageQuotaExceededError,
)
from legal_workbench.integrations.document_extractors import (
    AttachmentTooLargeError,
    sanitize_attachment_filename,
)
from legal_workbench.integrations.feishu_client import FeishuApiClient, FeishuApiError
from legal_workbench.integrations.feishu_event_sources import (
    EventSourceHealth,
    EventSourceStatus,
)
from legal_workbench.integrations.feishu_local_connector import LocalFeishuAttachment


class MessageResourceClient(Protocol):
    async def download_message_resource(
        self,
        *,
        message_id: str,
        file_key: str,
        resource_type: str,
    ) -> tuple[bytes, str, int]: ...


def _connection_mode(settings: Settings) -> IntegrationConnectionMode:
    return IntegrationConnectionMode(settings.feishu_event_source.value)


def _connection_status(status: EventSourceStatus) -> IntegrationConnectionStatus:
    return IntegrationConnectionStatus(status.value)


def _attachment_storage_usage(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
    return total


def _write_private_file(target: Path, content: bytes) -> None:
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.part")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def _download_error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.isascii() and 0 < len(code) <= 100:
        return code
    if isinstance(exc, FeishuApiError):
        return "FEISHU_ATTACHMENT_DOWNLOAD_FAILED"
    if isinstance(exc, OSError):
        return "ATTACHMENT_STORAGE_WRITE_FAILED"
    return "ATTACHMENT_DOWNLOAD_FAILED"


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
        client: MessageResourceClient | None = None,
        unavailable_under_user_identity: bool = False,
        force_metadata_only_reason: str | None = None,
        analysis_gate: AutomaticAnalysisGate | None = None,
    ) -> None:
        self._settings = settings
        self._uow_factory = uow_factory
        self._client = client or FeishuApiClient(settings)
        self._unavailable_under_user_identity = unavailable_under_user_identity
        self._force_metadata_only_reason = force_metadata_only_reason
        self._analysis_gate = analysis_gate or AutomaticAnalysisGate()

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
        if not self._settings.enable_real_feishu:
            raise InvalidStateTransitionError(
                "Real Feishu integration is disabled; reconnect was not attempted."
            )
        connection = await self.get_connection()
        connection.status = IntegrationConnectionStatus.STARTING
        connection.last_error_code = "MANUAL_RECONNECT_REQUESTED"
        connection.last_error_message = "Manual reconnect requested through the API."
        connection.updated_at = datetime.now(UTC)
        digest = request_hash({"operation": "feishu_reconnect"})
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation="feishu_reconnect", key=idempotency_key)
            replay = require_matching_replay(
                await uow.idempotency.get(operation="feishu_reconnect", key=idempotency_key),
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
                await uow.idempotency.get(operation="feishu_reconcile", key=idempotency_key),
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
                items = await cast(FeishuApiClient, self._client).list_chat_messages(
                    chat_id=chat_id, start_time=start, end_time=now
                )
                for item in items:
                    payload, event_id, event_type = await self._reconcile_payload(chat_id, item)
                    ingest_result = await IngestFeishuEventHandler(self._uow_factory).execute(
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
            await uow.lock_idempotency(operation="feishu_reconcile", key=idempotency_key)
            concurrent_replay = require_matching_replay(
                await uow.idempotency.get(operation="feishu_reconcile", key=idempotency_key),
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
        if self._force_metadata_only_reason is not None:
            now = datetime.now(UTC)
            async with self._uow_factory() as uow:
                for attachment in attachments:
                    attachment.download_status = AttachmentDownloadStatus.METADATA_ONLY
                    attachment.download_error = self._force_metadata_only_reason
                    attachment.extraction_status = (
                        DocumentExtractionStatus.BODY_UNAVAILABLE
                    )
                    attachment.extraction_error_code = self._force_metadata_only_reason
                    attachment.updated_at = now
                    await uow.feishu.save_attachment(attachment)
                await uow.commit()
            await self._request_analysis_after_download_failures(message_id)
            return
        for attachment in attachments:
            reservation_token: UUID | None = None
            target: Path | None = None
            target_created = False
            attachment.download_status = AttachmentDownloadStatus.DOWNLOADING
            attachment.updated_at = datetime.now(UTC)
            async with self._uow_factory() as uow:
                await uow.feishu.save_attachment(attachment)
                await uow.commit()
            try:
                resource_type = "image" if message.message_type == "image" else "file"
                content, mime_type, _size = await self._client.download_message_resource(
                    message_id=message.message_id,
                    file_key=attachment.file_key,
                    resource_type=resource_type,
                )
                if len(content) > self._settings.feishu_attachment_max_bytes:
                    raise AttachmentTooLargeError(
                        "Attachment exceeds the configured download limit."
                    )
                root = Path(self._settings.feishu_attachment_root)
                root.mkdir(parents=True, exist_ok=True, mode=0o700)
                root = root.resolve(strict=True)
                directory = (
                    root
                    / sanitize_attachment_filename(message.tenant_key or "default")
                    / str(message.id)
                )
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                directory = directory.resolve(strict=True)
                directory.relative_to(root)
                target = directory / (
                    f"{attachment.id}-{sanitize_attachment_filename(attachment.file_name)}"
                )
                requested_bytes = len(content)
                async with self._uow_factory() as uow:
                    reservation_token = await uow.storage_quota.reserve(
                        attachment_id=attachment.id,
                        requested_bytes=requested_bytes,
                        total_bytes=self._settings.feishu_attachment_total_quota_bytes,
                        observed_used_bytes=_attachment_storage_usage(root),
                        expires_at=datetime.now(UTC) + timedelta(minutes=10),
                    )
                    if reservation_token is None:
                        raise StorageQuotaExceededError(
                            "Attachment storage quota has been exceeded."
                        )
                    await uow.commit()
                _write_private_file(target, content)
                target_created = True
                attachment.sha256 = sha256(content).hexdigest()
                attachment.local_path = str(target)
                attachment.mime_type = attachment.mime_type or mime_type
                attachment.size = requested_bytes
                attachment.download_status = AttachmentDownloadStatus.DOWNLOADED
                attachment.download_error = None
                attachment.extraction_status = DocumentExtractionStatus.PENDING
                attachment.updated_at = datetime.now(UTC)
                async with self._uow_factory() as uow:
                    await uow.feishu.save_attachment(attachment)
                    await uow.storage_quota.commit(reservation_token)
                    await uow.outbox_events.add(
                        OutboxEvent(
                            id=uuid4(),
                            event_type="DocumentExtractionRequested",
                            aggregate_type="message_attachment",
                            aggregate_id=attachment.id,
                            payload={"attachmentId": str(attachment.id)},
                            correlation_id=f"document-extraction:{attachment.id}",
                        )
                    )
                    await uow.commit()
            except Exception as exc:
                if target is not None and target_created:
                    target.unlink(missing_ok=True)
                if reservation_token is not None:
                    async with self._uow_factory() as uow:
                        await uow.storage_quota.release(reservation_token)
                        await uow.commit()
                if self._unavailable_under_user_identity and (
                    isinstance(exc, FeishuApiError)
                    or getattr(exc, "http_status", None) is not None
                ):
                    unavailable_code = "resource_unavailable_under_user_identity"
                    attachment.download_status = AttachmentDownloadStatus.METADATA_ONLY
                    attachment.download_error = unavailable_code
                    attachment.extraction_status = DocumentExtractionStatus.BODY_UNAVAILABLE
                    attachment.extraction_error_code = unavailable_code
                else:
                    attachment.download_status = AttachmentDownloadStatus.FAILED
                    attachment.download_error = _download_error_code(exc)
                attachment.updated_at = datetime.now(UTC)
                async with self._uow_factory() as uow:
                    await uow.feishu.save_attachment(attachment)
                    await uow.commit()
        await self._request_analysis_after_download_failures(message_id)

    async def materialize_local_attachment(
        self,
        message_id: UUID,
        source: LocalFeishuAttachment,
    ) -> None:
        async with self._uow_factory() as uow:
            message = await uow.feishu.get_message_by_id(message_id)
            attachments = await uow.feishu.list_attachments(message_id)
        if message is None or source.message_id != message.message_id:
            raise InvalidStateTransitionError(
                "Local attachment is not associated with the selected message."
            )
        attachment = next(
            (value for value in attachments if value.file_key == source.file_key),
            None,
        )
        if attachment is None:
            raise InvalidStateTransitionError(
                "Local attachment metadata does not match the selected message."
            )
        source_path = source.local_path.resolve(strict=True)
        if source.local_path.is_symlink() or not source_path.is_file():
            raise InvalidStateTransitionError("Local attachment source is not a safe file.")
        content = source_path.read_bytes()
        if len(content) > self._settings.feishu_attachment_max_bytes:
            raise AttachmentTooLargeError(
                "Attachment exceeds the configured download limit."
            )
        root = Path(self._settings.feishu_attachment_root)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root = root.resolve(strict=True)
        directory = (
            root
            / sanitize_attachment_filename(message.tenant_key or "default")
            / str(message.id)
        )
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = directory.resolve(strict=True)
        directory.relative_to(root)
        target = directory / (
            f"{attachment.id}-{sanitize_attachment_filename(source.file_name)}"
        )
        reservation_token: UUID | None = None
        created = False
        try:
            async with self._uow_factory() as uow:
                reservation_token = await uow.storage_quota.reserve(
                    attachment_id=attachment.id,
                    requested_bytes=len(content),
                    total_bytes=self._settings.feishu_attachment_total_quota_bytes,
                    observed_used_bytes=_attachment_storage_usage(root),
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                )
                if reservation_token is None:
                    raise StorageQuotaExceededError(
                        "Attachment storage quota has been exceeded."
                    )
                await uow.commit()
            _write_private_file(target, content)
            created = True
            attachment.file_name = source.file_name
            attachment.mime_type = source.mime_type or attachment.mime_type
            attachment.size = len(content)
            attachment.sha256 = sha256(content).hexdigest()
            attachment.local_path = str(target)
            attachment.download_status = AttachmentDownloadStatus.DOWNLOADED
            attachment.download_error = None
            attachment.extraction_status = DocumentExtractionStatus.PENDING
            attachment.extraction_error_code = None
            attachment.updated_at = datetime.now(UTC)
            async with self._uow_factory() as uow:
                await uow.feishu.save_attachment(attachment)
                await uow.storage_quota.commit(reservation_token)
                await uow.outbox_events.add(
                    OutboxEvent(
                        id=uuid4(),
                        event_type="DocumentExtractionRequested",
                        aggregate_type="message_attachment",
                        aggregate_id=attachment.id,
                        payload={"attachmentId": str(attachment.id)},
                        correlation_id=f"local-document-extraction:{attachment.id}",
                    )
                )
                await uow.commit()
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            if reservation_token is not None:
                async with self._uow_factory() as uow:
                    await uow.storage_quota.release(reservation_token)
                    await uow.commit()
            raise

    async def _request_analysis_after_download_failures(self, message_id: UUID) -> None:
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation="attachment_analysis_ready", key=str(message_id))
            attachments = await uow.feishu.list_attachments(message_id)
            if not attachments or any(
                value.download_status
                not in {
                    AttachmentDownloadStatus.FAILED,
                    AttachmentDownloadStatus.METADATA_ONLY,
                }
                and (
                    value.download_status != AttachmentDownloadStatus.DOWNLOADED
                    or value.extraction_status
                    not in {
                        DocumentExtractionStatus.SUCCEEDED,
                        DocumentExtractionStatus.BODY_UNAVAILABLE,
                        DocumentExtractionStatus.FAILED,
                    }
                )
                for value in attachments
            ):
                return
            message = await uow.feishu.get_message_by_id(message_id)
            await self._analysis_gate.request_if_allowed(
                uow,
                message_id,
                actor_id="feishu-connector",
                actor_source="integration",
                correlation_id=f"attachment-analysis:{message_id}",
                force_new_run=bool(message is not None and message.version > 1),
            )
            await uow.commit()

    async def _reconcile_payload(
        self, chat_id: str, item: dict[str, object]
    ) -> tuple[dict[str, object], str, str]:
        message_id = str(item.get("message_id") or "").strip()
        if not message_id:
            raise FeishuApiError("Reconciled message omitted message_id.")
        tenant_key = self._settings.feishu_tenant_key or ""
        async with self._uow_factory() as uow:
            existing = await uow.feishu.get_message(tenant_key=tenant_key, message_id=message_id)
        event_type = (
            "im.message.message_edited_v1" if existing is not None else "im.message.receive_v1"
        )
        update_time = _seconds_to_millis(item.get("update_time"))
        create_time = _seconds_to_millis(item.get("create_time"))
        sender = item.get("sender")
        sender_object = sender if isinstance(sender, dict) else {}
        sender_id = str(sender_object.get("id") or sender_object.get("open_id") or "")
        message = dict(item)
        message["chat_id"] = chat_id
        message["message_type"] = str(item.get("message_type") or item.get("msg_type") or "unknown")
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
