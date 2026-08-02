from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import TypedDict
from uuid import UUID, uuid4

from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import ContextSnapshot, FeishuMessage
from legal_workbench.domain.errors import EntityNotFoundError


class _ContentMetrics(TypedDict):
    reasons: list[str]
    originalSize: int
    includedSize: int


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
        visit(message.attachments)
    return sorted(found)


class ContextSnapshotBuilder:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        max_messages: int,
        max_text_characters: int,
        max_single_message_characters: int | None = None,
        max_attachments: int = 10,
        builder_version: str = "2.0.0",
        selection_policy_version: str = "thread-v2",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        single_limit = max_single_message_characters or max_text_characters
        if (
            max_messages < 1
            or max_text_characters < 1
            or single_limit < 1
            or max_attachments < 0
        ):
            raise ValueError("Context bounds must be positive.")
        self._uow_factory = uow_factory
        self._max_messages = max_messages
        self._max_text_characters = max_text_characters
        self._max_single_message_characters = single_limit
        self._max_attachments = max_attachments
        self._builder_version = builder_version
        self._selection_policy_version = selection_policy_version
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
            all_attachment_ids = _attachment_ids(selected)
            attachment_ids = all_attachment_ids[: self._max_attachments]
            participants = sorted({message.sender_id for message in selected if message.sender_id})
            content, content_metrics = self._build_content(
                selected,
                current_message_id=current.message_id,
                allowed_attachment_ids=set(attachment_ids),
            )
            available_unique_count = len({value.message_id for value in available})
            reasons = list(content_metrics["reasons"])
            if available_unique_count > len(selected):
                reasons.append("message_count_limit")
            if len(all_attachment_ids) > len(attachment_ids):
                reasons.append("attachment_limit")
            reasons = sorted(set(reasons))
            truncated = bool(reasons)
            attachment_version_hash = sha256(
                _canonical_json(
                    [
                        {
                            "messageId": message.message_id,
                            "messageVersion": message.version,
                            "attachments": message.attachments,
                        }
                        for message in selected
                    ]
                ).encode("utf-8")
            ).hexdigest()
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
                "snapshotVersion": 2,
                "builderVersion": self._builder_version,
                "selectionPolicyVersion": self._selection_policy_version,
                "currentMessageVersion": current.version,
                "attachmentVersionHash": attachment_version_hash,
                "messageIds": [message.message_id for message in selected],
                "participantIds": participants,
                "attachmentIds": attachment_ids,
                "threadMetadata": thread_metadata,
                "permissionSnapshot": permission_snapshot,
                "content": content,
                "truncated": truncated,
                "truncationReason": ",".join(reasons) or None,
                "originalSize": content_metrics["originalSize"],
                "includedSize": content_metrics["includedSize"],
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
                snapshot_version=2,
                source_ids=[message.message_id for message in selected],
                message_ids=[message.message_id for message in selected],
                file_ids=attachment_ids,
                attachment_ids=attachment_ids,
                relevant_matter_ids=[],
                participant_ids=participants,
                permission_snapshot=permission_snapshot,
                thread_metadata=thread_metadata,
                content=content,
                builder_version=self._builder_version,
                selection_policy_version=self._selection_policy_version,
                current_message_version=current.version,
                attachment_version_hash=attachment_version_hash,
                truncated=truncated,
                truncation_reason=",".join(reasons) or None,
                original_size=int(content_metrics["originalSize"]),
                included_size=int(content_metrics["includedSize"]),
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
        self,
        messages: Sequence[FeishuMessage],
        *,
        current_message_id: str,
        allowed_attachment_ids: set[str],
    ) -> tuple[dict[str, object], _ContentMetrics]:
        remaining = self._max_text_characters
        reasons: list[str] = []
        allocated: dict[str, object] = {}
        original_sizes: dict[str, int] = {}
        included_sizes: dict[str, int] = {}

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
            source_content = message.structured_content or message.content
            raw_content = _canonical_json(source_content)
            original_sizes[message.message_id] = len(raw_content)
            per_message_content = raw_content[: self._max_single_message_characters]
            if len(raw_content) > len(per_message_content):
                reasons.append("single_message_limit")
            included = per_message_content[: max(remaining, 0)]
            included_sizes[message.message_id] = len(included)
            if len(per_message_content) > len(included):
                reasons.append("total_character_limit")
            if len(included) != len(raw_content):
                allocated[message.message_id] = {
                    "truncatedText": included,
                    "contentHash": message.content_hash,
                }
            else:
                allocated[message.message_id] = source_content
            remaining -= len(included)

        entries: list[dict[str, object]] = []
        for message in messages:
            entries.append(
                {
                    "messageId": message.message_id,
                    "senderId": message.sender_id,
                    "messageType": message.message_type,
                    "messageVersion": message.version,
                    "contentHash": message.content_hash,
                    "createTime": (
                        message.create_time.isoformat() if message.create_time else None
                    ),
                    "content": allocated[message.message_id],
                    "attachments": [
                        value
                        for value in message.attachments
                        if str(
                            value.get("fileKey")
                            or value.get("file_key")
                            or value.get("imageKey")
                            or value.get("image_key")
                            or ""
                        )
                        in allowed_attachment_ids
                    ],
                    "editedAt": message.edited_at.isoformat() if message.edited_at else None,
                    "recalledAt": (
                        message.recalled_at.isoformat() if message.recalled_at else None
                    ),
                    "untrustedInput": True,
                }
            )
        original_size = sum(original_sizes.values())
        included_size = sum(included_sizes.values())
        return (
            {
                "messages": entries,
                "truncated": bool(reasons),
                "truncationReason": ",".join(sorted(set(reasons))) or None,
                "originalSize": original_size,
                "includedSize": included_size,
                "builderVersion": self._builder_version,
                "selectionPolicyVersion": self._selection_policy_version,
            },
            {
                "reasons": reasons,
                "originalSize": original_size,
                "includedSize": included_size,
            },
        )
