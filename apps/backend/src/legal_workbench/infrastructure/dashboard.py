from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from legal_workbench.application.dashboard import (
    DashboardDataSource,
    DashboardGroup,
    DashboardSourceRecord,
)
from legal_workbench.domain.enums import (
    AgentRunStatus,
    CandidateStatus,
    DeadlineStatus,
    FeishuMessageStatus,
    IntegrationConnectionStatus,
    LegalRisk,
    MatterLifecycleStatus,
    Priority,
    PrioritySource,
    ReviewPackageStatus,
    ReviewPackageType,
    WorkItemStatus,
)
from legal_workbench.infrastructure.models import (
    AgentRunModel,
    DeadlineModel,
    FeishuMessageModel,
    IntegrationConnectionModel,
    LegalMatterModel,
    MessageCandidateModel,
    OutboxDeadLetterModel,
    ReviewPackageModel,
    WorkItemModel,
)
from legal_workbench.infrastructure.system_status import SystemStatusService


class CompositeDashboardDataSource:
    def __init__(self, *sources: DashboardDataSource) -> None:
        self._sources = sources

    async def load(self, *, actor_id: str, now: datetime) -> list[DashboardSourceRecord]:
        values = await asyncio.gather(
            *(source.load(actor_id=actor_id, now=now) for source in self._sources)
        )
        return [record for group in values for record in group]


class SqlAlchemyDashboardDataSource:
    MAX_RECORDS = 500

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load(self, *, actor_id: str, now: datetime) -> list[DashboardSourceRecord]:
        horizon = now + timedelta(days=7)
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        async with self._session_factory() as session:
            work_item_rows = (
                await session.execute(
                    select(WorkItemModel, LegalMatterModel)
                    .join(LegalMatterModel, LegalMatterModel.id == WorkItemModel.matter_id)
                    .where(
                        WorkItemModel.owner_id == actor_id,
                        WorkItemModel.status.not_in(
                            [WorkItemStatus.DONE, WorkItemStatus.CANCELLED]
                        ),
                    )
                    .order_by(WorkItemModel.created_at, WorkItemModel.id)
                    .limit(self.MAX_RECORDS)
                )
            ).all()
            matter_rows = (
                (
                    await session.execute(
                        select(LegalMatterModel)
                        .where(
                            LegalMatterModel.owner_id == actor_id,
                            LegalMatterModel.lifecycle_status.not_in(
                                [
                                    MatterLifecycleStatus.CLOSED,
                                    MatterLifecycleStatus.CANCELLED,
                                ]
                            ),
                        )
                        .order_by(LegalMatterModel.created_at, LegalMatterModel.id)
                        .limit(self.MAX_RECORDS)
                    )
                )
                .scalars()
                .all()
            )
            work_item_ids = [item.id for item, _matter in work_item_rows]
            matter_ids = list(
                {matter.id for _item, matter in work_item_rows}
                | {matter.id for matter in matter_rows}
            )
            deadline_rows: Sequence[DeadlineModel] = ()
            if work_item_ids or matter_ids:
                deadline_rows = (
                    (
                        await session.execute(
                            select(DeadlineModel)
                            .where(
                                DeadlineModel.status == DeadlineStatus.ACTIVE,
                                DeadlineModel.due_at <= horizon,
                                or_(
                                    DeadlineModel.work_item_id.in_(work_item_ids),
                                    DeadlineModel.matter_id.in_(matter_ids),
                                ),
                            )
                            .order_by(DeadlineModel.due_at, DeadlineModel.id)
                            .limit(self.MAX_RECORDS * 4)
                        )
                    )
                    .scalars()
                    .all()
                )
            candidate_rows = (
                (
                    await session.execute(
                        select(MessageCandidateModel)
                        .where(MessageCandidateModel.status == CandidateStatus.PENDING_CONFIRMATION)
                        .order_by(MessageCandidateModel.created_at, MessageCandidateModel.id)
                        .limit(self.MAX_RECORDS)
                    )
                )
                .scalars()
                .all()
            )
            failed_run_rows = (
                (
                    await session.execute(
                        select(AgentRunModel)
                        .outerjoin(
                            FeishuMessageModel,
                            FeishuMessageModel.id == AgentRunModel.feishu_message_id,
                        )
                        .where(
                            AgentRunModel.status.in_(
                                [
                                    AgentRunStatus.FAILED,
                                    AgentRunStatus.TIMED_OUT,
                                    AgentRunStatus.DEAD_LETTER,
                                ]
                            ),
                            or_(
                                AgentRunModel.feishu_message_id.is_(None),
                                FeishuMessageModel.last_agent_run_id == AgentRunModel.id,
                            ),
                        )
                        .order_by(AgentRunModel.created_at, AgentRunModel.id)
                        .limit(self.MAX_RECORDS)
                    )
                )
                .scalars()
                .all()
            )
            failed_message_rows = (
                (
                    await session.execute(
                        select(FeishuMessageModel)
                        .where(
                            FeishuMessageModel.status.in_(
                                [
                                    FeishuMessageStatus.ANALYSIS_FAILED,
                                    FeishuMessageStatus.DEAD_LETTER,
                                ]
                            ),
                            FeishuMessageModel.last_agent_run_id.is_(None),
                        )
                        .order_by(FeishuMessageModel.created_at, FeishuMessageModel.id)
                        .limit(self.MAX_RECORDS)
                    )
                )
                .scalars()
                .all()
            )
            review_rows = (
                await session.execute(
                    select(ReviewPackageModel, LegalMatterModel)
                    .join(LegalMatterModel, LegalMatterModel.id == ReviewPackageModel.matter_id)
                    .where(
                        ReviewPackageModel.status == ReviewPackageStatus.PENDING_REVIEW,
                        ReviewPackageModel.package_type == ReviewPackageType.EXTERNAL_MESSAGE,
                    )
                    .order_by(ReviewPackageModel.created_at, ReviewPackageModel.id)
                    .limit(self.MAX_RECORDS)
                )
            ).all()
            dead_letter_rows = (
                (
                    await session.execute(
                        select(OutboxDeadLetterModel)
                        .where(OutboxDeadLetterModel.requeued_at.is_(None))
                        .order_by(OutboxDeadLetterModel.failed_at, OutboxDeadLetterModel.id)
                        .limit(self.MAX_RECORDS)
                    )
                )
                .scalars()
                .all()
            )
            connection_rows = (
                (
                    await session.execute(
                        select(IntegrationConnectionModel)
                        .where(
                            IntegrationConnectionModel.status.in_(
                                [
                                    IntegrationConnectionStatus.DEGRADED,
                                    IntegrationConnectionStatus.DISCONNECTED,
                                    IntegrationConnectionStatus.FAILED,
                                ]
                            )
                        )
                        .order_by(
                            IntegrationConnectionModel.updated_at,
                            IntegrationConnectionModel.id,
                        )
                    )
                )
                .scalars()
                .all()
            )

        work_deadlines: dict[object, list[DeadlineModel]] = {}
        matter_deadlines: dict[object, list[DeadlineModel]] = {}
        for deadline in deadline_rows:
            if deadline.work_item_id is not None:
                work_deadlines.setdefault(deadline.work_item_id, []).append(deadline)
            elif deadline.matter_id is not None:
                matter_deadlines.setdefault(deadline.matter_id, []).append(deadline)

        records: list[DashboardSourceRecord] = []
        active_matter_ids: set[object] = set()
        for item, matter in work_item_rows:
            active_matter_ids.add(matter.id)
            candidates: list[tuple[datetime, bool]] = [
                (value.due_at, value.is_hard)
                for value in (
                    work_deadlines.get(item.id, []) + matter_deadlines.get(matter.id, [])
                )
            ]
            if item.planned_complete_at is not None:
                candidates.append((item.planned_complete_at, False))
            elif matter.target_deadline_at is not None:
                candidates.append((matter.target_deadline_at, False))
            due_at, is_hard = min(candidates, default=(None, False), key=lambda value: value[0])
            confirmed_priority = (
                item.priority if item.priority_source == PrioritySource.LEGAL_CONFIRMED else None
            )
            base = DashboardSourceRecord(
                id=item.id,
                group=DashboardGroup.TODAY_MUST_HANDLE,
                object_type="work_item",
                title=item.title,
                description=item.next_action,
                href=f"/matters/{matter.id}",
                status=item.status.value,
                created_at=item.created_at,
                due_at=due_at,
                is_hard_deadline=is_hard,
                legal_risk=matter.legal_risk,
                confirmed_priority=confirmed_priority,
                ai_suggested_priority=item.ai_suggested_priority,
                waiting_since=item.waiting_since,
                reason="负责人名下的开放 WorkItem",
            )
            records.extend(
                self._work_groups(
                    base,
                    now=now,
                    tomorrow=tomorrow,
                    horizon=horizon,
                    is_waiting=item.status == WorkItemStatus.WAITING,
                )
            )

        for matter in matter_rows:
            if matter.id in active_matter_ids:
                continue
            deadline_values = matter_deadlines.get(matter.id, [])
            candidates = [(value.due_at, value.is_hard) for value in deadline_values]
            if matter.target_deadline_at is not None:
                candidates.append((matter.target_deadline_at, False))
            due_at, is_hard = min(candidates, default=(None, False), key=lambda value: value[0])
            confirmed_priority = (
                matter.priority
                if matter.priority_source == PrioritySource.LEGAL_CONFIRMED
                else None
            )
            base = DashboardSourceRecord(
                id=matter.id,
                group=DashboardGroup.TODAY_MUST_HANDLE,
                object_type="matter",
                title=matter.title,
                description=matter.next_action or "尚未建立开放 WorkItem",
                href=f"/matters/{matter.id}",
                status=matter.work_status.value,
                created_at=matter.created_at,
                due_at=due_at,
                is_hard_deadline=is_hard,
                legal_risk=matter.legal_risk,
                confirmed_priority=confirmed_priority,
                reason="负责人名下且没有开放 WorkItem 的 Matter",
            )
            records.extend(
                self._work_groups(
                    base,
                    now=now,
                    tomorrow=tomorrow,
                    horizon=horizon,
                    is_waiting=False,
                )
            )

        records.extend(self._candidate_records(candidate_rows))
        records.extend(self._failed_run_records(failed_run_rows))
        records.extend(self._failed_message_records(failed_message_rows))
        records.extend(self._review_records([(package, matter) for package, matter in review_rows]))
        records.extend(self._dead_letter_records(dead_letter_rows))
        records.extend(self._connection_records(connection_rows))
        return records

    @staticmethod
    def _work_groups(
        base: DashboardSourceRecord,
        *,
        now: datetime,
        tomorrow: datetime,
        horizon: datetime,
        is_waiting: bool,
    ) -> list[DashboardSourceRecord]:
        records: list[DashboardSourceRecord] = []
        due_at = base.due_at
        if (
            (due_at is not None and due_at < tomorrow)
            or (base.is_hard_deadline and due_at is not None and due_at <= horizon)
            or base.confirmed_priority == Priority.URGENT
            or base.legal_risk == LegalRisk.CRITICAL
        ):
            records.append(replace(base, group=DashboardGroup.TODAY_MUST_HANDLE))
        if due_at is not None and due_at < now:
            records.append(
                replace(
                    base,
                    group=DashboardGroup.OVERDUE,
                    reason="开放工作已经超过有效期限",
                )
            )
        if is_waiting:
            records.append(
                replace(
                    base,
                    group=DashboardGroup.WAITING_OTHERS,
                    reason="WorkItem 正在等待外部依赖",
                )
            )
        if due_at is not None and now <= due_at <= horizon:
            records.append(
                replace(
                    base,
                    group=DashboardGroup.UPCOMING_DEADLINES,
                    reason="有效期限将在七天内到达",
                )
            )
        return records

    @staticmethod
    def _candidate_records(
        values: Sequence[MessageCandidateModel],
    ) -> list[DashboardSourceRecord]:
        records: list[DashboardSourceRecord] = []
        for value in values:
            href = (
                f"/inbox/{value.feishu_message_id}"
                if value.feishu_message_id
                else f"/candidates/{value.id}"
            )
            records.append(
                DashboardSourceRecord(
                    id=value.id,
                    group=DashboardGroup.PENDING_CANDIDATES,
                    object_type="candidate",
                    title=value.title_proposal or "待确认消息 Candidate",
                    description=f"建议动作: {value.recommended_action.value}",
                    href=href,
                    status=value.status.value,
                    created_at=value.created_at,
                    legal_risk=LegalRisk.PENDING,
                    ai_suggested_priority=_candidate_ai_priority(value.analysis_payload),
                    reason="Candidate 等待法务人工确认",
                )
            )
        return records

    @staticmethod
    def _failed_run_records(values: Sequence[AgentRunModel]) -> list[DashboardSourceRecord]:
        return [
            DashboardSourceRecord(
                id=value.id,
                group=DashboardGroup.ANALYSIS_FAILED,
                object_type="agent_run",
                title=f"AgentRun {value.id}",
                description=value.failure_message or value.failure_code or "分析运行失败",
                href=f"/agent-runs/{value.id}",
                status=value.status.value,
                created_at=value.created_at,
                reason="最新 AgentRun 未成功完成",
            )
            for value in values
        ]

    @staticmethod
    def _failed_message_records(
        values: Sequence[FeishuMessageModel],
    ) -> list[DashboardSourceRecord]:
        return [
            DashboardSourceRecord(
                id=value.id,
                group=DashboardGroup.ANALYSIS_FAILED,
                object_type="feishu_message",
                title=(value.plain_text or "消息分析失败")[:160],
                description=value.failure_message or value.failure_code or "分析未能启动",
                href=f"/inbox/{value.id}",
                status=value.status.value,
                created_at=value.created_at,
                reason="消息没有可用的 AgentRun 结果",
            )
            for value in values
        ]

    @staticmethod
    def _review_records(
        values: Sequence[tuple[ReviewPackageModel, LegalMatterModel]],
    ) -> list[DashboardSourceRecord]:
        return [
            DashboardSourceRecord(
                id=package.id,
                group=DashboardGroup.PENDING_OUTBOUND_REVIEW,
                object_type="review_package",
                title=package.title,
                description=package.background,
                href=f"/reviews?packageId={package.id}",
                status=package.status.value,
                created_at=package.created_at,
                legal_risk=matter.legal_risk,
                confirmed_priority=(
                    matter.priority
                    if matter.priority_source == PrioritySource.LEGAL_CONFIRMED
                    else None
                ),
                reason="外发内容等待法务审核",
            )
            for package, matter in values
        ]

    @staticmethod
    def _dead_letter_records(
        values: Sequence[OutboxDeadLetterModel],
    ) -> list[DashboardSourceRecord]:
        return [
            DashboardSourceRecord(
                id=value.id,
                group=DashboardGroup.SYSTEM_ABNORMAL,
                object_type="outbox_dead_letter",
                title=f"Outbox 死信: {value.event_type}",
                description=value.last_error,
                href="/system",
                status="dead_letter",
                created_at=value.failed_at,
                reason="Outbox 事件等待人工恢复",
            )
            for value in values
        ]

    @staticmethod
    def _connection_records(
        values: Sequence[IntegrationConnectionModel],
    ) -> list[DashboardSourceRecord]:
        return [
            DashboardSourceRecord(
                id=value.id,
                group=DashboardGroup.SYSTEM_ABNORMAL,
                object_type="integration_connection",
                title=f"{value.integration_type} 集成异常",
                description=value.last_error_message or value.status.value,
                href="/system",
                status=value.status.value,
                created_at=value.updated_at,
                reason="持久化集成连接状态异常",
            )
            for value in values
        ]


class OperationalHealthDashboardDataSource:
    async def load(self, *, actor_id: str, now: datetime) -> list[DashboardSourceRecord]:
        del actor_id
        try:
            snapshot = await SystemStatusService().snapshot()
        except Exception:
            # The business queue must remain usable when a secondary health probe
            # fails. Do not expose the exception because it may contain a DSN or
            # other runtime details.
            return [
                DashboardSourceRecord(
                    id="component:health-probe",
                    group=DashboardGroup.SYSTEM_ABNORMAL,
                    object_type="system_component",
                    title="系统健康检查执行失败",
                    description="无法生成完整健康快照; 请进入系统状态页重试。",
                    href="/system",
                    status="unavailable",
                    created_at=now,
                    reason="实时系统健康检查未完成",
                )
            ]
        return [
            DashboardSourceRecord(
                id=f"component:{key}",
                group=DashboardGroup.SYSTEM_ABNORMAL,
                object_type="system_component",
                title=f"系统组件异常: {key}",
                description=component.detail,
                href="/system",
                status=component.status,
                created_at=component.updated_at,
                reason="实时系统健康检查未通过",
            )
            for key, component in snapshot.components.items()
            if component.status in {"degraded", "unavailable"}
        ]


def _candidate_ai_priority(payload: dict[str, object]) -> Priority | None:
    for key in ("aiSuggestedPriority", "suggestedPriority", "priority"):
        value = payload.get(key)
        if isinstance(value, str):
            try:
                return Priority(value)
            except ValueError:
                continue
    return None
