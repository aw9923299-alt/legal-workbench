from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_outbox_dead_letter_requeue_is_audited_and_idempotent() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.config import Settings
    from legal_workbench.infrastructure.models import (
        AuditEventModel,
        IdempotencyRecordModel,
        OutboxDeadLetterModel,
        OutboxEventModel,
    )
    from legal_workbench.infrastructure.outbox import OutboxDispatcher

    database_url = os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"]
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    dead_letter_id = uuid4()
    aggregate_id = uuid4()
    try:
        async with session_factory() as session, session.begin():
            session.add(
                OutboxDeadLetterModel(
                    id=dead_letter_id,
                    original_event_id=uuid4(),
                    event_type="MessageCandidateCreated",
                    aggregate_type="message_candidate",
                    aggregate_id=aggregate_id,
                    payload={"candidateId": str(aggregate_id)},
                    correlation_id="corr-original",
                    attempts=5,
                    last_error="simulated failure",
                    failed_at=datetime.now(UTC),
                )
            )
        dispatcher = OutboxDispatcher(
            session_factory=session_factory,
            settings=Settings(database_url=database_url, _env_file=None),
        )
        first = await dispatcher.requeue_dead_letter(
            dead_letter_id,
            actor_id="local-legal-user",
            actor_source="local_session",
            correlation_id="corr-requeue",
            idempotency_key="idem-requeue",
        )
        replay = await dispatcher.requeue_dead_letter(
            dead_letter_id,
            actor_id="local-legal-user",
            actor_source="local_session",
            correlation_id="corr-requeue-retry",
            idempotency_key="idem-requeue",
        )
        async with session_factory() as session:
            outbox_count = await session.scalar(
                select(func.count()).select_from(OutboxEventModel).where(
                    OutboxEventModel.id == first.outbox_event_id
                )
            )
            audit_count = await session.scalar(
                select(func.count()).select_from(AuditEventModel).where(
                    AuditEventModel.aggregate_id == dead_letter_id,
                    AuditEventModel.event_type == "outbox_dead_letter_requeued",
                )
            )
            idempotency_count = await session.scalar(
                select(func.count()).select_from(IdempotencyRecordModel).where(
                    IdempotencyRecordModel.operation
                    == f"requeue_outbox_dead_letter:{dead_letter_id}"
                )
            )
        assert first.idempotent_replay is False
        assert replay.idempotent_replay is True
        assert replay.outbox_event_id == first.outbox_event_id
        assert outbox_count == 1
        assert audit_count == 1
        assert idempotency_count == 1
    finally:
        await engine.dispose()
