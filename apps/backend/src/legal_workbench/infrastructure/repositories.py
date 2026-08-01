from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_workbench.domain.entities import (
    AuditEvent,
    ContextSnapshot,
    IdempotencyRecord,
    LegalMatter,
    MessageCandidate,
    OutboxEvent,
    WorkItem,
)
from legal_workbench.domain.enums import CandidateMatterRelation, CandidateStatus, MatterCategory
from legal_workbench.infrastructure.models import (
    AuditEventModel,
    CandidateMatterLinkModel,
    ContextSnapshotModel,
    IdempotencyRecordModel,
    LegalMatterModel,
    MessageCandidateModel,
    OutboxEventModel,
    WorkItemModel,
)


class SqlAlchemyContextSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, snapshot: ContextSnapshot) -> None:
        self._session.add(
            ContextSnapshotModel(
                id=snapshot.id,
                source_type=snapshot.source_type,
                source_ids=snapshot.source_ids,
                message_ids=snapshot.message_ids,
                file_ids=snapshot.file_ids,
                relevant_matter_ids=snapshot.relevant_matter_ids,
                participant_ids=snapshot.participant_ids,
                permission_snapshot=snapshot.permission_snapshot,
                generated_at=snapshot.generated_at,
                content_hash=snapshot.content_hash,
            )
        )


class SqlAlchemyMessageCandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tracked: dict[UUID, MessageCandidateModel] = {}

    async def add(self, candidate: MessageCandidate) -> None:
        model = MessageCandidateModel(
            id=candidate.id,
            context_snapshot_id=candidate.context_snapshot_id,
            status=candidate.status,
            legal_relevance=candidate.legal_relevance,
            message_role=candidate.message_role,
            recommended_action=candidate.recommended_action,
            title_proposal=candidate.title_proposal,
            category_proposals=candidate.category_proposals,
            deadline_proposals=candidate.deadline_proposals,
            related_matter_proposals=candidate.related_matter_proposals,
            evidence_refs=candidate.evidence_refs,
            confidence=candidate.confidence,
            agent_run_id=candidate.agent_run_id,
            confirmed_by=candidate.confirmed_by,
            confirmed_at=candidate.confirmed_at,
            version=candidate.version,
        )
        self._tracked[candidate.id] = model
        self._session.add(model)

    async def get(self, candidate_id: UUID) -> MessageCandidate | None:
        model = await self._session.get(MessageCandidateModel, candidate_id)
        if model is None:
            return None
        self._tracked[candidate_id] = model
        return self._to_domain(model)

    async def get_for_update(self, candidate_id: UUID) -> MessageCandidate | None:
        statement = select(MessageCandidateModel).where(
            MessageCandidateModel.id == candidate_id
        ).with_for_update()
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked[candidate_id] = model
        return self._to_domain(model)

    async def save(self, candidate: MessageCandidate) -> None:
        model = self._tracked.get(candidate.id)
        if model is None:
            model = await self._session.get(MessageCandidateModel, candidate.id)
        if model is None:
            raise RuntimeError(f"Candidate {candidate.id} is not tracked")
        model.status = candidate.status
        model.confirmed_by = candidate.confirmed_by
        model.confirmed_at = candidate.confirmed_at

    async def list(
        self, *, status: CandidateStatus | None, limit: int
    ) -> Sequence[MessageCandidate]:
        statement: Select[tuple[MessageCandidateModel]] = select(MessageCandidateModel)
        if status is not None:
            statement = statement.where(MessageCandidateModel.status == status)
        statement = statement.order_by(MessageCandidateModel.created_at.desc()).limit(limit)
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    async def link_to_matter(
        self,
        *,
        candidate_id: UUID,
        matter_id: UUID,
        relation_type: CandidateMatterRelation,
        confirmed_by: str,
    ) -> None:
        self._session.add(
            CandidateMatterLinkModel(
                candidate_id=candidate_id,
                matter_id=matter_id,
                relation_type=relation_type,
                confirmed_by=confirmed_by,
                confidence=Decimal("1.0000"),
            )
        )

    @staticmethod
    def _to_domain(model: MessageCandidateModel) -> MessageCandidate:
        return MessageCandidate(
            id=model.id,
            context_snapshot_id=model.context_snapshot_id,
            status=model.status,
            legal_relevance=model.legal_relevance,
            message_role=model.message_role,
            recommended_action=model.recommended_action,
            confidence=model.confidence,
            title_proposal=model.title_proposal,
            category_proposals=model.category_proposals,
            deadline_proposals=model.deadline_proposals,
            related_matter_proposals=model.related_matter_proposals,
            evidence_refs=model.evidence_refs,
            agent_run_id=model.agent_run_id,
            confirmed_by=model.confirmed_by,
            confirmed_at=model.confirmed_at,
            version=model.version,
        )


class SqlAlchemyLegalMatterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, matter: LegalMatter) -> None:
        self._session.add(
            LegalMatterModel(
                id=matter.id,
                matter_number=matter.matter_number,
                title=matter.title,
                primary_category=matter.primary_category,
                secondary_categories=[item.value for item in matter.secondary_categories],
                lifecycle_status=matter.lifecycle_status,
                work_status=matter.work_status,
                owner_id=matter.owner_id,
                collaborator_ids=matter.collaborator_ids,
                requester_ids=matter.requester_ids,
                entity_ids=matter.entity_ids,
                legal_risk=matter.legal_risk,
                business_impact=matter.business_impact,
                confidentiality=matter.confidentiality,
                summary=matter.summary,
                objective=matter.objective,
                current_stage=matter.current_stage,
                opened_at=matter.opened_at,
                resolved_at=matter.resolved_at,
                closed_at=matter.closed_at,
                reopened_at=matter.reopened_at,
                version=matter.version,
            )
        )

    async def get(self, matter_id: UUID) -> LegalMatter | None:
        model = await self._session.get(LegalMatterModel, matter_id)
        return None if model is None else self._to_domain(model)

    async def get_for_update(self, matter_id: UUID) -> LegalMatter | None:
        statement = select(LegalMatterModel).where(
            LegalMatterModel.id == matter_id
        ).with_for_update()
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._to_domain(model)

    async def list(self, *, owner_id: str | None, limit: int) -> Sequence[LegalMatter]:
        statement: Select[tuple[LegalMatterModel]] = select(LegalMatterModel)
        if owner_id is not None:
            statement = statement.where(LegalMatterModel.owner_id == owner_id)
        statement = statement.order_by(LegalMatterModel.opened_at.desc()).limit(limit)
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_domain(model: LegalMatterModel) -> LegalMatter:
        return LegalMatter(
            id=model.id,
            matter_number=model.matter_number,
            title=model.title,
            primary_category=model.primary_category,
            secondary_categories=[MatterCategory(item) for item in model.secondary_categories],
            lifecycle_status=model.lifecycle_status,
            work_status=model.work_status,
            owner_id=model.owner_id,
            collaborator_ids=model.collaborator_ids,
            requester_ids=model.requester_ids,
            entity_ids=model.entity_ids,
            legal_risk=model.legal_risk,
            business_impact=model.business_impact,
            confidentiality=model.confidentiality,
            summary=model.summary,
            objective=model.objective,
            current_stage=model.current_stage,
            version=model.version,
            opened_at=model.opened_at,
            resolved_at=model.resolved_at,
            closed_at=model.closed_at,
            reopened_at=model.reopened_at,
        )


class SqlAlchemyWorkItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, work_item: WorkItem) -> None:
        self._session.add(self._to_model(work_item))

    async def add_many(self, work_items: Sequence[WorkItem]) -> None:
        self._session.add_all([self._to_model(item) for item in work_items])

    async def get(self, work_item_id: UUID) -> WorkItem | None:
        model = await self._session.get(WorkItemModel, work_item_id)
        return None if model is None else self._to_domain(model)

    async def list_by_matter(self, matter_id: UUID) -> Sequence[WorkItem]:
        statement = (
            select(WorkItemModel)
            .where(WorkItemModel.matter_id == matter_id)
            .order_by(WorkItemModel.sequence_order, WorkItemModel.created_at)
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_model(work_item: WorkItem) -> WorkItemModel:
        return WorkItemModel(
            id=work_item.id,
            matter_id=work_item.matter_id,
            title=work_item.title,
            status=work_item.status,
            owner_id=work_item.owner_id,
            collaborator_ids=work_item.collaborator_ids,
            priority=work_item.priority,
            priority_source=work_item.priority_source,
            ai_suggested_priority=work_item.ai_suggested_priority,
            priority_reasons=work_item.priority_reasons,
            override_reason=work_item.override_reason,
            estimated_minutes=work_item.estimated_minutes,
            next_action=work_item.next_action,
            waiting_party_id=work_item.waiting_party_id,
            waiting_reason=work_item.waiting_reason,
            waiting_since=work_item.waiting_since,
            is_blocked=work_item.is_blocked,
            blocker_reason=work_item.blocker_reason,
            blocker_owner_id=work_item.blocker_owner_id,
            planned_start_at=work_item.planned_start_at,
            planned_complete_at=work_item.planned_complete_at,
            completed_at=work_item.completed_at,
            sequence_order=work_item.sequence_order,
            version=work_item.version,
        )

    @staticmethod
    def _to_domain(model: WorkItemModel) -> WorkItem:
        return WorkItem(
            id=model.id,
            matter_id=model.matter_id,
            title=model.title,
            status=model.status,
            owner_id=model.owner_id,
            collaborator_ids=model.collaborator_ids,
            priority=model.priority,
            priority_source=model.priority_source,
            ai_suggested_priority=model.ai_suggested_priority,
            priority_reasons=model.priority_reasons,
            override_reason=model.override_reason,
            estimated_minutes=model.estimated_minutes,
            next_action=model.next_action,
            waiting_party_id=model.waiting_party_id,
            waiting_reason=model.waiting_reason,
            waiting_since=model.waiting_since,
            is_blocked=model.is_blocked,
            blocker_reason=model.blocker_reason,
            blocker_owner_id=model.blocker_owner_id,
            planned_start_at=model.planned_start_at,
            planned_complete_at=model.planned_complete_at,
            completed_at=model.completed_at,
            sequence_order=model.sequence_order,
            version=model.version,
        )


class SqlAlchemyAuditEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: AuditEvent) -> None:
        self._session.add(
            AuditEventModel(
                id=event.id,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
                actor_id=event.actor_id,
                payload=event.payload,
                correlation_id=event.correlation_id,
                created_at=event.created_at,
            )
        )


class SqlAlchemyOutboxEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: OutboxEvent) -> None:
        self._session.add(
            OutboxEventModel(
                id=event.id,
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                payload=event.payload,
                correlation_id=event.correlation_id,
                occurred_at=event.occurred_at,
            )
        )


class SqlAlchemyIdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, operation: str, key: str) -> IdempotencyRecord | None:
        statement = select(IdempotencyRecordModel).where(
            IdempotencyRecordModel.operation == operation,
            IdempotencyRecordModel.idempotency_key == key,
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        return IdempotencyRecord(
            id=model.id,
            operation=model.operation,
            idempotency_key=model.idempotency_key,
            request_hash=model.request_hash,
            response_payload=model.response_payload,
            created_at=model.created_at,
            expires_at=model.expires_at,
        )

    async def add(self, record: IdempotencyRecord) -> None:
        self._session.add(
            IdempotencyRecordModel(
                id=record.id,
                operation=record.operation,
                idempotency_key=record.idempotency_key,
                request_hash=record.request_hash,
                response_payload=record.response_payload,
                created_at=record.created_at,
                expires_at=record.expires_at,
            )
        )
