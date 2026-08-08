from __future__ import annotations

import os
from uuid import uuid4

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_work_item_lifecycle_is_versioned_audited_and_idempotent() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.application.commands import CreateDependencyCommand
    from legal_workbench.application.work_item_lifecycle import (
        ResolveDependencyCommand,
        ResolveDependencyHandler,
        WorkItemActionCommand,
        WorkItemLifecycleHandler,
    )
    from legal_workbench.application.workflow_handlers import CreateDependencyHandler
    from legal_workbench.domain.entities import LegalMatter, WorkItem
    from legal_workbench.domain.enums import (
        BusinessImpact,
        Confidentiality,
        DependencyType,
        LegalRisk,
        MatterCategory,
        Priority,
        PrioritySource,
        WorkItemAction,
        WorkItemStatus,
    )
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    uow_factory = SqlAlchemyUnitOfWorkFactory(async_sessionmaker(engine, expire_on_commit=False))
    unique = uuid4().hex
    matter = LegalMatter.create(
        title=f"WorkItem lifecycle {unique}",
        primary_category=MatterCategory.CONTRACT,
        secondary_categories=[],
        owner_id="legal-owner",
        legal_risk=LegalRisk.MEDIUM,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.INTERNAL,
        requester_ids=[],
        summary=None,
        objective=None,
    )
    work_item = WorkItem.create(
        matter_id=matter.id,
        title="完成闭环验证",
        owner_id="legal-owner",
        priority=Priority.HIGH,
        priority_source=PrioritySource.LEGAL_CONFIRMED,
        next_action="开始处理",
        priority_reasons=["集成测试"],
    )
    lifecycle = WorkItemLifecycleHandler(uow_factory)

    async def action(
        value: WorkItemAction,
        version: int,
        *,
        reason: str | None = None,
        key: str | None = None,
    ):
        return await lifecycle.execute(
            WorkItemActionCommand(
                work_item_id=work_item.id,
                action=value,
                expected_version=version,
                actor_id="legal-reviewer",
                correlation_id=f"{value.value}-{unique}",
                idempotency_key=key or f"{value.value}-{unique}",
                reason=reason,
            )
        )

    try:
        async with uow_factory() as uow:
            await uow.matters.add(matter)
            await uow.work_items.add(work_item)
            await uow.commit()

        started = await action(WorkItemAction.START, 1)
        assert (started.status, started.version) == (WorkItemStatus.IN_PROGRESS, 2)

        dependency = await CreateDependencyHandler(uow_factory).execute(
            CreateDependencyCommand(
                work_item_id=work_item.id,
                work_item_version=started.version,
                actor_id="legal-reviewer",
                correlation_id=f"dependency-{unique}",
                idempotency_key=f"dependency-{unique}",
                dependency_type=DependencyType.MATERIAL,
                external_party_id="business-owner",
                description="等待签署版本",
            )
        )
        assert dependency.work_item_version == 3

        waiting = await action(WorkItemAction.WAIT, 3, reason="等待签署版本")
        assert (waiting.status, waiting.version) == (WorkItemStatus.WAITING, 4)

        resolved = await ResolveDependencyHandler(uow_factory).execute(
            ResolveDependencyCommand(
                work_item_id=work_item.id,
                dependency_id=dependency.dependency_id,
                work_item_version=waiting.version,
                dependency_version=1,
                actor_id="legal-reviewer",
                correlation_id=f"resolve-{unique}",
                idempotency_key=f"resolve-{unique}",
                reason="签署版本已收到",
            )
        )
        assert (resolved.work_item_version, resolved.dependency_version) == (5, 2)

        resumed = await action(WorkItemAction.RESUME, 5)
        assert (resumed.status, resumed.version) == (WorkItemStatus.IN_PROGRESS, 6)

        completed = await action(
            WorkItemAction.COMPLETE,
            6,
            reason="闭环验证完成",
            key=f"complete-{unique}",
        )
        replay = await action(
            WorkItemAction.COMPLETE,
            6,
            reason="闭环验证完成",
            key=f"complete-{unique}",
        )
        assert (completed.status, completed.version) == (WorkItemStatus.DONE, 7)
        assert replay.idempotent_replay is True
        assert replay.version == completed.version

        async with engine.connect() as connection:
            persisted = (
                await connection.execute(
                    text(
                        "SELECT w.status, w.version, d.status, d.version, d.satisfied_by, "
                        "(SELECT count(*) FROM audit_events a WHERE a.aggregate_id IN "
                        "(:work_item_id, :dependency_id)), "
                        "(SELECT count(*) FROM outbox_events o WHERE o.aggregate_id IN "
                        "(:work_item_id, :dependency_id)), "
                        "(SELECT count(*) FROM idempotency_records i "
                        "WHERE i.idempotency_key = :complete_key) "
                        "FROM work_items w JOIN work_item_dependencies d "
                        "ON d.work_item_id = w.id WHERE w.id = :work_item_id"
                    ),
                    {
                        "work_item_id": work_item.id,
                        "dependency_id": dependency.dependency_id,
                        "complete_key": f"complete-{unique}",
                    },
                )
            ).one()

        assert persisted == (
            WorkItemStatus.DONE.value,
            7,
            "satisfied",
            2,
            "legal-reviewer",
            6,
            6,
            1,
        )
    finally:
        await engine.dispose()
