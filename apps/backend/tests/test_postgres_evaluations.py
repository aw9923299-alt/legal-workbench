from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fake_evaluation_suite_persists_to_postgresql() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.application.evaluations import (
        EvaluationService,
        RunEvaluationCommand,
    )
    from legal_workbench.domain.enums import EvaluationRunStatus, EvaluationRuntimeType
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    factory = SqlAlchemyUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "evaluations"
        / "message_judgement_v1.json"
    )
    correlation_id = f"evaluation-pg:{uuid4()}"
    try:
        report = await EvaluationService(factory).run(
            RunEvaluationCommand(
                fixture_path=fixture,
                runtime_type=EvaluationRuntimeType.FAKE,
                allow_real_runtime=False,
                actor_id="postgres-evaluator",
                actor_source="test",
                correlation_id=correlation_id,
                idempotency_key=f"evaluation-pg:{uuid4()}",
            )
        )

        async with engine.connect() as connection:
            persisted = (
                await connection.execute(
                    text(
                        "SELECT r.status, r.runtime_type, r.agent_definition_version, "
                        "r.metrics->>'case_count', count(er.id), "
                        "count(*) FILTER (WHERE er.failure_code IS NULL), "
                        "count(*) FILTER (WHERE er.candidate_created) "
                        "FROM evaluation_runs r "
                        "JOIN evaluation_results er ON er.evaluation_run_id = r.id "
                        "WHERE r.id = :run_id "
                        "GROUP BY r.status, r.runtime_type, r.agent_definition_version, "
                        "r.metrics->>'case_count'"
                    ),
                    {"run_id": report.run.id},
                )
            ).one()
            audit_count = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM audit_events "
                        "WHERE aggregate_id = :run_id AND aggregate_type = 'evaluation_run'"
                    ),
                    {"run_id": report.run.id},
                )
            ).scalar_one()

        assert report.run.status == EvaluationRunStatus.COMPLETED
        assert persisted == ("completed", "fake", "2.2.0", "11", 11, 11, 8)
        assert audit_count == 2
    finally:
        await engine.dispose()
