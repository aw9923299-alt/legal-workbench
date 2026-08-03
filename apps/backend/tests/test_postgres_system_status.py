from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from legal_workbench.agents.definitions import build_message_judgement_definition
from legal_workbench.domain.entities import AgentRun, ContextSnapshot
from legal_workbench.domain.enums import AgentRunStatus
from legal_workbench.infrastructure.system_status import _pending_recovery_count


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pending_recovery_excludes_runs_without_feishu_message() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    uow_factory = SqlAlchemyUnitOfWorkFactory(session_factory)
    now = datetime.now(UTC)
    definition = build_message_judgement_definition()
    snapshot = ContextSnapshot(
        id=uuid4(),
        source_type="system_status_test",
        source_id=f"system-status-{uuid4().hex}",
        source_ids=[],
        message_ids=[],
        file_ids=[],
        relevant_matter_ids=[],
        participant_ids=[],
        permission_snapshot={},
        generated_at=now,
        content_hash=uuid4().hex * 2,
    )
    run = AgentRun(
        id=uuid4(),
        agent_definition_id=definition.id,
        context_snapshot_id=snapshot.id,
        status=AgentRunStatus.QUEUED,
        objective="Verify recovery status selection.",
        prompt_snapshot="non-sensitive system status test",
        working_directory=f"/tmp/{uuid4()}",
        attempt_number=1,
        max_attempts=2,
        correlation_id=f"system-status-{uuid4().hex}",
        created_by="integration-test",
        feishu_message_id=None,
        created_at=now - timedelta(minutes=10),
        updated_at=now - timedelta(minutes=10),
    )

    try:
        async with session_factory() as session:
            before = await _pending_recovery_count(
                session,
                now=now,
                stale_after_seconds=120,
            )
        async with uow_factory() as uow:
            if await uow.agent_definitions.get(definition.id) is None:
                await uow.agent_definitions.add(definition)
            await uow.context_snapshots.add(snapshot)
            await uow.flush()
            await uow.agent_runs.add(run)
            await uow.commit()
        async with session_factory() as session:
            after = await _pending_recovery_count(
                session,
                now=now,
                stale_after_seconds=120,
            )

        assert after == before
    finally:
        await engine.dispose()
