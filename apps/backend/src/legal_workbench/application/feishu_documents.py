from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid4

from legal_workbench.application.idempotency import request_hash, require_matching_replay
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import (
    AuditEvent,
    DocumentExtraction,
    DocumentSegment,
    DocumentVersion,
    ExtractedSegment,
    FeishuDocument,
    FeishuDocumentSubscription,
    IdempotencyRecord,
)
from legal_workbench.domain.enums import DocumentExtractionStatus
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityNotFoundError,
    EntityVersionConflictError,
)

_DOCUMENT_LINK = re.compile(
    r"https://[a-zA-Z0-9.-]+\.(?:feishu\.cn|larksuite\.com)/(docx|wiki)/([a-zA-Z0-9]+)"
)


@dataclass(frozen=True, slots=True)
class FeishuDocumentLink:
    document_type: str
    token: str
    url: str


@dataclass(frozen=True, slots=True)
class FeishuDocumentSyncResult:
    document_id: UUID
    document_version_id: UUID
    created_version: bool
    segment_count: int


class DocumentMarkdownClient(Protocol):
    async def get_document_markdown(
        self, *, authorization_id: UUID, document_id: str
    ) -> str: ...


class FolderFilesClient(Protocol):
    async def list_folder_files(
        self,
        *,
        authorization_id: UUID,
        folder_token: str,
        page_token: str | None = None,
    ) -> tuple[tuple[dict[str, object], ...], str | None]: ...


@dataclass(frozen=True, slots=True)
class FeishuFolderSyncResult:
    discovered_documents: int
    created_versions: int


def extract_feishu_document_links(text: str) -> tuple[FeishuDocumentLink, ...]:
    found: dict[tuple[str, str], FeishuDocumentLink] = {}
    for match in _DOCUMENT_LINK.finditer(text):
        document_type, token = match.groups()
        found.setdefault(
            (document_type, token),
            FeishuDocumentLink(
                document_type=document_type,
                token=token,
                url=match.group(0),
            ),
        )
    return tuple(found.values())


def _markdown_segments(markdown: str) -> tuple[ExtractedSegment, ...]:
    segments: list[ExtractedSegment] = []
    search_from = 0
    for line in markdown.splitlines():
        content = line.strip()
        if not content:
            continue
        relative_start = markdown.find(content, search_from)
        if relative_start < 0:
            relative_start = search_from
        segments.append(
            ExtractedSegment(
                page_number=None,
                paragraph_number=len(segments) + 1,
                start_offset=relative_start,
                end_offset=relative_start + len(content),
                content=content,
                content_hash=sha256(content.encode("utf-8")).hexdigest(),
            )
        )
        search_from = relative_start + len(content)
    return tuple(segments)


class FeishuDocumentSyncService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        client: DocumentMarkdownClient,
    ) -> None:
        self._uow_factory = uow_factory
        self._client = client

    async def sync_document(
        self,
        *,
        authorization_id: UUID,
        document_token: str,
        document_type: str,
        title: str | None,
        source_url: str,
        source_message_id: UUID | None = None,
        actor_id: str | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> FeishuDocumentSyncResult:
        if document_type != "docx":
            raise DomainValidationError(
                "A wiki link must be resolved to its official docx object before Markdown sync."
            )
        markdown = await self._client.get_document_markdown(
            authorization_id=authorization_id,
            document_id=document_token,
        )
        content_hash = sha256(markdown.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)
        async with self._uow_factory() as uow:
            digest = request_hash(
                {
                    "authorizationId": authorization_id,
                    "documentToken": document_token,
                    "documentType": document_type,
                    "title": title,
                    "sourceUrl": source_url,
                    "sourceMessageId": source_message_id,
                }
            )
            operation = "import_feishu_document"
            if idempotency_key is not None:
                await uow.lock_idempotency(operation=operation, key=idempotency_key)
                replay = require_matching_replay(
                    await uow.idempotency.get(
                        operation=operation, key=idempotency_key
                    ),
                    expected_hash=digest,
                    idempotency_key=idempotency_key,
                )
                if replay is not None:
                    return FeishuDocumentSyncResult(
                        document_id=UUID(str(replay.response_payload["documentId"])),
                        document_version_id=UUID(
                            str(replay.response_payload["documentVersionId"])
                        ),
                        created_version=bool(
                            replay.response_payload.get("createdVersion", False)
                        ),
                        segment_count=int(
                            str(replay.response_payload.get("segmentCount", 0))
                        ),
                    )
            document = await uow.documents.find_feishu_document(
                authorization_id=authorization_id,
                document_token=document_token,
            )
            if document is None:
                document = FeishuDocument(
                    id=uuid4(),
                    authorization_id=authorization_id,
                    document_token=document_token,
                    document_type=document_type,
                    title=title,
                    source_url=source_url,
                )
                await uow.documents.add_feishu_document(document)
                await uow.flush()
            existing = await uow.documents.find_feishu_document_version(
                document_id=document.id,
                content_sha256=content_hash,
            )
            document.title = title
            document.source_url = source_url
            document.last_content_hash = content_hash
            document.last_synced_at = now
            document.last_error_code = None
            document.updated_at = now
            if existing is not None:
                if source_message_id is not None:
                    await uow.documents.add_feishu_message_document_link(
                        message_id=source_message_id,
                        document_id=document.id,
                        source_url=source_url,
                    )
                await uow.documents.save_feishu_document(document)
                if actor_id is not None and correlation_id is not None:
                    await uow.audit_events.add(
                        AuditEvent(
                            id=uuid4(),
                            aggregate_type="feishu_document",
                            aggregate_id=document.id,
                            event_type="feishu_document_imported_unchanged",
                            actor_id=actor_id,
                            actor_source="user",
                            payload={"documentToken": document_token},
                            correlation_id=correlation_id,
                        )
                    )
                if idempotency_key is not None:
                    await uow.idempotency.add(
                        IdempotencyRecord(
                            id=uuid4(),
                            operation=operation,
                            idempotency_key=idempotency_key,
                            request_hash=digest,
                            response_payload={
                                "documentId": str(document.id),
                                "documentVersionId": str(existing.id),
                                "createdVersion": False,
                                "segmentCount": 0,
                            },
                        )
                    )
                await uow.commit()
                return FeishuDocumentSyncResult(
                    document_id=document.id,
                    document_version_id=existing.id,
                    created_version=False,
                    segment_count=0,
                )
            version = DocumentVersion(
                id=uuid4(),
                attachment_id=None,
                feishu_document_id=document.id,
                version=await uow.documents.next_feishu_document_version(document.id),
                content_sha256=content_hash,
                file_name=f"{title or document_token}.md",
                mime_type="text/markdown",
                size=len(markdown.encode("utf-8")),
                local_path=f"feishu://docx/{document_token}",
            )
            await uow.documents.add_version(version)
            await uow.flush()
            extracted = _markdown_segments(markdown)
            extraction = DocumentExtraction(
                id=uuid4(),
                document_version_id=version.id,
                status=(
                    DocumentExtractionStatus.SUCCEEDED
                    if extracted
                    else DocumentExtractionStatus.BODY_UNAVAILABLE
                ),
                extractor_version="feishu-markdown-v1",
                character_count=sum(len(value.content) for value in extracted),
                error_code=None if extracted else "DOCUMENT_BODY_UNAVAILABLE",
                finished_at=now,
            )
            await uow.documents.add_extraction(extraction)
            segments = tuple(
                DocumentSegment.from_extracted(
                    extraction_id=extraction.id,
                    attachment_id=None,
                    feishu_document_id=document.id,
                    segment=value,
                )
                for value in extracted
            )
            if segments:
                await uow.documents.add_segments(segments)
            if source_message_id is not None:
                await uow.documents.add_feishu_message_document_link(
                    message_id=source_message_id,
                    document_id=document.id,
                    source_url=source_url,
                )
            await uow.documents.save_feishu_document(document)
            if actor_id is not None and correlation_id is not None:
                await uow.audit_events.add(
                    AuditEvent(
                        id=uuid4(),
                        aggregate_type="feishu_document",
                        aggregate_id=document.id,
                        event_type="feishu_document_imported",
                        actor_id=actor_id,
                        actor_source="user",
                        payload={
                            "documentToken": document_token,
                            "documentVersionId": str(version.id),
                            "segmentCount": len(segments),
                        },
                        correlation_id=correlation_id,
                    )
                )
            if idempotency_key is not None:
                await uow.idempotency.add(
                    IdempotencyRecord(
                        id=uuid4(),
                        operation=operation,
                        idempotency_key=idempotency_key,
                        request_hash=digest,
                        response_payload={
                            "documentId": str(document.id),
                            "documentVersionId": str(version.id),
                            "createdVersion": True,
                            "segmentCount": len(segments),
                        },
                    )
                )
            await uow.commit()
        return FeishuDocumentSyncResult(
            document_id=document.id,
            document_version_id=version.id,
            created_version=True,
            segment_count=len(segments),
        )


class FeishuFolderSyncService:
    """Synchronize only a user-selected folder; never mirrors the whole drive."""

    def __init__(
        self,
        *,
        client: FolderFilesClient,
        document_sync: FeishuDocumentSyncService,
    ) -> None:
        self._client = client
        self._document_sync = document_sync

    async def sync_folder(
        self,
        *,
        authorization_id: UUID,
        folder_token: str,
        recursive: bool,
    ) -> FeishuFolderSyncResult:
        pending = [folder_token]
        visited_folders: set[str] = set()
        visited_documents: set[str] = set()
        created_versions = 0
        while pending:
            current = pending.pop(0)
            if current in visited_folders:
                continue
            visited_folders.add(current)
            page_token: str | None = None
            while True:
                files, page_token = await self._client.list_folder_files(
                    authorization_id=authorization_id,
                    folder_token=current,
                    page_token=page_token,
                )
                for item in files:
                    token = str(item.get("token") or "").strip()
                    item_type = str(item.get("type") or "").strip().lower()
                    if not token:
                        continue
                    if item_type == "folder":
                        if recursive and token not in visited_folders:
                            pending.append(token)
                        continue
                    if item_type != "docx" or token in visited_documents:
                        continue
                    visited_documents.add(token)
                    source_url = str(item.get("url") or "").strip()
                    if not source_url:
                        source_url = f"https://open.feishu.cn/docx/{token}"
                    synced = await self._document_sync.sync_document(
                        authorization_id=authorization_id,
                        document_token=token,
                        document_type="docx",
                        title=str(item.get("name") or "").strip() or None,
                        source_url=source_url,
                    )
                    created_versions += int(synced.created_version)
                if page_token is None:
                    break
        return FeishuFolderSyncResult(
            discovered_documents=len(visited_documents),
            created_versions=created_versions,
        )


class FeishuFolderSubscriptionService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        folder_sync: FeishuFolderSyncService,
    ) -> None:
        self._uow_factory = uow_factory
        self._folder_sync = folder_sync

    async def list_subscriptions(
        self, *, authorization_id: UUID | None = None, active_only: bool = False
    ) -> tuple[FeishuDocumentSubscription, ...]:
        async with self._uow_factory() as uow:
            values = await uow.documents.list_feishu_document_subscriptions(
                authorization_id=authorization_id,
                active_only=active_only,
            )
        return tuple(values)

    async def subscribe(
        self,
        *,
        authorization_id: UUID,
        folder_token: str,
        recursive: bool,
        actor_id: str,
        correlation_id: str,
        idempotency_key: str,
    ) -> FeishuDocumentSubscription:
        normalized_token = folder_token.strip()
        digest = request_hash(
            {
                "authorizationId": authorization_id,
                "folderToken": normalized_token,
                "recursive": recursive,
            }
        )
        operation = "subscribe_feishu_folder"
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=operation, key=idempotency_key)
            replay = require_matching_replay(
                await uow.idempotency.get(operation=operation, key=idempotency_key),
                expected_hash=digest,
                idempotency_key=idempotency_key,
            )
            if replay is not None:
                stored = await uow.documents.get_feishu_document_subscription_by_id(
                    UUID(str(replay.response_payload["subscriptionId"]))
                )
                if stored is None:
                    raise EntityNotFoundError("Feishu folder subscription was not found.")
                return stored
            subscription = await uow.documents.get_feishu_document_subscription(
                authorization_id=authorization_id,
                folder_token=normalized_token,
            )
            if subscription is None:
                subscription = FeishuDocumentSubscription(
                    id=uuid4(),
                    authorization_id=authorization_id,
                    folder_token=normalized_token,
                    recursive=recursive,
                )
                await uow.documents.add_feishu_document_subscription(subscription)
            else:
                subscription.recursive = recursive
                subscription.active = True
                subscription.version += 1
                subscription.updated_at = datetime.now(UTC)
                await uow.documents.save_feishu_document_subscription(subscription)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="feishu_document_subscription",
                    aggregate_id=subscription.id,
                    event_type="feishu_folder_subscribed",
                    actor_id=actor_id,
                    actor_source="user",
                    payload={
                        "folderToken": normalized_token,
                        "recursive": recursive,
                        "version": subscription.version,
                    },
                    correlation_id=correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=operation,
                    idempotency_key=idempotency_key,
                    request_hash=digest,
                    response_payload={"subscriptionId": str(subscription.id)},
                )
            )
            await uow.commit()
            return subscription

    async def unsubscribe(
        self,
        *,
        authorization_id: UUID,
        folder_token: str,
        expected_version: int,
        actor_id: str,
        correlation_id: str,
        idempotency_key: str,
    ) -> FeishuDocumentSubscription:
        normalized_token = folder_token.strip()
        digest = request_hash(
            {
                "authorizationId": authorization_id,
                "folderToken": normalized_token,
                "expectedVersion": expected_version,
            }
        )
        operation = "unsubscribe_feishu_folder"
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=operation, key=idempotency_key)
            replay = require_matching_replay(
                await uow.idempotency.get(operation=operation, key=idempotency_key),
                expected_hash=digest,
                idempotency_key=idempotency_key,
            )
            subscription = await uow.documents.get_feishu_document_subscription(
                authorization_id=authorization_id,
                folder_token=normalized_token,
            )
            if subscription is None:
                raise EntityNotFoundError("Feishu folder subscription was not found.")
            if replay is not None:
                return subscription
            if subscription.version != expected_version:
                raise EntityVersionConflictError(
                    "Feishu folder subscription changed before it was removed."
                )
            subscription.active = False
            subscription.version += 1
            subscription.updated_at = datetime.now(UTC)
            await uow.documents.save_feishu_document_subscription(subscription)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="feishu_document_subscription",
                    aggregate_id=subscription.id,
                    event_type="feishu_folder_unsubscribed",
                    actor_id=actor_id,
                    actor_source="user",
                    payload={"version": subscription.version},
                    correlation_id=correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=operation,
                    idempotency_key=idempotency_key,
                    request_hash=digest,
                    response_payload={"subscriptionId": str(subscription.id)},
                )
            )
            await uow.commit()
            return subscription

    async def sync_subscription(
        self, subscription_id: UUID
    ) -> FeishuFolderSyncResult:
        async with self._uow_factory() as uow:
            subscription = await uow.documents.get_feishu_document_subscription_by_id(
                subscription_id
            )
        if subscription is None or not subscription.active:
            raise EntityNotFoundError("Active Feishu folder subscription was not found.")
        try:
            result = await self._folder_sync.sync_folder(
                authorization_id=subscription.authorization_id,
                folder_token=subscription.folder_token,
                recursive=subscription.recursive,
            )
        except Exception:
            async with self._uow_factory() as uow:
                current = await uow.documents.get_feishu_document_subscription_by_id(
                    subscription_id
                )
                if current is not None:
                    current.last_error_code = "folder_sync_failed"
                    current.updated_at = datetime.now(UTC)
                    await uow.documents.save_feishu_document_subscription(current)
                    await uow.commit()
            raise
        async with self._uow_factory() as uow:
            current = await uow.documents.get_feishu_document_subscription_by_id(
                subscription_id
            )
            if current is not None:
                current.last_synced_at = datetime.now(UTC)
                current.last_error_code = None
                current.updated_at = datetime.now(UTC)
                await uow.documents.save_feishu_document_subscription(current)
                await uow.commit()
        return result
