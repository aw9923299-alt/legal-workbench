from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from legal_workbench.agents.definitions import build_message_judgement_definition
from legal_workbench.application.agent_attempts import AgentAttemptService
from legal_workbench.domain.entities import AgentRun, ContextSnapshot
from legal_workbench.domain.enums import AgentAttemptStatus, AgentRunStatus
from legal_workbench.domain.errors import StaleAgentAttemptError


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_rejects_completion_from_expired_attempt() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.infrastructure.models import AgentRunAttemptModel
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
        source_type="fencing_test",
        source_id=f"fencing-{uuid4().hex}",
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
        status=AgentRunStatus.RUNNING,
        objective="Verify PostgreSQL fencing.",
        prompt_snapshot="non-sensitive fencing test",
        working_directory="/tmp/legal-workbench-fencing-test",
        attempt_number=1,
        max_attempts=2,
        correlation_id=f"fencing-{uuid4().hex}",
        created_by="integration-test",
        worker_id="worker-old",
        lease_expires_at=now + timedelta(seconds=60),
    )

    try:
        async with uow_factory() as uow:
            if await uow.agent_definitions.get(definition.id) is None:
                await uow.agent_definitions.add(definition)
            await uow.context_snapshots.add(snapshot)
            await uow.flush()
            await uow.agent_runs.add(run)
            await uow.flush()
            first = await AgentAttemptService(
                uow.agent_run_attempts, lease_seconds=60
            ).claim(
                run_id=run.id,
                attempt_number=1,
                worker_id="worker-old",
            )
            await uow.commit()

        async with session_factory() as session, session.begin():
            await session.execute(
                update(AgentRunAttemptModel)
                .where(
                    AgentRunAttemptModel.agent_run_id == run.id,
                    AgentRunAttemptModel.attempt_number == 1,
                )
                .values(lease_expires_at=now - timedelta(seconds=1))
            )

        async with uow_factory() as uow:
            attempt_service = AgentAttemptService(
                uow.agent_run_attempts, lease_seconds=60
            )
            with pytest.raises(StaleAgentAttemptError):
                await attempt_service.heartbeat(first)
            with pytest.raises(StaleAgentAttemptError):
                await attempt_service.complete(first)

        async with uow_factory() as uow:
            expired = await uow.agent_run_attempts.expire_current(
                run_id=run.id,
                attempt_number=1,
                finished_at=now + timedelta(seconds=61),
            )
            stored_run = await uow.agent_runs.get_for_update(run.id)
            assert stored_run is not None
            stored_run.attempt_number = 2
            stored_run.worker_id = "worker-current"
            await uow.agent_runs.save(stored_run)
            second = await AgentAttemptService(
                uow.agent_run_attempts, lease_seconds=60
            ).claim(
                run_id=run.id,
                attempt_number=2,
                worker_id="worker-current",
            )
            await uow.commit()

        assert expired is True
        assert second.lease_token != first.lease_token
        async with uow_factory() as uow:
            with pytest.raises(StaleAgentAttemptError):
                await AgentAttemptService(
                    uow.agent_run_attempts, lease_seconds=60
                ).complete(first)

        async with uow_factory() as uow:
            attempts = list(await uow.agent_run_attempts.list_by_run(run.id))
        assert [value.status for value in attempts] == [
            AgentAttemptStatus.EXPIRED,
            AgentAttemptStatus.RUNNING,
        ]
    finally:
        await engine.dispose()
