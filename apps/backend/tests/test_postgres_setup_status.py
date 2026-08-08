from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_setup_metadata_and_worker_request_persist_without_secret(
    tmp_path: Path,
) -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.agents.codex_health import (
        CodexHealthStatus,
        CodexRuntimeHealth,
    )
    from legal_workbench.application.setup import SetupService
    from legal_workbench.config import Settings
    from legal_workbench.domain.entities import IntegrationCredential, SystemSetting
    from legal_workbench.infrastructure.secrets import LocalSecretProvider
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    class HealthChecker:
        async def check(self) -> CodexRuntimeHealth:
            return CodexRuntimeHealth(
                status=CodexHealthStatus.UNAUTHENTICATED,
                executable="/opt/codex",
                detected_version="0.146.0",
                expected_version="0.146.0",
                authentication="missing_runtime_api_key",
                runtime_directory_writable=True,
                detail="Synthetic isolated Worker authentication is absent.",
            )

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    factory = SqlAlchemyUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    secrets = LocalSecretProvider(tmp_path / "setup-secrets")
    raw_secret = f"sensitive-feishu-{uuid4().hex}"
    secret_ref = secrets.write("feishu_app_secret", raw_secret)
    suffix = uuid4().hex[:10]
    try:
        async with factory() as uow:
            await uow.setup.save_setting(
                SystemSetting.create(
                    key="feishu.app_id",
                    value=f"cli_setup_{suffix}",
                    updated_by="postgres-setup-test",
                )
            )
            await uow.setup.save_credential(
                IntegrationCredential(
                    id=uuid4(),
                    provider="feishu",
                    credential_kind="app_secret",
                    secret_ref=secret_ref,
                    configured=True,
                    masked_hint="••••test",
                )
            )
            await uow.commit()

        setup = SetupService(
            factory,
            settings=Settings(
                environment="test",
                session_secret="test-session-secret-that-is-long-enough",
                _env_file=None,
            ),
            secret_provider=secrets,
            codex_health_checker=HealthChecker(),
            basic_services_probe=lambda: {"api": "ready", "postgresql": "ready"},
        )
        status = await setup.get_status(correlation_id=f"setup-pg:{suffix}")
        requested = await setup.request_codex_check(
            check_kind="validate",
            actor_id="postgres-setup-test",
            actor_source="test",
            correlation_id=f"setup-check-pg:{suffix}",
            idempotency_key=f"setup-check-pg:{suffix}",
        )

        async with engine.connect() as connection:
            check_row = (
                await connection.execute(
                    text(
                        "SELECT c.status, c.state, o.event_type "
                        "FROM integration_check_runs c "
                        "JOIN outbox_events o ON o.aggregate_id = c.id "
                        "WHERE c.id = :check_id"
                    ),
                    {"check_id": requested.check_run_id},
                )
            ).one()
            leaked = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM integration_credentials "
                        "WHERE coalesce(secret_ref, '') LIKE :secret "
                        "OR coalesce(masked_hint, '') LIKE :secret"
                    ),
                    {"secret": f"%{raw_secret}%"},
                )
            ).scalar_one()

        assert status.feishu.credentials.configured is True
        assert check_row == ("pending", "pending", "CodexSetupCheckRequested")
        assert leaked == 0
    finally:
        await engine.dispose()
