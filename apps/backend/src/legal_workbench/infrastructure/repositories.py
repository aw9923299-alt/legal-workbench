from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_workbench.domain.entities import (
    AuditEvent,
    Communication,
    ContextSnapshot,
    Deadline,
    FeishuMessage,
    FeishuRawEvent,
    IdempotencyRecord,
    LegalMatter,
    MessageCandidate,
    OutboxEvent,
    PriorityConfirmation,
    ReviewPackage,
    ReviewRecord,
    WorkItem,
    WorkItemDependency,
)
from legal_workbench.domain.enums import (
    CandidateMatterRelation,
    CandidateStatus,
    CommunicationStatus,
    DeadlineStatus,
    MatterCategory,
    ReviewDecision,
    ReviewPackageStatus,
)
from legal_workbench.infrastructure.models import (
    AuditEventModel,
    CandidateMatterLinkModel,
    CommunicationModel,
    ContextSnapshotModel,
    DeadlineModel,
    FeishuEventModel,
    FeishuMessageModel,
    IdempotencyRecordModel,
    LegalMatterModel,
    MessageCandidateModel,
    OutboxEventModel,
    PriorityConfirmationModel,
    ReviewPackageModel,
    ReviewRecordModel,
    WorkItemDependencyModel,
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
        statement = (
            select(MessageCandidateModel)
            .where(MessageCandidateModel.id == candidate_id)
            .with_for_update()
        )
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
        statement = (
            select(LegalMatterModel)
            .where(LegalMatterModel.id == matter_id)
            .with_for_update()
        )
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
        self._tracked: dict[UUID, WorkItemModel] = {}

    async def add(self, work_item: WorkItem) -> None:
        model = self._to_model(work_item)
        self._tracked[work_item.id] = model
        self._session.add(model)

    async def add_many(self, work_items: Sequence[WorkItem]) -> None:
        models = [self._to_model(item) for item in work_items]
        self._tracked.update({model.id: model for model in models})
        self._session.add_all(models)

    async def get(self, work_item_id: UUID) -> WorkItem | None:
        model = await self._session.get(WorkItemModel, work_item_id)
        if model is None:
            return None
        self._tracked[work_item_id] = model
        return self._to_domain(model)

    async def get_for_update(self, work_item_id: UUID) -> WorkItem | None:
        statement = (
            select(WorkItemModel)
            .where(WorkItemModel.id == work_item_id)
            .with_for_update()
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked[work_item_id] = model
        return self._to_domain(model)

    async def save(self, work_item: WorkItem) -> None:
        model = self._tracked.get(work_item.id)
        if model is None:
            model = await self._session.get(WorkItemModel, work_item.id)
        if model is None:
            raise RuntimeError(f"Work item {work_item.id} is not tracked")
        model.priority = work_item.priority
        model.priority_source = work_item.priority_source
        model.priority_reasons = work_item.priority_reasons
        model.override_reason = work_item.override_reason
        model.planned_complete_at = work_item.planned_complete_at
        model.priority_confirmed_by = work_item.priority_confirmed_by
        model.priority_confirmed_at = work_item.priority_confirmed_at

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
            priority_confirmed_by=work_item.priority_confirmed_by,
            priority_confirmed_at=work_item.priority_confirmed_at,
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
            priority_confirmed_by=model.priority_confirmed_by,
            priority_confirmed_at=model.priority_confirmed_at,
            sequence_order=model.sequence_order,
            version=model.version,
        )


class SqlAlchemyPriorityConfirmationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, confirmation: PriorityConfirmation) -> None:
        self._session.add(
            PriorityConfirmationModel(
                id=confirmation.id,
                work_item_id=confirmation.work_item_id,
                proposed_priority=confirmation.proposed_priority,
                confirmed_priority=confirmation.confirmed_priority,
                proposed_complete_at=confirmation.proposed_complete_at,
                confirmed_complete_at=confirmation.confirmed_complete_at,
                reasons=confirmation.reasons,
                override_reason=confirmation.override_reason,
                confirmed_by=confirmation.confirmed_by,
                confirmed_at=confirmation.confirmed_at,
                status=confirmation.status,
                version=confirmation.version,
            )
        )

    async def list_by_work_item(self, work_item_id: UUID) -> Sequence[PriorityConfirmation]:
        statement = (
            select(PriorityConfirmationModel)
            .where(PriorityConfirmationModel.work_item_id == work_item_id)
            .order_by(PriorityConfirmationModel.confirmed_at.desc())
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [
            PriorityConfirmation(
                id=model.id,
                work_item_id=model.work_item_id,
                proposed_priority=model.proposed_priority,
                confirmed_priority=model.confirmed_priority,
                proposed_complete_at=model.proposed_complete_at,
                confirmed_complete_at=model.confirmed_complete_at,
                reasons=model.reasons,
                override_reason=model.override_reason,
                confirmed_by=model.confirmed_by,
                confirmed_at=model.confirmed_at,
                status=model.status,
                version=model.version,
            )
            for model in models
        ]


class SqlAlchemyDeadlineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, deadline: Deadline) -> None:
        self._session.add(
            DeadlineModel(
                id=deadline.id,
                matter_id=deadline.matter_id,
                work_item_id=deadline.work_item_id,
                deadline_type=deadline.deadline_type,
                source=deadline.source,
                due_at=deadline.due_at,
                timezone=deadline.timezone,
                is_hard=deadline.is_hard,
                status=deadline.status,
                source_reference=deadline.source_reference,
                confidence=deadline.confidence,
                reminder_policy=deadline.reminder_policy,
                confirmed_by=deadline.confirmed_by,
                confirmed_at=deadline.confirmed_at,
                completed_at=deadline.completed_at,
                version=deadline.version,
            )
        )

    async def list_by_work_item(
        self, work_item_id: UUID, *, status: DeadlineStatus | None = None
    ) -> Sequence[Deadline]:
        statement = select(DeadlineModel).where(DeadlineModel.work_item_id == work_item_id)
        if status is not None:
            statement = statement.where(DeadlineModel.status == status)
        statement = statement.order_by(DeadlineModel.due_at)
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    async def list_by_matter(
        self, matter_id: UUID, *, status: DeadlineStatus | None = None
    ) -> Sequence[Deadline]:
        statement = select(DeadlineModel).where(DeadlineModel.matter_id == matter_id)
        if status is not None:
            statement = statement.where(DeadlineModel.status == status)
        statement = statement.order_by(DeadlineModel.due_at)
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_domain(model: DeadlineModel) -> Deadline:
        return Deadline(
            id=model.id,
            matter_id=model.matter_id,
            work_item_id=model.work_item_id,
            deadline_type=model.deadline_type,
            source=model.source,
            due_at=model.due_at,
            timezone=model.timezone,
            is_hard=model.is_hard,
            status=model.status,
            source_reference=model.source_reference,
            confidence=model.confidence,
            reminder_policy=model.reminder_policy,
            confirmed_by=model.confirmed_by,
            confirmed_at=model.confirmed_at,
            completed_at=model.completed_at,
            version=model.version,
        )


class SqlAlchemyDependencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, dependency: WorkItemDependency) -> None:
        self._session.add(
            WorkItemDependencyModel(
                id=dependency.id,
                work_item_id=dependency.work_item_id,
                depends_on_work_item_id=dependency.depends_on_work_item_id,
                dependency_type=dependency.dependency_type,
                status=dependency.status,
                external_party_id=dependency.external_party_id,
                description=dependency.description,
                satisfied_at=dependency.satisfied_at,
                waived_by=dependency.waived_by,
                waived_at=dependency.waived_at,
                version=dependency.version,
            )
        )

    async def list_by_work_item(self, work_item_id: UUID) -> Sequence[WorkItemDependency]:
        statement = (
            select(WorkItemDependencyModel)
            .where(WorkItemDependencyModel.work_item_id == work_item_id)
            .order_by(WorkItemDependencyModel.created_at)
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [
            WorkItemDependency(
                id=model.id,
                work_item_id=model.work_item_id,
                depends_on_work_item_id=model.depends_on_work_item_id,
                dependency_type=model.dependency_type,
                status=model.status,
                external_party_id=model.external_party_id,
                description=model.description,
                satisfied_at=model.satisfied_at,
                waived_by=model.waived_by,
                waived_at=model.waived_at,
                version=model.version,
            )
            for model in models
        ]


class SqlAlchemyReviewPackageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tracked: dict[UUID, ReviewPackageModel] = {}

    async def add(self, package: ReviewPackage) -> None:
        model = self._to_model(package)
        self._tracked[package.id] = model
        self._session.add(model)

    async def get(self, package_id: UUID) -> ReviewPackage | None:
        model = await self._session.get(ReviewPackageModel, package_id)
        if model is None:
            return None
        self._tracked[package_id] = model
        return self._to_domain(model)

    async def get_for_update(self, package_id: UUID) -> ReviewPackage | None:
        statement = (
            select(ReviewPackageModel)
            .where(ReviewPackageModel.id == package_id)
            .with_for_update()
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked[package_id] = model
        return self._to_domain(model)

    async def save(self, package: ReviewPackage) -> None:
        model = self._tracked.get(package.id)
        if model is None:
            model = await self._session.get(ReviewPackageModel, package.id)
        if model is None:
            raise RuntimeError(f"Review package {package.id} is not tracked")
        model.status = package.status
        model.submitted_at = package.submitted_at
        model.approved_content_hash = package.approved_content_hash

    async def list(
        self, *, status: ReviewPackageStatus | None, matter_id: UUID | None, limit: int
    ) -> Sequence[ReviewPackage]:
        statement = select(ReviewPackageModel)
        if status is not None:
            statement = statement.where(ReviewPackageModel.status == status)
        if matter_id is not None:
            statement = statement.where(ReviewPackageModel.matter_id == matter_id)
        statement = statement.order_by(ReviewPackageModel.created_at.desc()).limit(limit)
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_model(package: ReviewPackage) -> ReviewPackageModel:
        return ReviewPackageModel(
            id=package.id,
            matter_id=package.matter_id,
            work_item_id=package.work_item_id,
            package_type=package.package_type,
            status=package.status,
            title=package.title,
            background=package.background,
            confirmed_facts=package.confirmed_facts,
            unconfirmed_facts=package.unconfirmed_facts,
            reasoning=package.reasoning,
            risks=package.risks,
            alternatives=package.alternatives,
            citations=package.citations,
            proposed_content=package.proposed_content,
            target=package.target,
            created_by=package.created_by,
            submitted_at=package.submitted_at,
            approved_content_hash=package.approved_content_hash,
            version=package.version,
        )

    @staticmethod
    def _to_domain(model: ReviewPackageModel) -> ReviewPackage:
        return ReviewPackage(
            id=model.id,
            matter_id=model.matter_id,
            work_item_id=model.work_item_id,
            package_type=model.package_type,
            status=model.status,
            title=model.title,
            background=model.background,
            confirmed_facts=model.confirmed_facts,
            unconfirmed_facts=model.unconfirmed_facts,
            reasoning=model.reasoning,
            risks=model.risks,
            alternatives=model.alternatives,
            citations=model.citations,
            proposed_content=model.proposed_content,
            target=model.target,
            created_by=model.created_by,
            submitted_at=model.submitted_at,
            approved_content_hash=model.approved_content_hash,
            version=model.version,
        )


class SqlAlchemyReviewRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: ReviewRecord) -> None:
        self._session.add(
            ReviewRecordModel(
                id=record.id,
                review_package_id=record.review_package_id,
                reviewer_id=record.reviewer_id,
                decision=record.decision,
                comments=record.comments,
                final_content=record.final_content,
                final_content_hash=record.final_content_hash,
                change_summary=record.change_summary,
                reusable_as_example=record.reusable_as_example,
                reviewed_at=record.reviewed_at,
            )
        )

    async def get(self, record_id: UUID) -> ReviewRecord | None:
        model = await self._session.get(ReviewRecordModel, record_id)
        return None if model is None else self._to_domain(model)

    async def get_latest_approved(self, package_id: UUID) -> ReviewRecord | None:
        statement = (
            select(ReviewRecordModel)
            .where(
                ReviewRecordModel.review_package_id == package_id,
                ReviewRecordModel.decision.in_(
                    [ReviewDecision.APPROVED, ReviewDecision.APPROVED_WITH_EDITS]
                ),
            )
            .order_by(ReviewRecordModel.reviewed_at.desc())
            .limit(1)
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._to_domain(model)

    async def list_by_package(self, package_id: UUID) -> Sequence[ReviewRecord]:
        statement = (
            select(ReviewRecordModel)
            .where(ReviewRecordModel.review_package_id == package_id)
            .order_by(ReviewRecordModel.reviewed_at.desc())
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_domain(model: ReviewRecordModel) -> ReviewRecord:
        return ReviewRecord(
            id=model.id,
            review_package_id=model.review_package_id,
            reviewer_id=model.reviewer_id,
            decision=model.decision,
            comments=model.comments,
            final_content=model.final_content,
            final_content_hash=model.final_content_hash,
            change_summary=model.change_summary,
            reusable_as_example=model.reusable_as_example,
            reviewed_at=model.reviewed_at,
        )


class SqlAlchemyCommunicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tracked: dict[UUID, CommunicationModel] = {}

    async def add(self, communication: Communication) -> None:
        model = CommunicationModel(
            id=communication.id,
            matter_id=communication.matter_id,
            work_item_id=communication.work_item_id,
            review_package_id=communication.review_package_id,
            review_record_id=communication.review_record_id,
            channel=communication.channel,
            target=communication.target,
            content=communication.content,
            content_hash=communication.content_hash,
            status=communication.status,
            requested_by=communication.requested_by,
            correlation_id=communication.correlation_id,
            external_message_id=communication.external_message_id,
            attempts=communication.attempts,
            last_error=communication.last_error,
            queued_at=communication.queued_at,
            sent_at=communication.sent_at,
            version=communication.version,
        )
        self._tracked[communication.id] = model
        self._session.add(model)

    async def get(self, communication_id: UUID) -> Communication | None:
        model = await self._session.get(CommunicationModel, communication_id)
        if model is None:
            return None
        self._tracked[communication_id] = model
        return self._to_domain(model)

    async def get_for_update(self, communication_id: UUID) -> Communication | None:
        statement = (
            select(CommunicationModel)
            .where(CommunicationModel.id == communication_id)
            .with_for_update()
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked[communication_id] = model
        return self._to_domain(model)

    async def get_by_review_record(
        self, review_record_id: UUID
    ) -> Communication | None:
        statement = select(CommunicationModel).where(
            CommunicationModel.review_record_id == review_record_id
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._to_domain(model)

    async def list(
        self, *, status: CommunicationStatus | None, limit: int
    ) -> Sequence[Communication]:
        statement = select(CommunicationModel)
        if status is not None:
            statement = statement.where(CommunicationModel.status == status)
        statement = statement.order_by(CommunicationModel.created_at.desc()).limit(limit)
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_domain(model: CommunicationModel) -> Communication:
        return Communication(
            id=model.id,
            matter_id=model.matter_id,
            work_item_id=model.work_item_id,
            review_package_id=model.review_package_id,
            review_record_id=model.review_record_id,
            channel=model.channel,
            target=model.target,
            content=model.content,
            content_hash=model.content_hash,
            status=model.status,
            requested_by=model.requested_by,
            correlation_id=model.correlation_id,
            external_message_id=model.external_message_id,
            attempts=model.attempts,
            last_error=model.last_error,
            queued_at=model.queued_at,
            sent_at=model.sent_at,
            version=model.version,
        )


class SqlAlchemyFeishuRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_event_by_external_id(self, event_id: str) -> FeishuRawEvent | None:
        statement = select(FeishuEventModel).where(FeishuEventModel.event_id == event_id)
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._event_to_domain(model)

    async def add_event(self, event: FeishuRawEvent) -> None:
        self._session.add(
            FeishuEventModel(
                id=event.id,
                event_id=event.event_id,
                event_type=event.event_type,
                tenant_key=event.tenant_key,
                app_id=event.app_id,
                schema_version=event.schema_version,
                raw_payload=event.raw_payload,
                payload_hash=event.payload_hash,
                status=event.status,
                received_at=event.received_at,
                processed_at=event.processed_at,
                last_error=event.last_error,
            )
        )

    async def get_message(self, *, tenant_key: str | None, message_id: str) -> FeishuMessage | None:
        statement = select(FeishuMessageModel).where(
            FeishuMessageModel.tenant_key.is_(None)
            if tenant_key is None
            else FeishuMessageModel.tenant_key == tenant_key,
            FeishuMessageModel.message_id == message_id,
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._message_to_domain(model)

    async def add_message(self, message: FeishuMessage) -> None:
        self._session.add(
            FeishuMessageModel(
                id=message.id,
                event_id=message.event_id,
                tenant_key=message.tenant_key,
                message_id=message.message_id,
                chat_id=message.chat_id,
                thread_id=message.thread_id,
                root_id=message.root_id,
                parent_id=message.parent_id,
                sender_id=message.sender_id,
                sender_type=message.sender_type,
                message_type=message.message_type,
                content=message.content,
                mentions=message.mentions,
                create_time=message.create_time,
                update_time=message.update_time,
                raw_message=message.raw_message,
                status=message.status,
            )
        )

    @staticmethod
    def _event_to_domain(model: FeishuEventModel) -> FeishuRawEvent:
        return FeishuRawEvent(
            id=model.id,
            event_id=model.event_id,
            event_type=model.event_type,
            tenant_key=model.tenant_key,
            app_id=model.app_id,
            schema_version=model.schema_version,
            raw_payload=model.raw_payload,
            payload_hash=model.payload_hash,
            status=model.status,
            received_at=model.received_at,
            processed_at=model.processed_at,
            last_error=model.last_error,
        )

    @staticmethod
    def _message_to_domain(model: FeishuMessageModel) -> FeishuMessage:
        return FeishuMessage(
            id=model.id,
            event_id=model.event_id,
            tenant_key=model.tenant_key,
            message_id=model.message_id,
            chat_id=model.chat_id,
            thread_id=model.thread_id,
            root_id=model.root_id,
            parent_id=model.parent_id,
            sender_id=model.sender_id,
            sender_type=model.sender_type,
            message_type=model.message_type,
            content=model.content,
            mentions=model.mentions,
            create_time=model.create_time,
            update_time=model.update_time,
            raw_message=model.raw_message,
            status=model.status,
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
