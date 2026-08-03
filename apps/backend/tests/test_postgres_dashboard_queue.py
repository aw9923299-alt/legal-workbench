from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dashboard_projection_reads_and_orders_postgresql_facts() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.application.dashboard import DashboardQueueService
    from legal_workbench.domain.entities import Deadline, LegalMatter, WorkItem
    from legal_workbench.domain.enums import (
        BusinessImpact,
        Confidentiality,
        DeadlineSource,
        DeadlineType,
        LegalRisk,
        MatterCategory,
        Priority,
        PrioritySource,
    )
    from legal_workbench.infrastructure.dashboard import SqlAlchemyDashboardDataSource
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

    engine = create_async_engine(
        os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"], pool_pre_ping=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    uow_factory = SqlAlchemyUnitOfWorkFactory(session_factory)
    unique = uuid4().hex
    owner = f"dashboard-{unique}"
    now = datetime(2026, 8, 3, 9, tzinfo=UTC)
    matter = LegalMatter.create(
        title=f"Dashboard projection {unique}",
        primary_category=MatterCategory.CONTRACT,
        secondary_categories=[],
        owner_id=owner,
        legal_risk=LegalRisk.HIGH,
        business_impact=BusinessImpact.PROJECT,
        confidentiality=Confidentiality.INTERNAL,
        requester_ids=[],
        summary=None,
        objective=None,
    )
    hard_item = WorkItem.create(
        matter_id=matter.id,
        title="明日硬期限",
        owner_id=owner,
        priority=Priority.MEDIUM,
        priority_source=PrioritySource.LEGAL_CONFIRMED,
        next_action="准备申报",
        priority_reasons=["法务确认"],
    )
    overdue_item = WorkItem.create(
        matter_id=matter.id,
        title="已逾期软期限",
        owner_id=owner,
        priority=Priority.MEDIUM,
        priority_source=PrioritySource.LEGAL_CONFIRMED,
        next_action="补齐材料",
        priority_reasons=["法务确认"],
    )
    work_deadline = Deadline.create(
        deadline_type=DeadlineType.INTERNAL,
        source=DeadlineSource.LEGAL_CONFIRMED,
        due_at=now + timedelta(days=2),
        timezone="UTC",
        is_hard=False,
        matter_id=None,
        work_item_id=hard_item.id,
        source_reference="test-work-soft",
        confidence=None,
        reminder_policy={},
        actor_id=owner,
    )
    matter_deadline = Deadline.create(
        deadline_type=DeadlineType.LEGAL,
        source=DeadlineSource.LEGAL_CONFIRMED,
        due_at=now + timedelta(days=1),
        timezone="UTC",
        is_hard=True,
        matter_id=matter.id,
        work_item_id=None,
        source_reference="test-matter-hard",
        confidence=None,
        reminder_policy={},
        actor_id=owner,
    )
    overdue_deadline = Deadline.create(
        deadline_type=DeadlineType.INTERNAL,
        source=DeadlineSource.LEGAL_CONFIRMED,
        due_at=now - timedelta(hours=1),
        timezone="UTC",
        is_hard=False,
        matter_id=None,
        work_item_id=overdue_item.id,
        source_reference="test-soft",
        confidence=None,
        reminder_policy={},
        actor_id=owner,
    )

    try:
        async with uow_factory() as uow:
            await uow.matters.add(matter)
            await uow.flush()
            await uow.work_items.add_many([hard_item, overdue_item])
            await uow.flush()
            await uow.deadlines.add(work_deadline)
            await uow.deadlines.add(matter_deadline)
            await uow.deadlines.add(overdue_deadline)
            await uow.commit()

        queue = await DashboardQueueService(
            SqlAlchemyDashboardDataSource(session_factory)
        ).get_today(actor_id=owner, now=now)

        assert [item.id for item in queue.today_must_handle[:2]] == [
            str(hard_item.id),
            str(overdue_item.id),
        ]
        assert [item.id for item in queue.overdue] == [str(overdue_item.id)]
        assert queue.today_must_handle[0].is_hard_deadline is True
        assert queue.today_must_handle[0].due_at == matter_deadline.due_at
        assert queue.today_must_handle[0].href == f"/matters/{matter.id}"
    finally:
        await engine.dispose()
