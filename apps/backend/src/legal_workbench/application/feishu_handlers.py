from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from legal_workbench.application.commands import IngestFeishuEventCommand
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.application.results import FeishuEventIngestedResult
from legal_workbench.domain.entities import (
    AuditEvent,
    FeishuMessage,
    FeishuRawEvent,
    OutboxEvent,
)
from legal_workbench.domain.enums import FeishuEventStatus, FeishuMessageStatus
from legal_workbench.domain.errors import IdempotencyConflictError


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


def _parse_content(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"text": value}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {"value": value}


def _extract_message(
    *,
    event_db_id,
    tenant_key: str | None,
    payload: dict[str, object],
) -> FeishuMessage | None:
    event = payload.get("event")
    if not isinstance(event, dict):
        return None
    message = event.get("message")
    if not isinstance(message, dict):
        return None
    message_id = str(message.get("message_id") or "").strip()
    if not message_id:
        return None
    sender = event.get("sender")
    sender_id: str | None = None
    sender_type: str | None = None
    if isinstance(sender, dict):
        sender_type = str(sender.get("sender_type") or "") or None
        sender_id_value = sender.get("sender_id")
        if isinstance(sender_id_value, dict):
            sender_id = str(
                sender_id_value.get("open_id")
                or sender_id_value.get("user_id")
                or sender_id_value.get("union_id")
                or ""
            ) or None
    mentions = message.get("mentions")
    normalized_mentions = mentions if isinstance(mentions, list) else []
    return FeishuMessage(
        id=uuid4(),
        event_id=event_db_id,
        tenant_key=tenant_key or "",
        message_id=message_id,
        chat_id=str(message.get("chat_id") or "") or None,
        thread_id=str(message.get("thread_id") or "") or None,
        root_id=str(message.get("root_id") or "") or None,
        parent_id=str(message.get("parent_id") or "") or None,
        sender_id=sender_id,
        sender_type=sender_type,
        message_type=str(message.get("message_type") or "unknown"),
        content=_parse_content(message.get("content")),
        mentions=[item for item in normalized_mentions if isinstance(item, dict)],
        create_time=_parse_millis(message.get("create_time")),
        update_time=_parse_millis(message.get("update_time")),
        raw_message=message,
        status=FeishuMessageStatus.RECEIVED,
    )


class IngestFeishuEventHandler:
    OPERATION = "ingest_feishu_event"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: IngestFeishuEventCommand) -> FeishuEventIngestedResult:
        digest = _payload_hash(command.raw_payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.event_id)
            existing = await uow.feishu.get_event_by_external_id(command.event_id)
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
                tenant_key=command.tenant_key or "",
                app_id=command.app_id,
                schema_version=command.schema_version,
                raw_payload=command.raw_payload,
                payload_hash=digest,
                status=FeishuEventStatus.RECEIVED,
            )
            message = _extract_message(
                event_db_id=event.id,
                tenant_key=event.tenant_key,
                payload=command.raw_payload,
            )
            if message is not None:
                existing_message = await uow.feishu.get_message(
                    tenant_key=message.tenant_key,
                    message_id=message.message_id,
                )
                if existing_message is not None:
                    message = None
                    event.status = FeishuEventStatus.DUPLICATE
            await uow.feishu.add_event(event)
            if message is not None:
                await uow.feishu.add_message(message)
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
                        },
                        correlation_id=command.correlation_id,
                    )
                )
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="feishu_event",
                    aggregate_id=event.id,
                    event_type="feishu_event_ingested",
                    actor_id=command.actor_id,
                    payload={
                        "eventId": command.event_id,
                        "eventType": command.event_type,
                        "messageId": str(message.id) if message else None,
                        "duplicateMessage": message is None,
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
