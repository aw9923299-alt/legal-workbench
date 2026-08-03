from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from legal_workbench.application.idempotency import request_hash, require_matching_replay
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import AuditEvent, IdempotencyRecord, MessageAttachment
from legal_workbench.domain.enums import AttachmentDownloadStatus
from legal_workbench.domain.errors import EntityNotFoundError, InvalidStateTransitionError


@dataclass(frozen=True, slots=True)
class SetAttachmentAuthorizationResult:
    attachment: MessageAttachment
    idempotent_replay: bool


class AttachmentAuthorizationService:
    OPERATION = "set_attachment_analysis_authorization"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        *,
        message_id: UUID,
        attachment_id: UUID,
        authorized: bool,
        actor_id: str,
        actor_source: str,
        correlation_id: str,
        idempotency_key: str,
    ) -> SetAttachmentAuthorizationResult:
        digest = request_hash(
            {
                "messageId": str(message_id),
                "attachmentId": str(attachment_id),
                "authorized": authorized,
            }
        )
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=idempotency_key)
            replay = require_matching_replay(
                await uow.idempotency.get(operation=self.OPERATION, key=idempotency_key),
                expected_hash=digest,
                idempotency_key=idempotency_key,
            )
            attachment = await uow.feishu.get_attachment_for_update(attachment_id)
            if attachment is None or attachment.feishu_message_id != message_id:
                raise EntityNotFoundError("Message attachment was not found.")
            if replay is not None:
                return SetAttachmentAuthorizationResult(
                    attachment=attachment,
                    idempotent_replay=True,
                )
            if attachment.download_status != AttachmentDownloadStatus.DOWNLOADED:
                raise InvalidStateTransitionError(
                    "Only a downloaded attachment can be authorized for analysis."
                )
            attachment.authorized_for_analysis = authorized
            attachment.updated_at = datetime.now(UTC)
            await uow.feishu.save_attachment(attachment)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="message_attachment",
                    aggregate_id=attachment.id,
                    event_type=(
                        "attachment_analysis_authorized"
                        if authorized
                        else "attachment_analysis_revoked"
                    ),
                    actor_id=actor_id,
                    actor_source=actor_source,
                    payload={
                        "messageId": str(message_id),
                        "authorized": authorized,
                    },
                    correlation_id=correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=idempotency_key,
                    request_hash=digest,
                    response_payload={
                        "attachmentId": str(attachment.id),
                        "authorizedForAnalysis": authorized,
                    },
                )
            )
            await uow.commit()
            return SetAttachmentAuthorizationResult(
                attachment=attachment,
                idempotent_replay=False,
            )
