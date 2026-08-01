from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from legal_workbench.config import Settings, get_settings
from legal_workbench.domain.entities import Communication
from legal_workbench.domain.enums import CommunicationStatus, FeishuMessageStatus
from legal_workbench.infrastructure.celery_app import celery_app
from legal_workbench.infrastructure.database import get_session_factory
from legal_workbench.infrastructure.models import (
    CommunicationModel,
    FeishuMessageModel,
    OutboxDeadLetterModel,
    OutboxEventModel,
)
from legal_workbench.integrations.feishu_client import FeishuApiClient

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ClaimedOutboxEvent:
    id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, object]
    correlation_id: str
    attempts: int


class OutboxDispatcher:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        settings: Settings | None = None,
        feishu_client: FeishuApiClient | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._settings = settings or get_settings()
        self._feishu_client = feishu_client or FeishuApiClient(self._settings)

    async def publish_batch(self) -> int:
        events = await self._claim_batch()
        for event in events:
            try:
                await self._dispatch(event)
            except Exception as exc:  # noqa: BLE001 - failures are persisted for retry/dead-letter
                await self._record_failure(event, exc)
            else:
                await self._mark_published(event.id)
        return len(events)

    async def list_dead_letters(self, *, limit: int = 100) -> list[OutboxDeadLetterModel]:
        async with self._session_factory() as session:
            statement = (
                select(OutboxDeadLetterModel)
                .order_by(OutboxDeadLetterModel.failed_at.desc())
                .limit(limit)
            )
            return list((await session.execute(statement)).scalars().all())

    async def requeue_dead_letter(self, dead_letter_id: UUID) -> UUID:
        async with self._session_factory() as session, session.begin():
            record = await session.get(
                OutboxDeadLetterModel, dead_letter_id, with_for_update=True
            )
            if record is None:
                raise LookupError("Outbox dead letter was not found.")
            if record.requeued_at is not None:
                raise RuntimeError("Outbox dead letter has already been requeued.")
            event_id = uuid4()
            session.add(
                OutboxEventModel(
                    id=event_id,
                    event_type=record.event_type,
                    aggregate_type=record.aggregate_type,
                    aggregate_id=record.aggregate_id,
                    payload=record.payload,
                    correlation_id=record.correlation_id,
                    occurred_at=datetime.now(UTC),
                    attempts=0,
                    next_attempt_at=datetime.now(UTC),
                )
            )
            record.requeued_at = datetime.now(UTC)
            record.requeued_event_id = event_id
            return event_id

    async def _claim_batch(self) -> list[ClaimedOutboxEvent]:
        now = datetime.now(UTC)
        locked_until = now + timedelta(seconds=self._settings.outbox_lock_seconds)
        async with self._session_factory() as session, session.begin():
            statement = (
                select(OutboxEventModel)
                .where(
                    OutboxEventModel.published_at.is_(None),
                    OutboxEventModel.dead_lettered_at.is_(None),
                    or_(
                        OutboxEventModel.next_attempt_at.is_(None),
                        OutboxEventModel.next_attempt_at <= now,
                    ),
                    or_(
                        OutboxEventModel.locked_until.is_(None),
                        OutboxEventModel.locked_until < now,
                    ),
                )
                .order_by(OutboxEventModel.occurred_at)
                .limit(self._settings.outbox_batch_size)
                .with_for_update(skip_locked=True)
            )
            models = list((await session.execute(statement)).scalars().all())
            for model in models:
                model.locked_until = locked_until
                model.locked_by = self._settings.outbox_worker_id
            return [
                ClaimedOutboxEvent(
                    id=model.id,
                    event_type=model.event_type,
                    aggregate_type=model.aggregate_type,
                    aggregate_id=model.aggregate_id,
                    payload=model.payload,
                    correlation_id=model.correlation_id,
                    attempts=model.attempts,
                )
                for model in models
            ]

    async def _dispatch(self, event: ClaimedOutboxEvent) -> None:
        if event.event_type == "CommunicationSendRequested":
            await self._send_communication(event.aggregate_id)
            return
        if event.event_type == "FeishuMessageReceived":
            celery_app.send_task(
                "feishu.process_message",
                args=[str(event.aggregate_id)],
                headers={"correlation_id": event.correlation_id},
            )
            return
        logger.info(
            "outbox_event_published_without_external_handler",
            event_id=str(event.id),
            event_type=event.event_type,
            aggregate_id=str(event.aggregate_id),
        )

    async def _send_communication(self, communication_id: UUID) -> None:
        communication = await self._mark_communication_sending(communication_id)
        if communication is None:
            return
        try:
            external_message_id = await self._feishu_client.send_communication(communication)
        except Exception as exc:
            await self._mark_communication_failed(communication_id, str(exc))
            raise
        await self._mark_communication_sent(communication_id, external_message_id)

    async def _mark_communication_sending(
        self, communication_id: UUID
    ) -> Communication | None:
        async with self._session_factory() as session, session.begin():
            statement = (
                select(CommunicationModel)
                .where(CommunicationModel.id == communication_id)
                .with_for_update()
            )
            model = (await session.execute(statement)).scalar_one_or_none()
            if model is None:
                raise LookupError("Communication was not found.")
            if model.status == CommunicationStatus.SENT:
                return None
            if model.status not in {
                CommunicationStatus.QUEUED,
                CommunicationStatus.FAILED,
                CommunicationStatus.UNKNOWN,
            }:
                raise RuntimeError(
                    f"Communication cannot be sent from status {model.status.value}."
                )
            model.status = CommunicationStatus.SENDING
            model.attempts += 1
            model.last_error = None
            return self._to_domain(model)

    async def _mark_communication_sent(
        self, communication_id: UUID, external_message_id: str
    ) -> None:
        async with self._session_factory() as session, session.begin():
            model = await session.get(CommunicationModel, communication_id, with_for_update=True)
            if model is None:
                raise LookupError("Communication was not found after sending.")
            model.status = CommunicationStatus.SENT
            model.external_message_id = external_message_id
            model.sent_at = datetime.now(UTC)
            model.last_error = None

    async def _mark_communication_failed(self, communication_id: UUID, error: str) -> None:
        async with self._session_factory() as session, session.begin():
            model = await session.get(CommunicationModel, communication_id, with_for_update=True)
            if model is not None and model.status != CommunicationStatus.SENT:
                model.status = CommunicationStatus.FAILED
                model.last_error = error[:4000]

    async def _mark_published(self, event_id: UUID) -> None:
        async with self._session_factory() as session, session.begin():
            model = await session.get(OutboxEventModel, event_id, with_for_update=True)
            if model is None:
                return
            model.published_at = datetime.now(UTC)
            model.locked_until = None
            model.locked_by = None
            model.last_error = None

    async def _record_failure(
        self, event: ClaimedOutboxEvent, error: Exception
    ) -> None:
        now = datetime.now(UTC)
        error_text = f"{type(error).__name__}: {error}"[:4000]
        attempts = event.attempts + 1
        async with self._session_factory() as session, session.begin():
            model = await session.get(OutboxEventModel, event.id, with_for_update=True)
            if model is None or model.published_at is not None:
                return
            model.attempts = attempts
            model.last_error = error_text
            model.locked_until = None
            model.locked_by = None
            if attempts >= self._settings.outbox_max_attempts:
                model.dead_lettered_at = now
                model.next_attempt_at = None
                session.add(
                    OutboxDeadLetterModel(
                        id=uuid4(),
                        original_event_id=model.id,
                        event_type=model.event_type,
                        aggregate_type=model.aggregate_type,
                        aggregate_id=model.aggregate_id,
                        payload=model.payload,
                        correlation_id=model.correlation_id,
                        attempts=attempts,
                        last_error=error_text,
                        failed_at=now,
                    )
                )
                if model.event_type == "CommunicationSendRequested":
                    communication = await session.get(
                        CommunicationModel, model.aggregate_id, with_for_update=True
                    )
                    if communication is not None:
                        communication.status = CommunicationStatus.DEAD_LETTER
                        communication.last_error = error_text
            else:
                delay = min(
                    self._settings.outbox_retry_base_seconds * (2 ** (attempts - 1)),
                    self._settings.outbox_retry_max_seconds,
                )
                model.next_attempt_at = now + timedelta(seconds=delay)
        logger.warning(
            "outbox_event_failed",
            event_id=str(event.id),
            event_type=event.event_type,
            attempts=attempts,
            error=error_text,
        )

    @staticmethod
    def _to_domain(model: CommunicationModel) -> Communication:
        return Communication(
            id=model.id,
            matter_id=model.matter_id,
            work_item_id=model.work_item_id,
            review_package_id=model.review_package_id,
            review_record_id=model.review_record_id,
            channel=model.channel,
            target=model.target,
            content=model.content,
            content_hash=model.content_hash,
            status=model.status,
            requested_by=model.requested_by,
            correlation_id=model.correlation_id,
            external_message_id=model.external_message_id,
            attempts=model.attempts,
            last_error=model.last_error,
            queued_at=model.queued_at,
            sent_at=model.sent_at,
            version=model.version,
        )


async def mark_feishu_message_queued(message_id: UUID) -> None:
    async with get_session_factory()() as session, session.begin():
        model = await session.get(FeishuMessageModel, message_id, with_for_update=True)
        if model is not None and model.status == FeishuMessageStatus.RECEIVED:
            model.status = FeishuMessageStatus.QUEUED_FOR_ANALYSIS
