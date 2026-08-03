from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from legal_workbench.api.dependencies import get_if_match_version
from legal_workbench.domain.entities import WorkItem, WorkItemDependency
from legal_workbench.domain.enums import (
    DependencyStatus,
    DependencyType,
    Priority,
    PrioritySource,
    WorkItemAction,
    WorkItemStatus,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityVersionConflictError,
    InvalidStateTransitionError,
)


def work_item(*, status: WorkItemStatus = WorkItemStatus.TODO) -> WorkItem:
    item = WorkItem.create(
        matter_id=uuid4(),
        title="核对协议",
        owner_id="legal-owner",
        priority=Priority.HIGH,
        priority_source=PrioritySource.LEGAL_CONFIRMED,
        next_action="读取签署版",
        priority_reasons=["人工确认"],
    )
    item.status = status
    return item


def active_dependency(item: WorkItem) -> WorkItemDependency:
    return WorkItemDependency.create(
        work_item_id=item.id,
        dependency_type=DependencyType.MATERIAL,
        depends_on_work_item_id=None,
        external_party_id="business-owner",
        description="等待盖章版本",
    )


@pytest.mark.parametrize(
    ("initial", "action", "expected"),
    [
        (WorkItemStatus.TODO, WorkItemAction.START, WorkItemStatus.IN_PROGRESS),
        (WorkItemStatus.IN_PROGRESS, WorkItemAction.PAUSE, WorkItemStatus.PAUSED),
        (WorkItemStatus.WAITING, WorkItemAction.RESUME, WorkItemStatus.IN_PROGRESS),
        (WorkItemStatus.BLOCKED, WorkItemAction.RESUME, WorkItemStatus.IN_PROGRESS),
        (WorkItemStatus.DONE, WorkItemAction.REOPEN, WorkItemStatus.TODO),
        (WorkItemStatus.CANCELLED, WorkItemAction.REOPEN, WorkItemStatus.TODO),
    ],
)
def test_allowed_transitions(
    initial: WorkItemStatus, action: WorkItemAction, expected: WorkItemStatus
) -> None:
    item = work_item(status=initial)
    if initial == WorkItemStatus.WAITING:
        item.waiting_reason = "等待材料"
        item.waiting_since = datetime.now(UTC)
    if initial == WorkItemStatus.BLOCKED:
        item.is_blocked = True
        item.blocker_reason = "系统故障"
        item.blocker_owner_id = "it-owner"

    item.apply(
        action=action,
        actor_id="legal",
        reason="verified",
        expected_version=1,
        open_dependencies=[],
    )

    assert item.status == expected
    assert item.version == 2


def test_wait_requires_an_open_dependency() -> None:
    item = work_item(status=WorkItemStatus.IN_PROGRESS)

    with pytest.raises(InvalidStateTransitionError):
        item.apply(
            action=WorkItemAction.WAIT,
            actor_id="legal",
            reason="等待业务材料",
            expected_version=1,
            open_dependencies=[],
        )


def test_complete_rejects_open_dependencies() -> None:
    item = work_item(status=WorkItemStatus.IN_PROGRESS)

    with pytest.raises(InvalidStateTransitionError):
        item.apply(
            action=WorkItemAction.COMPLETE,
            actor_id="legal",
            reason="已完成",
            expected_version=1,
            open_dependencies=[active_dependency(item)],
        )


@pytest.mark.parametrize(
    "action",
    [WorkItemAction.PAUSE, WorkItemAction.BLOCK, WorkItemAction.CANCEL, WorkItemAction.REOPEN],
)
def test_reasoned_actions_reject_blank_reason(action: WorkItemAction) -> None:
    initial = WorkItemStatus.DONE if action == WorkItemAction.REOPEN else WorkItemStatus.IN_PROGRESS
    item = work_item(status=initial)

    with pytest.raises(DomainValidationError):
        item.apply(
            action=action,
            actor_id="legal",
            reason=" ",
            blocker_owner_id="it-owner",
            expected_version=1,
            open_dependencies=[],
        )


def test_block_requires_a_responsible_owner() -> None:
    item = work_item(status=WorkItemStatus.IN_PROGRESS)

    with pytest.raises(DomainValidationError):
        item.apply(
            action=WorkItemAction.BLOCK,
            actor_id="legal",
            reason="接口不可用",
            blocker_owner_id=None,
            expected_version=1,
            open_dependencies=[],
        )


def test_blocking_a_waiting_item_clears_waiting_state_atomically() -> None:
    item = work_item(status=WorkItemStatus.WAITING)
    item.waiting_party_id = "business-owner"
    item.waiting_reason = "等待材料"
    item.waiting_since = datetime.now(UTC)

    item.apply(
        action=WorkItemAction.BLOCK,
        actor_id="legal",
        reason="材料渠道故障",
        blocker_owner_id="it-owner",
        expected_version=1,
        open_dependencies=[active_dependency(item)],
    )

    assert item.status == WorkItemStatus.BLOCKED
    assert item.waiting_party_id is None
    assert item.waiting_reason is None
    assert item.waiting_since is None
    assert item.is_blocked is True


def test_cancelling_a_blocked_item_clears_active_block_flags() -> None:
    item = work_item(status=WorkItemStatus.BLOCKED)
    item.is_blocked = True
    item.blocker_reason = "系统故障"
    item.blocker_owner_id = "it-owner"

    item.apply(
        action=WorkItemAction.CANCEL,
        actor_id="legal",
        reason="事项终止",
        expected_version=1,
        open_dependencies=[],
    )

    assert item.status == WorkItemStatus.CANCELLED
    assert item.is_blocked is False
    assert item.blocker_reason is None
    assert item.blocker_owner_id is None
    assert item.cancel_reason == "事项终止"


def test_transition_rejects_stale_version() -> None:
    item = work_item()
    item.version = 3

    with pytest.raises(EntityVersionConflictError):
        item.apply(
            action=WorkItemAction.START,
            actor_id="legal",
            reason=None,
            expected_version=2,
            open_dependencies=[],
        )


def test_field_changes_are_domain_operations_and_increment_once() -> None:
    item = work_item(status=WorkItemStatus.IN_PROGRESS)
    deadline = datetime(2026, 8, 10, 18, tzinfo=UTC)

    item.apply(
        action=WorkItemAction.CHANGE_OWNER,
        actor_id="legal",
        reason="重新分工",
        owner_id="new-owner",
        expected_version=1,
        open_dependencies=[],
    )
    item.apply(
        action=WorkItemAction.CHANGE_DEADLINE,
        actor_id="legal",
        reason="业务计划调整",
        deadline=deadline,
        expected_version=2,
        open_dependencies=[],
    )
    item.apply(
        action=WorkItemAction.CHANGE_NEXT_ACTION,
        actor_id="legal",
        reason="材料已齐",
        next_action="形成审查意见",
        expected_version=3,
        open_dependencies=[],
    )

    assert item.owner_id == "new-owner"
    assert item.planned_complete_at == deadline
    assert item.next_action == "形成审查意见"
    assert item.version == 4


def test_dependency_resolution_is_versioned_and_idempotency_safe() -> None:
    item = work_item()
    dependency = active_dependency(item)

    dependency.resolve(actor_id="legal", expected_version=1)

    assert dependency.status == DependencyStatus.SATISFIED
    assert dependency.satisfied_at is not None
    assert dependency.version == 2
    with pytest.raises(InvalidStateTransitionError):
        dependency.resolve(actor_id="legal", expected_version=2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("header", "expected"),
    [("3", 3), ('"4"', 4), ('W/"5"', 5)],
)
async def test_if_match_accepts_supported_entity_version_forms(header: str, expected: int) -> None:
    assert await get_if_match_version(header) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("header", [None, "", "0", "latest", 'W/"nope"'])
async def test_if_match_rejects_missing_or_invalid_versions(header: str | None) -> None:
    with pytest.raises(HTTPException):
        await get_if_match_version(header)
