from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from legal_workbench.application.commands import IngestFeishuEventCommand
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.application.results import FeishuEventIngestedResult
from legal_workbench.domain.entities import (
    AuditEvent,
    FeishuAttachment,
    FeishuMessage,
    FeishuMessageVersion,
    FeishuRawEvent,
    OutboxEvent,
)
from legal_workbench.domain.enums import (
    AttachmentDownloadStatus,
    FeishuEventStatus,
    FeishuMessageStatus,
)
from legal_workbench.domain.errors import IdempotencyConflictError
from legal_workbench.integrations.feishu_events import (
    FeishuMessageOperation,
    NormalizedMessage,
    normalize_feishu_event,
)


def _payload_hash(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _parse_millis(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        timestamp = int(str(value)) / 1000
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _new_message(
    *,
    event_db_id: UUID,
    normalized: NormalizedMessage,
    supported: bool,
    unsupported_reason: str | None,
) -> FeishuMessage:
    attachment_payload: list[dict[str, object]] = [
        {
            "fileKey": value.file_key,
            "fileName": value.file_name,
            "mimeType": value.mime_type,
            "size": value.size,
            "downloadStatus": value.download_status,
        }
        for value in normalized.attachments
    ]
    return FeishuMessage(
        id=uuid4(),
        event_id=event_db_id,
        tenant_key=normalized.tenant_key,
        message_id=normalized.message_id,
        chat_id=normalized.chat_id,
        thread_id=normalized.thread_id,
        root_id=normalized.root_message_id,
        parent_id=normalized.parent_message_id,
        sender_id=normalized.sender_id,
        sender_type=normalized.sender_type,
        message_type=normalized.message_type,
        content=normalized.structured_content,
        mentions=list(normalized.mentions),
        create_time=normalized.sent_at,
        update_time=normalized.edited_at,
        raw_message=normalized.raw_payload,
        status=(FeishuMessageStatus.RECEIVED if supported else FeishuMessageStatus.UNSUPPORTED),
        plain_text=normalized.plain_text,
        structured_content=normalized.structured_content,
        attachments=attachment_payload,
        content_hash=_payload_hash(normalized.raw_payload),
        edited_at=normalized.edited_at,
        recalled_at=normalized.recalled_at,
        unsupported_reason=unsupported_reason,
    )


class IngestFeishuEventHandler:
    OPERATION = "ingest_feishu_event"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: IngestFeishuEventCommand) -> FeishuEventIngestedResult:
        digest = _payload_hash(command.raw_payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.event_id)
            normalized = normalize_feishu_event(command.raw_payload)
            tenant_key = normalized.tenant_key or command.tenant_key or ""
            existing = await uow.feishu.get_event_by_external_id(
                command.event_id, tenant_key=tenant_key
            )
            if existing is not None:
                if existing.payload_hash != digest:
                    raise IdempotencyConflictError(
                        "The Feishu event ID was reused with a different payload.",
                        details={"eventId": command.event_id},
                    )
                return FeishuEventIngestedResult(
                    event_id=existing.id,
                    message_id=None,
                    duplicate=True,
                )

            event = FeishuRawEvent(
                id=uuid4(),
                event_id=command.event_id,
                event_type=command.event_type,
                tenant_key=tenant_key,
                app_id=command.app_id,
                schema_version=command.schema_version,
                raw_payload=command.raw_payload,
                payload_hash=digest,
                status=FeishuEventStatus.RECEIVED,
            )
            message: FeishuMessage | None = None
            message_version: FeishuMessageVersion | None = None
            attachments: list[FeishuAttachment] = []
            if normalized.external_message_id:
                await uow.lock_idempotency(
                    operation="feishu_message",
                    key=f"{tenant_key}:{normalized.external_message_id}",
                )
                existing_message = await uow.feishu.get_message(
                    tenant_key=tenant_key,
                    message_id=normalized.external_message_id,
                )
                if normalized.operation == FeishuMessageOperation.CREATE and existing_message:
                    event.status = FeishuEventStatus.DUPLICATE
                elif normalized.message is not None and existing_message is None:
                    message = _new_message(
                        event_db_id=event.id,
                        normalized=normalized.message,
                        supported=normalized.supported,
                        unsupported_reason=normalized.unsupported_reason,
                    )
                elif normalized.message is not None and existing_message is not None:
                    message = existing_message
                    message.event_id = event.id
                    message.message_type = normalized.message.message_type
                    message.content = normalized.message.structured_content
                    message.structured_content = normalized.message.structured_content
                    message.plain_text = normalized.message.plain_text
                    message.raw_message = normalized.message.raw_payload
                    message.mentions = list(normalized.message.mentions)
                    message.attachments = [
                        {
                            "fileKey": value.file_key,
                            "fileName": value.file_name,
                            "mimeType": value.mime_type,
                            "size": value.size,
                            "downloadStatus": value.download_status,
                        }
                        for value in normalized.message.attachments
                    ]
                    message.update_time = normalized.message.edited_at
                    message.edited_at = normalized.message.edited_at
                    message.content_hash = _payload_hash(normalized.message.raw_payload)
                    message.unsupported_reason = normalized.unsupported_reason
                    message.version += 1
                elif normalized.operation == FeishuMessageOperation.RECALL and existing_message:
                    message = existing_message
                    event_payload = command.raw_payload.get("event")
                    recall_time = (
                        _parse_millis(event_payload.get("recall_time"))
                        if isinstance(event_payload, dict)
                        else None
                    )
                    message.event_id = event.id
                    message.recalled_at = recall_time or datetime.now(UTC)
                    message.version += 1
            await uow.feishu.add_event(event)
            if message is not None:
                if existing_message is None:
                    await uow.feishu.add_message(message)
                    revision = 1
                else:
                    await uow.feishu.save_message(message)
                    revision = await uow.feishu.next_message_revision(message.id)
                message_version = FeishuMessageVersion(
                    id=uuid4(),
                    feishu_message_id=message.id,
                    event_id=event.id,
                    revision=revision,
                    raw_payload=command.raw_payload,
                    content_hash=_payload_hash(command.raw_payload),
                    plain_text=message.plain_text or "",
                    structured_content=message.structured_content,
                    attachments=message.attachments,
                    edited_at=message.edited_at,
                    recalled_at=message.recalled_at,
                    is_recalled=normalized.operation == FeishuMessageOperation.RECALL,
                )
                await uow.feishu.add_message_version(message_version)
                if normalized.message is not None:
                    attachments = [
                        FeishuAttachment(
                            id=uuid4(),
                            feishu_message_id=message.id,
                            message_version_id=message_version.id,
                            file_key=value.file_key,
                            file_name=value.file_name,
                            mime_type=value.mime_type,
                            size=value.size,
                            download_status=AttachmentDownloadStatus.PENDING,
                        )
                        for value in normalized.message.attachments
                    ]
                    await uow.feishu.add_attachments(attachments)
                if normalized.should_trigger_analysis:
                    await uow.outbox_events.add(
                        OutboxEvent(
                            id=uuid4(),
                            event_type="FeishuMessageReceived",
                            aggregate_type="feishu_message",
                            aggregate_id=message.id,
                            payload={
                                "messageId": str(message.id),
                                "externalMessageId": message.message_id,
                                "chatId": message.chat_id,
                                "tenantKey": message.tenant_key,
                                "forceNewRun": normalized.operation
                                == FeishuMessageOperation.EDIT,
                            },
                            correlation_id=command.correlation_id,
                        )
                    )
                event.status = FeishuEventStatus.PROCESSED
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="feishu_event",
                    aggregate_id=event.id,
                    event_type="feishu_event_ingested",
                    actor_id=command.actor_id,
                    actor_source="integration",
                    payload={
                        "eventId": command.event_id,
                        "eventType": command.event_type,
                        "messageId": str(message.id) if message else None,
                        "duplicateMessage": event.status == FeishuEventStatus.DUPLICATE,
                        "operation": normalized.operation.value,
                        "supported": normalized.supported,
                        "messageVersionId": str(message_version.id) if message_version else None,
                        "attachmentCount": len(attachments),
                    },
                    correlation_id=command.correlation_id,
                )
            )
            await uow.commit()
        return FeishuEventIngestedResult(
            event_id=event.id,
            message_id=message.id if message else None,
            duplicate=False,
        )
