from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

import pytest
from scripts.smoke_test_downstream_loop import _validated_redis_test_url

from legal_workbench.application.analysis_recovery import AnalysisRecoveryService
from legal_workbench.domain.entities import FeishuMessage, FeishuRawEvent
from legal_workbench.domain.enums import FeishuEventStatus, FeishuMessageStatus


class RedisDatabaseInspector(Protocol):
    async def dbsize(self) -> int: ...


async def _require_empty_test_database(redis: RedisDatabaseInspector) -> None:
    if await redis.dbsize() != 0:
        raise RuntimeError("Dedicated Redis DB 15 is not empty; refusing to flush")


@pytest.mark.asyncio
async def test_redis_flush_guard_rejects_nonempty_database() -> None:
    class NonEmptyRedis:
        async def dbsize(self) -> int:
            return 1

    with pytest.raises(RuntimeError, match="not empty"):
        await _require_empty_test_database(NonEmptyRedis())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_isolated_redis_flush_recovers_durable_postgres_work() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")
    if os.getenv("RUN_REDIS_INTEGRATION_TESTS") != "1":
        pytest.skip("Destructive isolated Redis integration tests are disabled")

    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    redis_url = _validated_redis_test_url(
        os.environ["LEGAL_WORKBENCH_TEST_REDIS_URL"]
    )

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    uow_factory = SqlAlchemyUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    redis = Redis.from_url(redis_url, decode_responses=True)
    marker = f"legal-workbench:test-delivery:{uuid4().hex}"
    now = datetime.now(UTC)
    event = FeishuRawEvent(
        id=uuid4(),
        event_id=f"evt-redis-flush-{uuid4().hex}",
        event_type="im.message.receive_v1",
        tenant_key="tenant-redis-flush-test",
        app_id="redis-flush-test",
        schema_version="2.0",
        raw_payload={"synthetic": True},
        payload_hash=uuid4().hex * 2,
        status=FeishuEventStatus.RECEIVED,
    )
    external_message_id = f"om_redis_flush_{uuid4().hex}"
    message = FeishuMessage(
        id=uuid4(),
        event_id=event.id,
        tenant_key=event.tenant_key,
        message_id=external_message_id,
        chat_id="oc_redis_flush_test",
        thread_id=None,
        root_id=None,
        parent_id=None,
        sender_id="ou_redis_flush_test",
        sender_type="user",
        message_type="text",
        content={"text": "synthetic durable recovery test"},
        mentions=[],
        create_time=now,
        update_time=None,
        raw_message={"synthetic": True},
        plain_text="synthetic durable recovery test",
        structured_content={"text": "synthetic durable recovery test"},
        status=FeishuMessageStatus.QUEUED_FOR_ANALYSIS,
    )

    try:
        assert await redis.ping() is True
        await _require_empty_test_database(redis)
        await redis.set(marker, "temporary-delivery")
        if await redis.dbsize() != 1 or await redis.get(marker) != "temporary-delivery":
            await redis.delete(marker)
            raise RuntimeError("Dedicated Redis DB 15 changed concurrently; refusing to flush")
        async with uow_factory() as uow:
            await uow.feishu.add_event(event)
            await uow.feishu.add_message(message)
            await uow.commit()

        await redis.flushdb()
        assert await redis.get(marker) is None

        result = await AnalysisRecoveryService(
            uow_factory,
            batch_size=10_000,
        ).recover()

        async with uow_factory() as uow:
            stored_message = await uow.feishu.get_message_by_id(message.id)
            recovery_event_exists = await uow.outbox_events.exists_pending(
                event_type=AnalysisRecoveryService.EVENT_TYPE,
                aggregate_id=message.id,
            )
        assert stored_message is not None
        assert recovery_event_exists is True
        assert result.missing_runs_requeued >= 1
    finally:
        await redis.delete(marker)
        await redis.aclose()
        await engine.dispose()
