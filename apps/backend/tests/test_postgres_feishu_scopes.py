from __future__ import annotations

import os
from uuid import uuid4

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_feishu_scope_decisions_are_persisted_audited_and_versioned() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.application.feishu_scopes import FeishuScopeService
    from legal_workbench.domain.enums import IntegrationSyncMode
    from legal_workbench.domain.errors import EntityVersionConflictError
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    factory = SqlAlchemyUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    service = FeishuScopeService(factory)
    unique = uuid4().hex
    try:
        scope = await service.register_known_chat(
            chat_id=f"oc_scope_{unique}",
            display_name="合成 PostgreSQL 群",
            actor_id="postgres-scope-test",
            actor_source="test",
            correlation_id=f"register:{unique}",
            idempotency_key=f"register:{unique}",
        )
        allowed = await service.change_scope(
            scope_id=scope.id,
            expected_version=1,
            action="allow",
            sync_mode=IntegrationSyncMode.ALL_MESSAGES,
            actor_id="postgres-scope-test",
            actor_source="test",
            correlation_id=f"allow:{unique}",
            idempotency_key=f"allow:{unique}",
        )
        with pytest.raises(EntityVersionConflictError):
            await service.change_scope(
                scope_id=scope.id,
                expected_version=1,
                action="exclude",
                sync_mode=None,
                actor_id="postgres-scope-test",
                actor_source="test",
                correlation_id=f"stale:{unique}",
                idempotency_key=f"stale:{unique}",
            )
        deferred = await service.defer_compensation(
            scope_id=scope.id,
            expected_version=allowed.version,
            actor_id="postgres-scope-test",
            actor_source="test",
            correlation_id=f"compensate:{unique}",
            idempotency_key=f"compensate:{unique}",
        )

        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT status, sync_mode, last_compensation_status, version "
                        "FROM integration_scopes WHERE id = :scope_id"
                    ),
                    {"scope_id": scope.id},
                )
            ).one()
            audit_count = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM audit_events "
                        "WHERE aggregate_type = 'integration_scope' "
                        "AND aggregate_id = :scope_id"
                    ),
                    {"scope_id": scope.id},
                )
            ).scalar_one()

        assert deferred.state == "not_executed"
        assert deferred.error_code == "REAL_FEISHU_PHASE_DEFERRED"
        assert row == ("allowed", "all_messages", "not_executed", 3)
        assert audit_count == 3
    finally:
        await engine.dispose()
