from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class FeishuMessageOperation(StrEnum):
    CREATE = "create"
    EDIT = "edit"
    RECALL = "recall"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class NormalizedAttachment:
    file_key: str
    file_name: str
    mime_type: str | None = None
    size: int | None = None
    download_status: str = "pending"


@dataclass(frozen=True, slots=True)
class NormalizedMessage:
    message_id: str
    tenant_key: str
    chat_id: str | None
    thread_id: str | None
    parent_message_id: str | None
    root_message_id: str | None
    sender_id: str | None
    sender_type: str | None
    message_type: str
    plain_text: str
    structured_content: dict[str, object]
    attachments: tuple[NormalizedAttachment, ...]
    sent_at: datetime | None
    edited_at: datetime | None
    recalled_at: datetime | None
    raw_payload: dict[str, object]
    mentions: tuple[dict[str, object], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class NormalizedFeishuEvent:
    event_id: str
    event_type: str
    tenant_key: str
    app_id: str | None
    schema_version: str | None
    operation: FeishuMessageOperation
    external_message_id: str | None
    message: NormalizedMessage | None
    supported: bool
    should_trigger_analysis: bool
    unsupported_reason: str | None = None


SUPPORTED_MESSAGE_TYPES = {"text", "post", "file", "image"}
EDIT_EVENT_TYPES = {
    "im.message.message_edited_v1",
    "im.message.message_updated_v1",
}
RECALL_EVENT_TYPES = {
    "im.message.recalled_v1",
    "im.message.message_recalled_v1",
}


def _as_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): child for key, child in value.items()}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"text": value}
        if isinstance(parsed, dict):
            return {str(key): child for key, child in parsed.items()}
        return {"value": parsed}
    return {"value": value}


def _millis(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        return datetime.fromtimestamp(int(str(value)) / 1000, tz=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _post_text(value: dict[str, object]) -> str:
    locale = next(
        (
            child
            for key in ("zh_cn", "en_us", "ja_jp")
            if isinstance((child := value.get(key)), dict)
        ),
        value,
    )
    lines: list[str] = []
    title = str(locale.get("title") or "").strip()
    if title:
        lines.append(title)
    content = locale.get("content")
    if isinstance(content, list):
        for row in content:
            if not isinstance(row, list):
                continue
            segments: list[str] = []
            for node in row:
                if not isinstance(node, dict):
                    continue
                tag = str(node.get("tag") or "")
                if tag == "at":
                    text = f"@{str(node.get('user_name') or node.get('user_id') or '').strip()}"
                else:
                    text = str(node.get("text") or node.get("href") or "").strip()
                if text:
                    segments.append(text)
            if segments:
                lines.append(" ".join(segments))
    return "\n".join(lines)


def _plain_text(message_type: str, content: dict[str, object]) -> str:
    if message_type == "text":
        return str(content.get("text") or "").strip()
    if message_type == "post":
        return _post_text(content)
    if message_type in {"file", "image"}:
        return str(
            content.get("file_name")
            or content.get("file_key")
            or content.get("image_key")
            or ""
        ).strip()
    return ""


def _optional_int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _attachments(message_type: str, content: dict[str, object]) -> tuple[NormalizedAttachment, ...]:
    if message_type not in {"file", "image"}:
        return ()
    file_key = str(content.get("file_key") or content.get("image_key") or "").strip()
    if not file_key:
        return ()
    file_name = str(content.get("file_name") or file_key).strip()
    return (
        NormalizedAttachment(
            file_key=file_key,
            file_name=file_name,
            mime_type=str(content.get("mime_type") or "").strip() or None,
            size=_optional_int(content.get("size")),
        ),
    )


def normalize_feishu_event(payload: dict[str, object]) -> NormalizedFeishuEvent:
    header = payload.get("header")
    header_object = _as_object(header) if isinstance(header, dict) else {}
    event = payload.get("event")
    event_object = _as_object(event) if isinstance(event, dict) else {}
    event_id = str(header_object.get("event_id") or payload.get("event_id") or "").strip()
    event_type = str(header_object.get("event_type") or payload.get("type") or "").strip()
    tenant_key = str(header_object.get("tenant_key") or payload.get("tenant_key") or "").strip()
    app_id = str(header_object.get("app_id") or "").strip() or None
    schema_version = str(payload.get("schema") or "").strip() or None

    if event_type in RECALL_EVENT_TYPES:
        external_id = str(
            event_object.get("message_id")
            or _as_object(event_object.get("message")).get("message_id")
            or ""
        ).strip()
        return NormalizedFeishuEvent(
            event_id=event_id,
            event_type=event_type,
            tenant_key=tenant_key,
            app_id=app_id,
            schema_version=schema_version,
            operation=FeishuMessageOperation.RECALL,
            external_message_id=external_id or None,
            message=None,
            supported=bool(external_id),
            should_trigger_analysis=False,
            unsupported_reason=None if external_id else "missing_message_id",
        )

    message_object = _as_object(event_object.get("message"))
    external_id = str(message_object.get("message_id") or "").strip()
    message_type = str(message_object.get("message_type") or "unknown").strip()
    structured_content = _as_object(message_object.get("content"))
    supported = message_type in SUPPORTED_MESSAGE_TYPES
    operation = (
        FeishuMessageOperation.EDIT
        if event_type in EDIT_EVENT_TYPES
        else FeishuMessageOperation.CREATE
    )
    if not external_id:
        operation = FeishuMessageOperation.UNSUPPORTED
    sender = _as_object(event_object.get("sender"))
    sender_ids = _as_object(sender.get("sender_id"))
    sender_id = str(
        sender_ids.get("open_id") or sender_ids.get("user_id") or sender_ids.get("union_id") or ""
    ).strip() or None
    mentions_value = message_object.get("mentions")
    mentions = tuple(
        _as_object(item)
        for item in mentions_value
        if isinstance(mentions_value, list) and isinstance(item, dict)
    ) if isinstance(mentions_value, list) else ()
    message = (
        NormalizedMessage(
            message_id=external_id,
            tenant_key=tenant_key,
            chat_id=str(message_object.get("chat_id") or "").strip() or None,
            thread_id=str(message_object.get("thread_id") or "").strip() or None,
            parent_message_id=str(message_object.get("parent_id") or "").strip() or None,
            root_message_id=str(message_object.get("root_id") or "").strip() or None,
            sender_id=sender_id,
            sender_type=str(sender.get("sender_type") or "").strip() or None,
            message_type=message_type,
            plain_text=_plain_text(message_type, structured_content),
            structured_content=structured_content,
            attachments=_attachments(message_type, structured_content),
            sent_at=_millis(message_object.get("create_time")),
            edited_at=(
                _millis(message_object.get("update_time"))
                if operation == FeishuMessageOperation.EDIT
                else None
            ),
            recalled_at=None,
            raw_payload=message_object,
            mentions=mentions,
        )
        if external_id
        else None
    )
    unsupported_reason = None if supported else f"unsupported_message_type:{message_type}"
    if not external_id:
        unsupported_reason = "missing_message_id"
    return NormalizedFeishuEvent(
        event_id=event_id,
        event_type=event_type,
        tenant_key=tenant_key,
        app_id=app_id,
        schema_version=schema_version,
        operation=operation,
        external_message_id=external_id or None,
        message=message,
        supported=supported and bool(external_id),
        should_trigger_analysis=supported and bool(external_id),
        unsupported_reason=unsupported_reason,
    )
