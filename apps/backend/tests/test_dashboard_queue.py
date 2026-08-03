from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from legal_workbench.api.schemas.dashboard import DashboardTodayResponse
from legal_workbench.application.dashboard import (
    DashboardGroup,
    DashboardQueueService,
    DashboardSourceRecord,
)
from legal_workbench.domain.enums import LegalRisk, Priority
from legal_workbench.infrastructure.dashboard import OperationalHealthDashboardDataSource
from legal_workbench.infrastructure.system_status import SystemStatusService

NOW = datetime(2026, 8, 3, 9, tzinfo=UTC)


def record(
    number: int,
    *,
    group: DashboardGroup = DashboardGroup.TODAY_MUST_HANDLE,
    due_at: datetime | None = None,
    hard: bool = False,
    risk: LegalRisk = LegalRisk.MEDIUM,
    priority: Priority | None = Priority.MEDIUM,
    ai_priority: Priority | None = None,
    waiting_since: datetime | None = None,
    created_at: datetime | None = None,
) -> DashboardSourceRecord:
    item_id = UUID(int=number)
    return DashboardSourceRecord(
        id=item_id,
        group=group,
        object_type="work_item",
        title=f"队列项目 {number}",
        description="下一步行动",
        href=f"/matters/{item_id}",
        status="todo",
        created_at=created_at or NOW - timedelta(hours=number),
        due_at=due_at,
        is_hard_deadline=hard,
        legal_risk=risk,
        confirmed_priority=priority,
        ai_suggested_priority=ai_priority,
        waiting_since=waiting_since,
        reason="满足测试队列规则",
    )


class FakeDashboardSource:
    def __init__(self, values: list[DashboardSourceRecord]) -> None:
        self.values = values

    async def load(self, *, actor_id: str, now: datetime) -> list[DashboardSourceRecord]:
        assert actor_id == "legal"
        assert now == NOW
        return self.values


@pytest.mark.asyncio
async def test_dashboard_orders_hard_deadline_before_soft_overdue() -> None:
    hard = record(1, due_at=NOW + timedelta(days=1), hard=True)
    overdue = record(2, due_at=NOW - timedelta(hours=1), hard=False)

    queue = await DashboardQueueService(FakeDashboardSource([overdue, hard])).get_today(
        actor_id="legal", now=NOW
    )

    assert [item.id for item in queue.today_must_handle] == [str(hard.id), str(overdue.id)]
    assert "硬期限" in queue.today_must_handle[0].ranking_reasons
    assert "已逾期" in queue.today_must_handle[1].ranking_reasons


@pytest.mark.asyncio
async def test_dashboard_uses_risk_then_human_priority_but_not_ai_priority() -> None:
    low_risk_urgent = record(1, risk=LegalRisk.LOW, priority=Priority.URGENT)
    high_risk_medium = record(2, risk=LegalRisk.HIGH, priority=Priority.MEDIUM)
    old_without_confirmation = record(
        3,
        risk=LegalRisk.MEDIUM,
        priority=None,
        ai_priority=Priority.URGENT,
        created_at=NOW - timedelta(days=2),
    )
    newer_human_low = record(
        4,
        risk=LegalRisk.MEDIUM,
        priority=Priority.LOW,
        created_at=NOW - timedelta(days=1),
    )

    queue = await DashboardQueueService(
        FakeDashboardSource(
            [low_risk_urgent, old_without_confirmation, newer_human_low, high_risk_medium]
        )
    ).get_today(actor_id="legal", now=NOW)

    assert [item.id for item in queue.today_must_handle] == [
        str(high_risk_medium.id),
        str(newer_human_low.id),
        str(old_without_confirmation.id),
        str(low_risk_urgent.id),
    ]
    assert queue.today_must_handle[2].ai_suggested_priority == Priority.URGENT
    assert queue.today_must_handle[2].confirmed_priority is None


@pytest.mark.asyncio
async def test_waiting_duration_breaks_an_otherwise_equal_tie() -> None:
    longer = record(1, waiting_since=NOW - timedelta(days=2))
    shorter = record(2, waiting_since=NOW - timedelta(hours=2))

    queue = await DashboardQueueService(FakeDashboardSource([shorter, longer])).get_today(
        actor_id="legal", now=NOW
    )

    assert [item.id for item in queue.today_must_handle] == [
        str(longer.id),
        str(shorter.id),
    ]
    assert queue.today_must_handle[0].waiting_seconds == 2 * 24 * 60 * 60


@pytest.mark.asyncio
async def test_dashboard_returns_all_required_groups_and_real_routes() -> None:
    values = [record(index + 1, group=group) for index, group in enumerate(DashboardGroup)]

    queue = await DashboardQueueService(FakeDashboardSource(values)).get_today(
        actor_id="legal", now=NOW
    )

    assert len(queue.all_items()) == len(DashboardGroup)
    assert all(
        item.href.startswith(
            ("/inbox/", "/candidates/", "/matters/", "/agent-runs/", "/reviews", "/system")
        )
        for item in queue.all_items()
    )
    assert {item.group for item in queue.all_items()} == set(DashboardGroup)
    encoded = DashboardTodayResponse.model_validate(queue)
    assert encoded.today_must_handle[0].id == str(values[0].id)


@pytest.mark.asyncio
async def test_health_probe_failure_becomes_a_safe_dashboard_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_snapshot(_: SystemStatusService) -> None:
        raise OSError("postgresql://secret:secret@localhost/database")

    monkeypatch.setattr(SystemStatusService, "snapshot", fail_snapshot)

    items = await OperationalHealthDashboardDataSource().load(actor_id="legal", now=NOW)

    assert len(items) == 1
    assert items[0].group == DashboardGroup.SYSTEM_ABNORMAL
    assert items[0].href == "/system"
    assert "secret" not in items[0].description


@pytest.mark.asyncio
async def test_dashboard_http_contract_uses_authenticated_actor() -> None:
    from httpx import ASGITransport, AsyncClient

    from legal_workbench.api.auth import RequestActor
    from legal_workbench.api.dependencies import get_actor_id, get_request_actor
    from legal_workbench.api.routes.dashboard import get_dashboard_service
    from legal_workbench.main import app

    class ApiSource:
        async def load(self, *, actor_id: str, now: datetime) -> list[DashboardSourceRecord]:
            assert actor_id == "legal"
            return [
                DashboardSourceRecord(
                    id="work-http",
                    group=DashboardGroup.TODAY_MUST_HANDLE,
                    object_type="work_item",
                    title="HTTP 工作队列",
                    description="接口契约",
                    href="/matters/matter-http",
                    status="todo",
                    created_at=now - timedelta(hours=1),
                    reason="接口测试",
                )
            ]

    app.dependency_overrides[get_actor_id] = lambda: "legal"
    app.dependency_overrides[get_request_actor] = lambda: RequestActor(
        actor_id="legal", identity_source="test"
    )
    app.dependency_overrides[get_dashboard_service] = lambda: DashboardQueueService(ApiSource())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/api/v1/dashboard/today")
    finally:
        app.dependency_overrides.pop(get_actor_id, None)
        app.dependency_overrides.pop(get_request_actor, None)
        app.dependency_overrides.pop(get_dashboard_service, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["todayMustHandle"][0]["id"] == "work-http"
    assert body["todayMustHandle"][0]["href"] == "/matters/matter-http"
    assert body["systemAbnormal"] == []
