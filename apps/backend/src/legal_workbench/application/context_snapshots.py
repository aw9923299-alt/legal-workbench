from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import ContextSnapshot, FeishuMessage
from legal_workbench.domain.errors import EntityNotFoundError


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _message_order(message: FeishuMessage) -> tuple[datetime, str]:
    return (message.create_time or datetime.min.replace(tzinfo=UTC), message.message_id)


def _attachment_ids(messages: Sequence[FeishuMessage]) -> list[str]:
    keys = {"file_key", "image_key", "media_key", "fileKey", "imageKey", "mediaKey"}
    found: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in keys and isinstance(child, str) and child:
                    found.add(child)
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for message in messages:
        visit(message.content)
    return sorted(found)


class ContextSnapshotBuilder:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        max_messages: int,
        max_text_characters: int,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if max_messages < 1 or max_text_characters < 1:
            raise ValueError("Context bounds must be positive.")
        self._uow_factory = uow_factory
        self._max_messages = max_messages
        self._max_text_characters = max_text_characters
        self._now = now or (lambda: datetime.now(UTC))

    async def build_for_feishu_message(self, message_id: UUID) -> ContextSnapshot:
        async with self._uow_factory() as uow:
            # Serialize snapshot lookup/creation for one message so concurrent
            # outbox deliveries reuse the immutable row instead of racing the
            # source/hash unique constraint.
            await uow.lock_idempotency(operation="context_snapshot", key=str(message_id))
            current = await uow.feishu.get_message_by_id(message_id)
            if current is None:
                raise EntityNotFoundError(
                    "Feishu message was not found.",
                    details={"code": "FEISHU_MESSAGE_NOT_FOUND", "messageId": str(message_id)},
                )
            available = list(
                await uow.feishu.list_context_messages(
                    current, limit=max(self._max_messages * 3, self._max_messages)
                )
            )
            selected = self._select_messages(current, available)
            attachment_ids = _attachment_ids(selected)
            participants = sorted({message.sender_id for message in selected if message.sender_id})
            content = self._build_content(selected, current_message_id=current.message_id)
            thread_metadata: dict[str, object] = {
                "chatId": current.chat_id,
                "threadId": current.thread_id,
                "rootId": current.root_id,
                "parentId": current.parent_id,
            }
            permission_snapshot: dict[str, object] = {
                "allowedMessageDatabaseIds": [str(message.id) for message in selected],
                "allowedMessageIds": [message.message_id for message in selected],
                "allowedAttachmentIds": attachment_ids,
                "databaseAccess": False,
                "networkAccess": False,
                "repositoryAccess": False,
            }
            hash_payload = {
                "sourceType": "feishu_message",
                "sourceId": str(current.id),
                "snapshotVersion": 1,
                "messageIds": [message.message_id for message in selected],
                "participantIds": participants,
                "attachmentIds": attachment_ids,
                "threadMetadata": thread_metadata,
                "permissionSnapshot": permission_snapshot,
                "content": content,
            }
            content_hash = sha256(_canonical_json(hash_payload).encode("utf-8")).hexdigest()
            existing = await uow.context_snapshots.find_by_source_hash(
                source_type="feishu_message",
                source_id=str(current.id),
                content_hash=content_hash,
            )
            if existing is not None:
                return existing
            snapshot = ContextSnapshot(
                id=uuid4(),
                source_type="feishu_message",
                source_id=str(current.id),
                snapshot_version=1,
                source_ids=[message.message_id for message in selected],
                message_ids=[message.message_id for message in selected],
                file_ids=attachment_ids,
                attachment_ids=attachment_ids,
                relevant_matter_ids=[],
                participant_ids=participants,
                permission_snapshot=permission_snapshot,
                thread_metadata=thread_metadata,
                content=content,
                generated_at=self._now(),
                content_hash=content_hash,
            )
            await uow.context_snapshots.add(snapshot)
            await uow.commit()
            return snapshot

    def _select_messages(
        self, current: FeishuMessage, available: Sequence[FeishuMessage]
    ) -> list[FeishuMessage]:
        unique = {message.message_id: message for message in available}
        unique[current.message_id] = current
        ordered = sorted(unique.values(), key=_message_order)
        selected = ordered[-self._max_messages :]
        if current.message_id not in {message.message_id for message in selected}:
            selected = [*selected[1:], current]
        return sorted(selected, key=_message_order)

    def _build_content(
        self, messages: Sequence[FeishuMessage], *, current_message_id: str
    ) -> dict[str, object]:
        remaining = self._max_text_characters
        truncated = False
        allocated: dict[str, object] = {}

        # The target message is the reason the snapshot exists, so it consumes
        # the bounded text budget first. Recent context then fills the balance.
        prioritized = sorted(
            messages,
            key=lambda message: (
                message.message_id == current_message_id,
                _message_order(message),
            ),
            reverse=True,
        )
        for message in prioritized:
            raw_content = _canonical_json(message.content)
            if len(raw_content) > remaining:
                allocated[message.message_id] = {
                    "truncatedText": raw_content[: max(remaining, 0)]
                }
                remaining = 0
                truncated = True
            else:
                allocated[message.message_id] = message.content
                remaining -= len(raw_content)

        entries: list[dict[str, object]] = []
        for message in messages:
            entries.append(
                {
                    "messageId": message.message_id,
                    "senderId": message.sender_id,
                    "messageType": message.message_type,
                    "createTime": (
                        message.create_time.isoformat() if message.create_time else None
                    ),
                    "content": allocated[message.message_id],
                    "untrustedInput": True,
                }
            )
        return {"messages": entries, "truncated": truncated}
