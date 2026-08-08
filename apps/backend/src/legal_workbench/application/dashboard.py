from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from legal_workbench.domain.enums import LegalRisk, Priority


class DashboardGroup(StrEnum):
    TODAY_MUST_HANDLE = "today_must_handle"
    OVERDUE = "overdue"
    PENDING_CANDIDATES = "pending_candidates"
    ANALYSIS_FAILED = "analysis_failed"
    WAITING_OTHERS = "waiting_others"
    UPCOMING_DEADLINES = "upcoming_deadlines"
    PENDING_OUTBOUND_REVIEW = "pending_outbound_review"
    SYSTEM_ABNORMAL = "system_abnormal"


@dataclass(frozen=True, slots=True)
class DashboardSourceRecord:
    id: UUID | str
    group: DashboardGroup
    object_type: str
    title: str
    description: str
    href: str
    status: str
    created_at: datetime
    reason: str
    due_at: datetime | None = None
    is_hard_deadline: bool = False
    legal_risk: LegalRisk = LegalRisk.PENDING
    confirmed_priority: Priority | None = None
    ai_suggested_priority: Priority | None = None
    waiting_since: datetime | None = None


class DashboardDataSource(Protocol):
    async def load(self, *, actor_id: str, now: datetime) -> list[DashboardSourceRecord]: ...


@dataclass(frozen=True, slots=True)
class DashboardItem:
    id: str
    group: DashboardGroup
    object_type: str
    title: str
    description: str
    href: str
    status: str
    created_at: datetime
    due_at: datetime | None
    is_hard_deadline: bool
    is_overdue: bool
    legal_risk: LegalRisk
    confirmed_priority: Priority | None
    ai_suggested_priority: Priority | None
    waiting_since: datetime | None
    waiting_seconds: int
    ranking_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DashboardResponse:
    generated_at: datetime
    today_must_handle: tuple[DashboardItem, ...]
    overdue: tuple[DashboardItem, ...]
    pending_candidates: tuple[DashboardItem, ...]
    analysis_failed: tuple[DashboardItem, ...]
    waiting_others: tuple[DashboardItem, ...]
    upcoming_deadlines: tuple[DashboardItem, ...]
    pending_outbound_review: tuple[DashboardItem, ...]
    system_abnormal: tuple[DashboardItem, ...]

    def all_items(self) -> tuple[DashboardItem, ...]:
        return tuple(item for group in DashboardGroup for item in getattr(self, group.value))


RISK_ORDER: dict[LegalRisk, int] = {
    LegalRisk.CRITICAL: 0,
    LegalRisk.HIGH: 1,
    LegalRisk.MEDIUM: 2,
    LegalRisk.LOW: 3,
    LegalRisk.PENDING: 4,
}
PRIORITY_ORDER: dict[Priority | None, int] = {
    Priority.URGENT: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
    None: 4,
}


def queue_sort_key(item: DashboardItem) -> tuple[object, ...]:
    return (
        0 if item.is_hard_deadline else 1,
        0 if item.is_overdue else 1,
        RISK_ORDER[item.legal_risk],
        PRIORITY_ORDER[item.confirmed_priority],
        -item.waiting_seconds,
        item.created_at,
        str(item.id),
    )


class DashboardQueueService:
    def __init__(self, source: DashboardDataSource) -> None:
        self._source = source

    async def get_today(self, *, actor_id: str, now: datetime) -> DashboardResponse:
        if not actor_id.strip():
            raise ValueError("Dashboard actor is required.")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Dashboard time must include a timezone.")
        groups: dict[DashboardGroup, list[DashboardItem]] = {group: [] for group in DashboardGroup}
        for record in await self._source.load(actor_id=actor_id, now=now):
            item = self._materialize(record, now=now)
            groups[item.group].append(item)
        for values in groups.values():
            values.sort(key=queue_sort_key)
        return DashboardResponse(
            generated_at=now,
            **{group.value: tuple(groups[group]) for group in DashboardGroup},
        )

    @staticmethod
    def _materialize(record: DashboardSourceRecord, *, now: datetime) -> DashboardItem:
        is_overdue = record.due_at is not None and record.due_at < now
        waiting_seconds = (
            max(0, int((now - record.waiting_since).total_seconds())) if record.waiting_since else 0
        )
        reasons = [record.reason]
        if record.is_hard_deadline:
            reasons.append("硬期限")
        if is_overdue:
            reasons.append("已逾期")
        if record.legal_risk != LegalRisk.PENDING:
            reasons.append(f"法律风险: {record.legal_risk.value}")
        if record.confirmed_priority is not None:
            reasons.append(f"人工确认优先级: {record.confirmed_priority.value}")
        if waiting_seconds:
            reasons.append(f"已等待 {waiting_seconds // 3600} 小时")
        return DashboardItem(
            id=str(record.id),
            group=record.group,
            object_type=record.object_type,
            title=record.title,
            description=record.description,
            href=record.href,
            status=record.status,
            created_at=record.created_at,
            due_at=record.due_at,
            is_hard_deadline=record.is_hard_deadline,
            is_overdue=is_overdue,
            legal_risk=record.legal_risk,
            confirmed_priority=record.confirmed_priority,
            ai_suggested_priority=record.ai_suggested_priority,
            waiting_since=record.waiting_since,
            waiting_seconds=waiting_seconds,
            ranking_reasons=tuple(reasons),
        )
