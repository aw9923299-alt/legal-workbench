from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import Select, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from legal_workbench.domain.entities import (
    AgentAttemptLease,
    AgentDefinition,
    AgentRun,
    AgentRunAttempt,
    AgentRunSource,
    AgentRunStatusChange,
    AuditEvent,
    CandidateRevision,
    Communication,
    ContextSnapshot,
    Deadline,
    DocumentExtraction,
    DocumentSegment,
    DocumentVersion,
    DraftArtifact,
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
    FeishuAttachment,
    FeishuMessage,
    FeishuMessageVersion,
    FeishuRawEvent,
    IdempotencyRecord,
    IntegrationCheckRun,
    IntegrationConnection,
    IntegrationCredential,
    IntegrationScope,
    LegalMatter,
    MatterUpdateProposal,
    MessageCandidate,
    OutboxEvent,
    PriorityConfirmation,
    ReviewPackage,
    ReviewRecord,
    SystemSetting,
    WorkItem,
    WorkItemDependency,
)
from legal_workbench.domain.enums import (
    AgentAttemptStatus,
    AgentDefinitionStatus,
    AgentRunStatus,
    AttachmentDownloadStatus,
    CandidateMatterRelation,
    CandidateStatus,
    CommunicationStatus,
    DeadlineStatus,
    DocumentExtractionStatus,
    FeishuMessageStatus,
    MatterCategory,
    MatterUpdateProposalStatus,
    ReviewDecision,
    ReviewPackageStatus,
)
from legal_workbench.domain.errors import StaleAgentAttemptError
from legal_workbench.infrastructure.models import (
    AgentDefinitionModel,
    AgentRunAttemptModel,
    AgentRunModel,
    AgentRunSourceModel,
    AgentRunStatusEventModel,
    AuditEventModel,
    CandidateMatterLinkModel,
    CandidateRevisionModel,
    CommunicationModel,
    ContextSnapshotModel,
    DeadlineModel,
    DocumentExtractionModel,
    DocumentSegmentModel,
    DocumentVersionModel,
    DraftArtifactModel,
    EvaluationCaseModel,
    EvaluationResultModel,
    EvaluationRunModel,
    FeishuAttachmentModel,
    FeishuEventModel,
    FeishuMessageModel,
    FeishuMessageVersionModel,
    IdempotencyRecordModel,
    IntegrationCheckRunModel,
    IntegrationConnectionModel,
    IntegrationCredentialModel,
    IntegrationScopeModel,
    LegalMatterModel,
    MatterUpdateProposalModel,
    MessageCandidateModel,
    OutboxEventModel,
    PriorityConfirmationModel,
    ReviewPackageModel,
    ReviewRecordModel,
    StorageQuotaReservationModel,
    SystemSettingModel,
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
                builder_version=snapshot.builder_version,
                selection_policy_version=snapshot.selection_policy_version,
                current_message_version=snapshot.current_message_version,
                attachment_version_hash=snapshot.attachment_version_hash,
                truncated=snapshot.truncated,
                truncation_reason=snapshot.truncation_reason,
                original_size=snapshot.original_size,
                included_size=snapshot.included_size,
                source_id=(
                    snapshot.source_id
                    or (snapshot.source_ids[0] if snapshot.source_ids else str(snapshot.id))
                ),
                snapshot_version=snapshot.snapshot_version,
                attachment_ids=snapshot.attachment_ids,
                included_segments=snapshot.included_segments,
                excluded_segments=snapshot.excluded_segments,
                thread_metadata=snapshot.thread_metadata,
                content=snapshot.content,
            )
        )

    async def get(self, snapshot_id: UUID) -> ContextSnapshot | None:
        model = await self._session.get(ContextSnapshotModel, snapshot_id)
        return None if model is None else self._to_domain(model)

    async def find_by_source_hash(
        self, *, source_type: str, source_id: str, content_hash: str
    ) -> ContextSnapshot | None:
        statement = select(ContextSnapshotModel).where(
            ContextSnapshotModel.source_type == source_type,
            ContextSnapshotModel.source_id == source_id,
            ContextSnapshotModel.content_hash == content_hash,
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._to_domain(model)

    @staticmethod
    def _to_domain(model: ContextSnapshotModel) -> ContextSnapshot:
        return ContextSnapshot(
            id=model.id,
            source_type=model.source_type,
            source_ids=model.source_ids,
            message_ids=model.message_ids,
            file_ids=model.file_ids,
            relevant_matter_ids=model.relevant_matter_ids,
            participant_ids=model.participant_ids,
            permission_snapshot=model.permission_snapshot,
            generated_at=model.generated_at,
            content_hash=model.content_hash,
            source_id=model.source_id,
            snapshot_version=model.snapshot_version,
            attachment_ids=model.attachment_ids,
            included_segments=model.included_segments,
            excluded_segments=model.excluded_segments,
            thread_metadata=model.thread_metadata,
            content=model.content,
            builder_version=model.builder_version,
            selection_policy_version=model.selection_policy_version,
            current_message_version=model.current_message_version,
            attachment_version_hash=model.attachment_version_hash,
            truncated=model.truncated,
            truncation_reason=model.truncation_reason,
            original_size=model.original_size,
            included_size=model.included_size,
            created_at=model.created_at,
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
            feishu_message_id=candidate.feishu_message_id,
            requires_manual_review=candidate.requires_manual_review,
            analysis_payload=candidate.analysis_payload,
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
        model.context_snapshot_id = candidate.context_snapshot_id
        model.legal_relevance = candidate.legal_relevance
        model.message_role = candidate.message_role
        model.recommended_action = candidate.recommended_action
        model.confidence = candidate.confidence
        model.title_proposal = candidate.title_proposal
        model.category_proposals = candidate.category_proposals
        model.deadline_proposals = candidate.deadline_proposals
        model.related_matter_proposals = candidate.related_matter_proposals
        model.evidence_refs = candidate.evidence_refs
        model.agent_run_id = candidate.agent_run_id
        model.feishu_message_id = candidate.feishu_message_id
        model.requires_manual_review = candidate.requires_manual_review
        model.analysis_payload = candidate.analysis_payload
        model.confirmed_by = candidate.confirmed_by
        model.confirmed_at = candidate.confirmed_at
        model.version = candidate.version

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

    async def get_active_for_message(self, message_id: UUID) -> MessageCandidate | None:
        statement = select(MessageCandidateModel).where(
            MessageCandidateModel.feishu_message_id == message_id,
            MessageCandidateModel.status.in_(
                [
                    CandidateStatus.PENDING_ANALYSIS,
                    CandidateStatus.PENDING_CONFIRMATION,
                    CandidateStatus.CONFIRMED,
                    CandidateStatus.LINKED,
                ]
            ),
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._to_domain(model)

    async def append_revision(self, revision: CandidateRevision) -> None:
        self._session.add(
            CandidateRevisionModel(
                id=revision.id,
                candidate_id=revision.candidate_id,
                revision=revision.revision,
                agent_run_id=revision.agent_run_id,
                analysis_payload=revision.analysis_payload,
                created_at=revision.created_at,
                superseded_at=revision.superseded_at,
                superseded_by=revision.superseded_by,
            )
        )
        # The self-referential FK is checked immediately, so persist the new
        # revision before pointing the prior current revision at it.
        await self._session.flush()
        await self._session.execute(
            update(CandidateRevisionModel)
            .where(
                CandidateRevisionModel.candidate_id == revision.candidate_id,
                CandidateRevisionModel.id != revision.id,
                CandidateRevisionModel.superseded_at.is_(None),
            )
            .values(
                superseded_at=revision.created_at,
                superseded_by=revision.id,
            )
        )

    async def list_revisions(self, candidate_id: UUID) -> Sequence[CandidateRevision]:
        statement = (
            select(CandidateRevisionModel)
            .where(CandidateRevisionModel.candidate_id == candidate_id)
            .order_by(CandidateRevisionModel.revision.desc())
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [
            CandidateRevision(
                id=model.id,
                candidate_id=model.candidate_id,
                revision=model.revision,
                agent_run_id=model.agent_run_id,
                analysis_payload=model.analysis_payload,
                created_at=model.created_at,
                superseded_at=model.superseded_at,
                superseded_by=model.superseded_by,
            )
            for model in models
        ]

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
            feishu_message_id=model.feishu_message_id,
            requires_manual_review=model.requires_manual_review,
            analysis_payload=model.analysis_payload,
            confirmed_by=model.confirmed_by,
            confirmed_at=model.confirmed_at,
            version=model.version,
        )


class SqlAlchemyAgentDefinitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, definition: AgentDefinition) -> None:
        self._session.add(
            AgentDefinitionModel(
                id=definition.id,
                key=definition.key,
                name=definition.name,
                version=definition.version,
                description=definition.description,
                status=definition.status,
                prompt_template=definition.prompt_template,
                input_schema=definition.input_schema,
                output_schema=definition.output_schema,
                allowed_tools=definition.allowed_tools,
                allowed_knowledge_scopes=definition.allowed_knowledge_scopes,
                timeout_seconds=definition.timeout_seconds,
                max_retries=definition.max_retries,
                requires_human_review=definition.requires_human_review,
                created_at=definition.created_at,
                updated_at=definition.updated_at,
            )
        )

    async def get(self, definition_id: UUID) -> AgentDefinition | None:
        model = await self._session.get(AgentDefinitionModel, definition_id)
        return None if model is None else self._to_domain(model)

    async def get_active(self, key: str) -> AgentDefinition | None:
        statement = (
            select(AgentDefinitionModel)
            .where(
                AgentDefinitionModel.key == key,
                AgentDefinitionModel.status == AgentDefinitionStatus.ACTIVE,
            )
            .order_by(AgentDefinitionModel.created_at.desc())
            .limit(1)
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._to_domain(model)

    @staticmethod
    def _to_domain(model: AgentDefinitionModel) -> AgentDefinition:
        return AgentDefinition(
            id=model.id,
            key=model.key,
            name=model.name,
            version=model.version,
            description=model.description,
            status=model.status,
            prompt_template=model.prompt_template,
            input_schema=model.input_schema,
            output_schema=model.output_schema,
            allowed_tools=model.allowed_tools,
            allowed_knowledge_scopes=model.allowed_knowledge_scopes,
            timeout_seconds=model.timeout_seconds,
            max_retries=model.max_retries,
            requires_human_review=model.requires_human_review,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class SqlAlchemyAgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tracked: dict[UUID, AgentRunModel] = {}

    async def add(self, run: AgentRun) -> None:
        model = AgentRunModel(
            id=run.id,
            agent_definition_id=run.agent_definition_id,
            matter_id=run.matter_id,
            work_item_id=run.work_item_id,
            feishu_message_id=run.feishu_message_id,
            context_snapshot_id=run.context_snapshot_id,
            status=run.status,
            objective=run.objective,
            input_payload=run.input_payload,
            output_payload=run.output_payload,
            raw_stdout=run.raw_stdout,
            raw_stderr=run.raw_stderr,
            prompt_snapshot=run.prompt_snapshot,
            working_directory=run.working_directory,
            started_at=run.started_at,
            heartbeat_at=run.heartbeat_at,
            finished_at=run.finished_at,
            timeout_at=run.timeout_at,
            attempt_number=run.attempt_number,
            max_attempts=run.max_attempts,
            failure_code=run.failure_code,
            failure_message=run.failure_message,
            correlation_id=run.correlation_id,
            created_by=run.created_by,
            runtime_version=run.runtime_version,
            agent_definition_version=run.agent_definition_version,
            prompt_version=run.prompt_version,
            validation_errors=run.validation_errors,
            repair_attempted=run.repair_attempted,
            token_usage=run.token_usage,
            worker_id=run.worker_id,
            lease_expires_at=run.lease_expires_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
            version=run.version,
        )
        self._tracked[run.id] = model
        self._session.add(model)
        self._session.add(
            AgentRunStatusEventModel(
                id=uuid4(),
                agent_run_id=run.id,
                from_status=None,
                to_status=run.status,
                changed_at=run.created_at,
                correlation_id=run.correlation_id,
                attempt_number=run.attempt_number,
                failure_code=run.failure_code,
                failure_message=run.failure_message,
            )
        )
        run.drain_status_changes()

    async def get(self, run_id: UUID) -> AgentRun | None:
        model = await self._session.get(AgentRunModel, run_id)
        if model is None:
            return None
        self._tracked[run_id] = model
        return self._to_domain(model)

    async def get_for_update(self, run_id: UUID) -> AgentRun | None:
        statement = select(AgentRunModel).where(AgentRunModel.id == run_id).with_for_update()
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked[run_id] = model
        return self._to_domain(model)

    async def save(self, run: AgentRun) -> None:
        model = self._tracked.get(run.id)
        if model is None:
            model = await self._session.get(AgentRunModel, run.id)
        if model is None:
            raise RuntimeError(f"AgentRun {run.id} is not tracked")
        model.status = run.status
        model.input_payload = run.input_payload
        model.output_payload = run.output_payload
        model.raw_stdout = run.raw_stdout
        model.raw_stderr = run.raw_stderr
        model.working_directory = run.working_directory
        model.started_at = run.started_at
        model.heartbeat_at = run.heartbeat_at
        model.finished_at = run.finished_at
        model.timeout_at = run.timeout_at
        model.attempt_number = run.attempt_number
        model.failure_code = run.failure_code
        model.failure_message = run.failure_message
        model.runtime_version = run.runtime_version
        model.agent_definition_version = run.agent_definition_version
        model.prompt_version = run.prompt_version
        model.validation_errors = run.validation_errors
        model.repair_attempted = run.repair_attempted
        model.token_usage = run.token_usage
        model.worker_id = run.worker_id
        model.lease_expires_at = run.lease_expires_at
        model.updated_at = run.updated_at
        model.version = run.version
        self._session.add_all(
            [
                AgentRunStatusEventModel(
                    id=change.id,
                    agent_run_id=change.agent_run_id,
                    from_status=change.from_status,
                    to_status=change.to_status,
                    changed_at=change.changed_at,
                    correlation_id=change.correlation_id,
                    attempt_number=change.attempt_number,
                    failure_code=change.failure_code,
                    failure_message=change.failure_message,
                )
                for change in run.drain_status_changes()
            ]
        )

    async def list(self, *, status: AgentRunStatus | None, limit: int) -> Sequence[AgentRun]:
        statement: Select[tuple[AgentRunModel]] = select(AgentRunModel)
        if status is not None:
            statement = statement.where(AgentRunModel.status == status)
        statement = statement.order_by(AgentRunModel.created_at.desc()).limit(limit)
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    async def list_by_message(self, message_id: UUID) -> Sequence[AgentRun]:
        statement = (
            select(AgentRunModel)
            .where(AgentRunModel.feishu_message_id == message_id)
            .order_by(AgentRunModel.created_at.desc())
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    async def list_status_events(self, run_id: UUID) -> Sequence[AgentRunStatusChange]:
        statement = (
            select(AgentRunStatusEventModel)
            .where(AgentRunStatusEventModel.agent_run_id == run_id)
            .order_by(
                AgentRunStatusEventModel.changed_at,
                AgentRunStatusEventModel.id,
            )
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [
            AgentRunStatusChange(
                id=model.id,
                agent_run_id=model.agent_run_id,
                from_status=model.from_status,
                to_status=model.to_status,
                changed_at=model.changed_at,
                correlation_id=model.correlation_id,
                attempt_number=model.attempt_number,
                failure_code=model.failure_code,
                failure_message=model.failure_message,
            )
            for model in models
        ]

    async def list_stale(
        self,
        *,
        statuses: Sequence[AgentRunStatus],
        older_than: datetime,
        limit: int,
    ) -> Sequence[AgentRun]:
        statement = (
            select(AgentRunModel)
            .where(
                AgentRunModel.status.in_(list(statuses)),
                func.coalesce(
                    AgentRunModel.heartbeat_at,
                    AgentRunModel.updated_at,
                )
                < older_than,
            )
            .order_by(AgentRunModel.updated_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        models = (await self._session.execute(statement)).scalars().all()
        for model in models:
            self._tracked[model.id] = model
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_domain(model: AgentRunModel) -> AgentRun:
        return AgentRun(
            id=model.id,
            agent_definition_id=model.agent_definition_id,
            matter_id=model.matter_id,
            work_item_id=model.work_item_id,
            feishu_message_id=model.feishu_message_id,
            context_snapshot_id=model.context_snapshot_id,
            status=model.status,
            objective=model.objective,
            input_payload=model.input_payload,
            output_payload=model.output_payload,
            raw_stdout=model.raw_stdout,
            raw_stderr=model.raw_stderr,
            prompt_snapshot=model.prompt_snapshot,
            working_directory=model.working_directory,
            started_at=model.started_at,
            heartbeat_at=model.heartbeat_at,
            finished_at=model.finished_at,
            timeout_at=model.timeout_at,
            attempt_number=model.attempt_number,
            max_attempts=model.max_attempts,
            failure_code=model.failure_code,
            failure_message=model.failure_message,
            runtime_version=model.runtime_version,
            agent_definition_version=model.agent_definition_version,
            prompt_version=model.prompt_version,
            validation_errors=model.validation_errors,
            repair_attempted=model.repair_attempted,
            token_usage=model.token_usage,
            worker_id=model.worker_id,
            lease_expires_at=model.lease_expires_at,
            correlation_id=model.correlation_id,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class SqlAlchemyAgentRunAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, attempt: AgentRunAttempt) -> None:
        self._session.add(
            AgentRunAttemptModel(
                id=attempt.id,
                agent_run_id=attempt.run_id,
                attempt_number=attempt.attempt_number,
                lease_token=attempt.lease_token,
                worker_id=attempt.worker_id,
                status=attempt.status,
                lease_expires_at=attempt.lease_expires_at,
                started_at=attempt.started_at,
                heartbeat_at=attempt.heartbeat_at,
                finished_at=attempt.finished_at,
                failure_code=attempt.failure_code,
                failure_message=attempt.failure_message,
            )
        )

    async def heartbeat(
        self,
        lease: AgentAttemptLease,
        *,
        heartbeat_at: datetime,
        lease_expires_at: datetime,
    ) -> None:
        statement = (
            update(AgentRunAttemptModel)
            .where(*self._active_lease_predicates(lease))
            .values(
                heartbeat_at=heartbeat_at,
                lease_expires_at=lease_expires_at,
            )
            .returning(AgentRunAttemptModel.id)
        )
        if (await self._session.execute(statement)).scalar_one_or_none() is None:
            self._raise_stale(lease)

    async def complete(self, lease: AgentAttemptLease, *, finished_at: datetime) -> None:
        statement = (
            update(AgentRunAttemptModel)
            .where(*self._active_lease_predicates(lease))
            .values(
                status=AgentAttemptStatus.COMPLETED,
                finished_at=finished_at,
                lease_expires_at=finished_at,
                failure_code=None,
                failure_message=None,
            )
            .returning(AgentRunAttemptModel.id)
        )
        if (await self._session.execute(statement)).scalar_one_or_none() is None:
            self._raise_stale(lease)

    async def fail(
        self,
        lease: AgentAttemptLease,
        *,
        status: AgentAttemptStatus,
        failure_code: str,
        failure_message: str,
        finished_at: datetime,
    ) -> None:
        if status not in {
            AgentAttemptStatus.FAILED,
            AgentAttemptStatus.TIMED_OUT,
            AgentAttemptStatus.CANCELLED,
        }:
            raise ValueError("Attempt failure status must be terminal.")
        statement = (
            update(AgentRunAttemptModel)
            .where(*self._active_lease_predicates(lease))
            .values(
                status=status,
                finished_at=finished_at,
                lease_expires_at=finished_at,
                failure_code=failure_code,
                failure_message=failure_message,
            )
            .returning(AgentRunAttemptModel.id)
        )
        if (await self._session.execute(statement)).scalar_one_or_none() is None:
            self._raise_stale(lease)

    async def expire_current(
        self,
        *,
        run_id: UUID,
        attempt_number: int,
        finished_at: datetime,
    ) -> bool:
        statement = (
            update(AgentRunAttemptModel)
            .where(
                AgentRunAttemptModel.agent_run_id == run_id,
                AgentRunAttemptModel.attempt_number == attempt_number,
                AgentRunAttemptModel.status == AgentAttemptStatus.RUNNING,
            )
            .values(
                status=AgentAttemptStatus.EXPIRED,
                finished_at=finished_at,
                lease_expires_at=finished_at,
                failure_code="AGENT_LEASE_EXPIRED",
                failure_message="Agent worker heartbeat lease expired.",
            )
            .returning(AgentRunAttemptModel.id)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def list_by_run(self, run_id: UUID) -> Sequence[AgentRunAttempt]:
        statement = (
            select(AgentRunAttemptModel)
            .where(AgentRunAttemptModel.agent_run_id == run_id)
            .order_by(AgentRunAttemptModel.attempt_number)
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _active_lease_predicates(
        lease: AgentAttemptLease,
    ) -> tuple[ColumnElement[bool], ...]:
        return (
            AgentRunAttemptModel.agent_run_id == lease.run_id,
            AgentRunAttemptModel.attempt_number == lease.attempt_number,
            AgentRunAttemptModel.lease_token == lease.lease_token,
            AgentRunAttemptModel.status == AgentAttemptStatus.RUNNING,
        )

    @staticmethod
    def _raise_stale(lease: AgentAttemptLease) -> None:
        raise StaleAgentAttemptError(
            "The Agent Attempt lease is stale and cannot update this run.",
            details={
                "runId": str(lease.run_id),
                "attemptNumber": lease.attempt_number,
            },
        )

    @staticmethod
    def _to_domain(model: AgentRunAttemptModel) -> AgentRunAttempt:
        return AgentRunAttempt(
            id=model.id,
            run_id=model.agent_run_id,
            attempt_number=model.attempt_number,
            lease_token=model.lease_token,
            worker_id=model.worker_id,
            status=model.status,
            lease_expires_at=model.lease_expires_at,
            started_at=model.started_at,
            heartbeat_at=model.heartbeat_at,
            finished_at=model.finished_at,
            failure_code=model.failure_code,
            failure_message=model.failure_message,
        )


class SqlAlchemyAgentRunSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, sources: Sequence[AgentRunSource]) -> None:
        self._session.add_all(
            [
                AgentRunSourceModel(
                    id=source.id,
                    agent_run_id=source.agent_run_id,
                    source_type=source.source_type,
                    source_id=source.source_id,
                    source_version=source.source_version,
                    source_hash=source.source_hash,
                    display_name=source.display_name,
                    citation_metadata=source.citation_metadata,
                    created_at=source.created_at,
                )
                for source in sources
            ]
        )

    async def list_by_run(self, run_id: UUID) -> Sequence[AgentRunSource]:
        statement = (
            select(AgentRunSourceModel)
            .where(AgentRunSourceModel.agent_run_id == run_id)
            .order_by(AgentRunSourceModel.created_at, AgentRunSourceModel.id)
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [
            AgentRunSource(
                id=model.id,
                agent_run_id=model.agent_run_id,
                source_type=model.source_type,
                source_id=model.source_id,
                source_version=model.source_version,
                source_hash=model.source_hash,
                display_name=model.display_name,
                citation_metadata=model.citation_metadata,
                created_at=model.created_at,
            )
            for model in models
        ]


class SqlAlchemyDraftArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, artifact: DraftArtifact) -> None:
        self._session.add(
            DraftArtifactModel(
                id=artifact.id,
                agent_run_id=artifact.agent_run_id,
                artifact_type=artifact.artifact_type,
                title=artifact.title,
                content=artifact.content,
                structured_payload=artifact.structured_payload,
                status=artifact.status,
                version=artifact.version,
                created_at=artifact.created_at,
                updated_at=artifact.updated_at,
            )
        )


class SqlAlchemyLegalMatterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tracked: dict[UUID, LegalMatterModel] = {}

    async def add(self, matter: LegalMatter) -> None:
        model = LegalMatterModel(
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
            priority=matter.priority,
            priority_source=matter.priority_source,
            target_deadline_at=matter.target_deadline_at,
            next_action=matter.next_action,
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
        self._tracked[matter.id] = model
        self._session.add(model)

    async def get(self, matter_id: UUID) -> LegalMatter | None:
        model = await self._session.get(LegalMatterModel, matter_id)
        if model is not None:
            self._tracked[matter_id] = model
        return None if model is None else self._to_domain(model)

    async def get_for_update(self, matter_id: UUID) -> LegalMatter | None:
        statement = (
            select(LegalMatterModel).where(LegalMatterModel.id == matter_id).with_for_update()
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is not None:
            self._tracked[matter_id] = model
        return None if model is None else self._to_domain(model)

    async def save(self, matter: LegalMatter) -> None:
        model = self._tracked.get(matter.id)
        if model is None:
            model = await self._session.get(LegalMatterModel, matter.id)
        if model is None:
            raise RuntimeError(f"Legal matter {matter.id} is not tracked")
        model.title = matter.title
        model.primary_category = matter.primary_category
        model.owner_id = matter.owner_id
        model.work_status = matter.work_status
        model.priority = matter.priority
        model.priority_source = matter.priority_source
        model.target_deadline_at = matter.target_deadline_at
        model.next_action = matter.next_action
        model.version = matter.version

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
            priority=model.priority,
            priority_source=model.priority_source,
            target_deadline_at=model.target_deadline_at,
            next_action=model.next_action,
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


class SqlAlchemyMatterUpdateProposalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tracked: dict[UUID, MatterUpdateProposalModel] = {}

    async def add(self, proposal: MatterUpdateProposal) -> None:
        model = MatterUpdateProposalModel(
            id=proposal.id,
            candidate_id=proposal.candidate_id,
            matter_id=proposal.matter_id,
            base_matter_version=proposal.base_matter_version,
            proposed_changes=proposal.proposed_changes,
            final_changes=proposal.final_changes,
            field_decisions=proposal.field_decisions,
            reason=proposal.reason,
            status=proposal.status,
            created_by=proposal.created_by,
            reviewed_by=proposal.reviewed_by,
            reviewed_at=proposal.reviewed_at,
            rejection_reason=proposal.rejection_reason,
            version=proposal.version,
            created_at=proposal.created_at,
        )
        self._tracked[proposal.id] = model
        self._session.add(model)

    async def get(self, proposal_id: UUID) -> MatterUpdateProposal | None:
        model = await self._session.get(MatterUpdateProposalModel, proposal_id)
        if model is None:
            return None
        self._tracked[proposal_id] = model
        return self._to_domain(model)

    async def get_for_update(self, proposal_id: UUID) -> MatterUpdateProposal | None:
        statement = (
            select(MatterUpdateProposalModel)
            .where(MatterUpdateProposalModel.id == proposal_id)
            .with_for_update()
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked[proposal_id] = model
        return self._to_domain(model)

    async def save(self, proposal: MatterUpdateProposal) -> None:
        model = self._tracked.get(proposal.id)
        if model is None:
            model = await self._session.get(MatterUpdateProposalModel, proposal.id)
        if model is None:
            raise RuntimeError(f"Matter update proposal {proposal.id} is not tracked")
        model.status = proposal.status
        model.final_changes = proposal.final_changes
        model.field_decisions = proposal.field_decisions
        model.reviewed_by = proposal.reviewed_by
        model.reviewed_at = proposal.reviewed_at
        model.rejection_reason = proposal.rejection_reason
        model.version = proposal.version

    async def list(
        self,
        *,
        status: MatterUpdateProposalStatus | None,
        matter_id: UUID | None,
        limit: int,
    ) -> Sequence[MatterUpdateProposal]:
        statement: Select[tuple[MatterUpdateProposalModel]] = select(MatterUpdateProposalModel)
        if status is not None:
            statement = statement.where(MatterUpdateProposalModel.status == status)
        if matter_id is not None:
            statement = statement.where(MatterUpdateProposalModel.matter_id == matter_id)
        statement = statement.order_by(MatterUpdateProposalModel.created_at.desc()).limit(limit)
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_domain(model: MatterUpdateProposalModel) -> MatterUpdateProposal:
        return MatterUpdateProposal(
            id=model.id,
            candidate_id=model.candidate_id,
            matter_id=model.matter_id,
            base_matter_version=model.base_matter_version,
            proposed_changes=model.proposed_changes,
            final_changes=model.final_changes,
            field_decisions=model.field_decisions,
            reason=model.reason,
            status=model.status,
            created_by=model.created_by,
            reviewed_by=model.reviewed_by,
            reviewed_at=model.reviewed_at,
            rejection_reason=model.rejection_reason,
            created_at=model.created_at,
            version=model.version,
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
        statement = select(WorkItemModel).where(WorkItemModel.id == work_item_id).with_for_update()
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
        model.status = work_item.status
        model.owner_id = work_item.owner_id
        model.priority_source = work_item.priority_source
        model.priority_reasons = work_item.priority_reasons
        model.override_reason = work_item.override_reason
        model.planned_complete_at = work_item.planned_complete_at
        model.next_action = work_item.next_action
        model.waiting_party_id = work_item.waiting_party_id
        model.waiting_reason = work_item.waiting_reason
        model.waiting_since = work_item.waiting_since
        model.paused_reason = work_item.paused_reason
        model.is_blocked = work_item.is_blocked
        model.blocker_reason = work_item.blocker_reason
        model.blocker_owner_id = work_item.blocker_owner_id
        model.planned_start_at = work_item.planned_start_at
        model.completed_at = work_item.completed_at
        model.cancelled_at = work_item.cancelled_at
        model.cancel_reason = work_item.cancel_reason
        model.priority_confirmed_by = work_item.priority_confirmed_by
        model.priority_confirmed_at = work_item.priority_confirmed_at
        model.version = work_item.version

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
            paused_reason=work_item.paused_reason,
            is_blocked=work_item.is_blocked,
            blocker_reason=work_item.blocker_reason,
            blocker_owner_id=work_item.blocker_owner_id,
            planned_start_at=work_item.planned_start_at,
            planned_complete_at=work_item.planned_complete_at,
            completed_at=work_item.completed_at,
            cancelled_at=work_item.cancelled_at,
            cancel_reason=work_item.cancel_reason,
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
            paused_reason=model.paused_reason,
            is_blocked=model.is_blocked,
            blocker_reason=model.blocker_reason,
            blocker_owner_id=model.blocker_owner_id,
            planned_start_at=model.planned_start_at,
            planned_complete_at=model.planned_complete_at,
            completed_at=model.completed_at,
            cancelled_at=model.cancelled_at,
            cancel_reason=model.cancel_reason,
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
        self._tracked: dict[UUID, WorkItemDependencyModel] = {}

    async def add(self, dependency: WorkItemDependency) -> None:
        model = WorkItemDependencyModel(
            id=dependency.id,
            work_item_id=dependency.work_item_id,
            depends_on_work_item_id=dependency.depends_on_work_item_id,
            dependency_type=dependency.dependency_type,
            status=dependency.status,
            external_party_id=dependency.external_party_id,
            description=dependency.description,
            satisfied_at=dependency.satisfied_at,
            satisfied_by=dependency.satisfied_by,
            waived_by=dependency.waived_by,
            waived_at=dependency.waived_at,
            version=dependency.version,
        )
        self._tracked[dependency.id] = model
        self._session.add(model)

    async def get_for_update(self, dependency_id: UUID) -> WorkItemDependency | None:
        statement = (
            select(WorkItemDependencyModel)
            .where(WorkItemDependencyModel.id == dependency_id)
            .with_for_update()
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked[dependency_id] = model
        return self._to_domain(model)

    async def save(self, dependency: WorkItemDependency) -> None:
        model = self._tracked.get(dependency.id)
        if model is None:
            model = await self._session.get(WorkItemDependencyModel, dependency.id)
        if model is None:
            raise RuntimeError(f"Work item dependency {dependency.id} is not tracked")
        model.status = dependency.status
        model.satisfied_at = dependency.satisfied_at
        model.satisfied_by = dependency.satisfied_by
        model.waived_by = dependency.waived_by
        model.waived_at = dependency.waived_at
        model.version = dependency.version

    async def list_by_work_item(self, work_item_id: UUID) -> Sequence[WorkItemDependency]:
        statement = (
            select(WorkItemDependencyModel)
            .where(WorkItemDependencyModel.work_item_id == work_item_id)
            .order_by(WorkItemDependencyModel.created_at)
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_domain(model: WorkItemDependencyModel) -> WorkItemDependency:
        return WorkItemDependency(
            id=model.id,
            work_item_id=model.work_item_id,
            depends_on_work_item_id=model.depends_on_work_item_id,
            dependency_type=model.dependency_type,
            status=model.status,
            external_party_id=model.external_party_id,
            description=model.description,
            satisfied_at=model.satisfied_at,
            satisfied_by=model.satisfied_by,
            waived_by=model.waived_by,
            waived_at=model.waived_at,
            version=model.version,
        )


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
            select(ReviewPackageModel).where(ReviewPackageModel.id == package_id).with_for_update()
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

    async def get_by_review_record(self, review_record_id: UUID) -> Communication | None:
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
        self._tracked_messages: dict[UUID, FeishuMessageModel] = {}
        self._tracked_attachments: dict[UUID, FeishuAttachmentModel] = {}

    async def get_event_by_external_id(
        self, event_id: str, *, tenant_key: str | None = None
    ) -> FeishuRawEvent | None:
        statement = select(FeishuEventModel).where(FeishuEventModel.event_id == event_id)
        if tenant_key is not None:
            statement = statement.where(FeishuEventModel.tenant_key == tenant_key)
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
            FeishuMessageModel.tenant_key == (tenant_key or ""),
            FeishuMessageModel.message_id == message_id,
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked_messages[model.id] = model
        return self._message_to_domain(model)

    async def add_message(self, message: FeishuMessage) -> None:
        model = FeishuMessageModel(
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
            plain_text=message.plain_text,
            structured_content=message.structured_content or message.content,
            attachments=message.attachments,
            content_hash=message.content_hash or self._message_hash(message.raw_message),
            edited_at=message.edited_at,
            recalled_at=message.recalled_at,
            unsupported_reason=message.unsupported_reason,
            status=message.status,
            context_snapshot_id=message.context_snapshot_id,
            last_agent_run_id=message.last_agent_run_id,
            analysis_attempts=message.analysis_attempts,
            failure_code=message.failure_code,
            failure_message=message.failure_message,
            version=message.version,
        )
        self._tracked_messages[message.id] = model
        self._session.add(model)

    async def get_message_by_id(self, message_id: UUID) -> FeishuMessage | None:
        model = await self._session.get(FeishuMessageModel, message_id)
        if model is None:
            return None
        self._tracked_messages[message_id] = model
        return self._message_to_domain(model)

    async def get_message_for_update(self, message_id: UUID) -> FeishuMessage | None:
        statement = (
            select(FeishuMessageModel).where(FeishuMessageModel.id == message_id).with_for_update()
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked_messages[message_id] = model
        return self._message_to_domain(model)

    async def list_context_messages(
        self, message: FeishuMessage, *, limit: int
    ) -> Sequence[FeishuMessage]:
        thread_key = message.thread_id or message.root_id or message.message_id
        external_ids = {
            value
            for value in [message.message_id, message.parent_id, message.root_id, thread_key]
            if value
        }
        statement = (
            select(FeishuMessageModel)
            .where(
                FeishuMessageModel.tenant_key == message.tenant_key,
                or_(
                    FeishuMessageModel.chat_id == message.chat_id,
                    FeishuMessageModel.message_id.in_(external_ids),
                ),
                or_(
                    FeishuMessageModel.message_id.in_(external_ids),
                    FeishuMessageModel.parent_id.in_(external_ids),
                    FeishuMessageModel.root_id == thread_key,
                    FeishuMessageModel.thread_id == thread_key,
                ),
            )
            .order_by(
                FeishuMessageModel.create_time.desc().nullslast(),
                FeishuMessageModel.message_id.desc(),
            )
            .limit(limit)
        )
        models = (await self._session.execute(statement)).scalars().all()
        for model in models:
            self._tracked_messages[model.id] = model
        return [self._message_to_domain(model) for model in models]

    async def list_messages(
        self,
        *,
        statuses: Sequence[FeishuMessageStatus] | None,
        search: str | None,
        chat_id: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        limit: int,
    ) -> Sequence[FeishuMessage]:
        statement: Select[tuple[FeishuMessageModel]] = select(FeishuMessageModel)
        if statuses:
            statement = statement.where(FeishuMessageModel.status.in_(list(statuses)))
        if search:
            statement = statement.where(FeishuMessageModel.plain_text.ilike(f"%{search}%"))
        if chat_id:
            statement = statement.where(FeishuMessageModel.chat_id == chat_id)
        if created_from:
            statement = statement.where(FeishuMessageModel.create_time >= created_from)
        if created_to:
            statement = statement.where(FeishuMessageModel.create_time <= created_to)
        statement = statement.order_by(
            FeishuMessageModel.create_time.desc().nullslast(),
            FeishuMessageModel.created_at.desc(),
        ).limit(limit)
        models = (await self._session.execute(statement)).scalars().all()
        for model in models:
            self._tracked_messages[model.id] = model
        return [self._message_to_domain(model) for model in models]

    async def list_queued_without_active_run(self, *, limit: int) -> Sequence[FeishuMessage]:
        active_run_exists = exists(
            select(AgentRunModel.id).where(
                AgentRunModel.feishu_message_id == FeishuMessageModel.id,
                AgentRunModel.status.in_(
                    [
                        AgentRunStatus.QUEUED,
                        AgentRunStatus.PREPARING,
                        AgentRunStatus.RUNNING,
                        AgentRunStatus.VALIDATING,
                    ]
                ),
            )
        )
        statement = (
            select(FeishuMessageModel)
            .where(
                FeishuMessageModel.status == FeishuMessageStatus.QUEUED_FOR_ANALYSIS,
                ~active_run_exists,
            )
            .order_by(FeishuMessageModel.updated_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        models = (await self._session.execute(statement)).scalars().all()
        for model in models:
            self._tracked_messages[model.id] = model
        return [self._message_to_domain(model) for model in models]

    async def save_message(self, message: FeishuMessage) -> None:
        model = self._tracked_messages.get(message.id)
        if model is None:
            model = await self._session.get(FeishuMessageModel, message.id)
        if model is None:
            raise RuntimeError(f"FeishuMessage {message.id} is not tracked")
        model.status = message.status
        model.context_snapshot_id = message.context_snapshot_id
        model.last_agent_run_id = message.last_agent_run_id
        model.analysis_attempts = message.analysis_attempts
        model.failure_code = message.failure_code
        model.failure_message = message.failure_message
        model.event_id = message.event_id
        model.message_type = message.message_type
        model.content = message.content
        model.mentions = message.mentions
        model.update_time = message.update_time
        model.raw_message = message.raw_message
        model.plain_text = message.plain_text
        model.structured_content = message.structured_content
        model.attachments = message.attachments
        model.content_hash = message.content_hash or self._message_hash(message.raw_message)
        model.edited_at = message.edited_at
        model.recalled_at = message.recalled_at
        model.unsupported_reason = message.unsupported_reason
        model.version = message.version

    async def next_message_revision(self, message_id: UUID) -> int:
        statement = select(func.coalesce(func.max(FeishuMessageVersionModel.revision), 0)).where(
            FeishuMessageVersionModel.feishu_message_id == message_id
        )
        return int((await self._session.execute(statement)).scalar_one()) + 1

    async def add_message_version(self, version: FeishuMessageVersion) -> None:
        self._session.add(
            FeishuMessageVersionModel(
                id=version.id,
                feishu_message_id=version.feishu_message_id,
                event_id=version.event_id,
                revision=version.revision,
                raw_payload=version.raw_payload,
                content_hash=version.content_hash,
                plain_text=version.plain_text,
                structured_content=version.structured_content,
                attachments=version.attachments,
                edited_at=version.edited_at,
                recalled_at=version.recalled_at,
                is_recalled=version.is_recalled,
                created_at=version.created_at,
            )
        )

    async def list_message_versions(self, message_id: UUID) -> Sequence[FeishuMessageVersion]:
        statement = (
            select(FeishuMessageVersionModel)
            .where(FeishuMessageVersionModel.feishu_message_id == message_id)
            .order_by(FeishuMessageVersionModel.revision.desc())
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [
            FeishuMessageVersion(
                id=model.id,
                feishu_message_id=model.feishu_message_id,
                event_id=model.event_id,
                revision=model.revision,
                raw_payload=model.raw_payload,
                content_hash=model.content_hash,
                plain_text=model.plain_text,
                structured_content=model.structured_content,
                attachments=model.attachments,
                edited_at=model.edited_at,
                recalled_at=model.recalled_at,
                is_recalled=model.is_recalled,
                created_at=model.created_at,
            )
            for model in models
        ]

    async def add_attachments(self, attachments: Sequence[FeishuAttachment]) -> None:
        models = [
            FeishuAttachmentModel(
                id=value.id,
                feishu_message_id=value.feishu_message_id,
                message_version_id=value.message_version_id,
                file_key=value.file_key,
                file_name=value.file_name,
                mime_type=value.mime_type,
                size=value.size,
                sha256=value.sha256,
                local_path=value.local_path,
                download_status=value.download_status,
                download_error=value.download_error,
                authorized_for_analysis=value.authorized_for_analysis,
                extraction_status=value.extraction_status,
                extractor_version=value.extractor_version,
                page_count=value.page_count,
                character_count=value.character_count,
                extraction_error_code=value.extraction_error_code,
                created_at=value.created_at,
                updated_at=value.updated_at,
            )
            for value in attachments
        ]
        self._tracked_attachments.update({model.id: model for model in models})
        self._session.add_all(models)

    async def list_pending_attachments(self, message_id: UUID) -> Sequence[FeishuAttachment]:
        statement = select(FeishuAttachmentModel).where(
            FeishuAttachmentModel.feishu_message_id == message_id,
            FeishuAttachmentModel.download_status == AttachmentDownloadStatus.PENDING,
        )
        models = (await self._session.execute(statement)).scalars().all()
        self._tracked_attachments.update({model.id: model for model in models})
        return [self._attachment_to_domain(model) for model in models]

    async def list_attachments(self, message_id: UUID) -> Sequence[FeishuAttachment]:
        statement = (
            select(FeishuAttachmentModel)
            .where(FeishuAttachmentModel.feishu_message_id == message_id)
            .order_by(FeishuAttachmentModel.created_at, FeishuAttachmentModel.id)
        )
        models = (await self._session.execute(statement)).scalars().all()
        self._tracked_attachments.update({model.id: model for model in models})
        return [self._attachment_to_domain(model) for model in models]

    async def get_attachment_for_update(self, attachment_id: UUID) -> FeishuAttachment | None:
        statement = (
            select(FeishuAttachmentModel)
            .where(FeishuAttachmentModel.id == attachment_id)
            .with_for_update()
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked_attachments[attachment_id] = model
        return self._attachment_to_domain(model)

    async def save_attachment(self, attachment: FeishuAttachment) -> None:
        model = self._tracked_attachments.get(attachment.id)
        if model is None:
            model = await self._session.get(FeishuAttachmentModel, attachment.id)
        if model is None:
            raise RuntimeError(f"FeishuAttachment {attachment.id} is not tracked")
        model.sha256 = attachment.sha256
        model.local_path = attachment.local_path
        model.download_status = attachment.download_status
        model.download_error = attachment.download_error
        model.authorized_for_analysis = attachment.authorized_for_analysis
        model.extraction_status = attachment.extraction_status
        model.extractor_version = attachment.extractor_version
        model.page_count = attachment.page_count
        model.character_count = attachment.character_count
        model.extraction_error_code = attachment.extraction_error_code
        model.updated_at = attachment.updated_at

    async def get_connection(
        self, *, integration_type: str, connection_mode: object
    ) -> IntegrationConnection | None:
        statement = select(IntegrationConnectionModel).where(
            IntegrationConnectionModel.integration_type == integration_type,
            IntegrationConnectionModel.connection_mode == connection_mode,
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._connection_to_domain(model)

    async def save_connection(self, connection: IntegrationConnection) -> None:
        model = await self._session.get(IntegrationConnectionModel, connection.id)
        if model is None:
            model = IntegrationConnectionModel(
                id=connection.id,
                integration_type=connection.integration_type,
                connection_mode=connection.connection_mode,
                status=connection.status,
                created_at=connection.updated_at,
                updated_at=connection.updated_at,
            )
            self._session.add(model)
        model.status = connection.status
        model.last_connected_at = connection.last_connected_at
        model.last_disconnected_at = connection.last_disconnected_at
        model.last_event_at = connection.last_event_at
        model.last_error_code = connection.last_error_code
        model.last_error_message = connection.last_error_message
        model.reconnect_count = connection.reconnect_count
        model.last_reconcile_at = connection.last_reconcile_at
        model.last_reconcile_status = connection.last_reconcile_status
        model.last_reconcile_message = connection.last_reconcile_message
        model.updated_at = connection.updated_at

    @staticmethod
    def _message_hash(value: dict[str, object]) -> str:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _connection_to_domain(model: IntegrationConnectionModel) -> IntegrationConnection:
        return IntegrationConnection(
            id=model.id,
            integration_type=model.integration_type,
            connection_mode=model.connection_mode,
            status=model.status,
            last_connected_at=model.last_connected_at,
            last_disconnected_at=model.last_disconnected_at,
            last_event_at=model.last_event_at,
            last_error_code=model.last_error_code,
            last_error_message=model.last_error_message,
            reconnect_count=model.reconnect_count,
            last_reconcile_at=model.last_reconcile_at,
            last_reconcile_status=model.last_reconcile_status,
            last_reconcile_message=model.last_reconcile_message,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _attachment_to_domain(model: FeishuAttachmentModel) -> FeishuAttachment:
        return FeishuAttachment(
            id=model.id,
            feishu_message_id=model.feishu_message_id,
            message_version_id=model.message_version_id,
            file_key=model.file_key,
            file_name=model.file_name,
            mime_type=model.mime_type,
            size=model.size,
            sha256=model.sha256,
            local_path=model.local_path,
            download_status=model.download_status,
            download_error=model.download_error,
            authorized_for_analysis=model.authorized_for_analysis,
            extraction_status=model.extraction_status,
            extractor_version=model.extractor_version,
            page_count=model.page_count,
            character_count=model.character_count,
            extraction_error_code=model.extraction_error_code,
            created_at=model.created_at,
            updated_at=model.updated_at,
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
            context_snapshot_id=model.context_snapshot_id,
            last_agent_run_id=model.last_agent_run_id,
            analysis_attempts=model.analysis_attempts,
            failure_code=model.failure_code,
            failure_message=model.failure_message,
            version=model.version,
            plain_text=model.plain_text,
            structured_content=model.structured_content,
            attachments=model.attachments,
            content_hash=model.content_hash,
            edited_at=model.edited_at,
            recalled_at=model.recalled_at,
            unsupported_reason=model.unsupported_reason,
        )


class SqlAlchemyAttachmentStorageQuotaRepository:
    LOCK_OPERATION = "attachment_storage_quota"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        *,
        attachment_id: UUID,
        requested_bytes: int,
        total_bytes: int,
        observed_used_bytes: int,
        expires_at: datetime,
    ) -> UUID | None:
        if min(requested_bytes, total_bytes, observed_used_bytes) < 0:
            raise ValueError("Storage quota values cannot be negative.")
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(self.LOCK_OPERATION, 0)))
        )
        now = datetime.now(UTC)
        await self._session.execute(
            update(StorageQuotaReservationModel)
            .where(
                StorageQuotaReservationModel.status == "reserved",
                StorageQuotaReservationModel.expires_at <= now,
            )
            .values(status="expired", updated_at=now)
        )
        stored_value = (
            await self._session.execute(
                select(func.coalesce(func.sum(FeishuAttachmentModel.size), 0)).where(
                    FeishuAttachmentModel.download_status == AttachmentDownloadStatus.DOWNLOADED
                )
            )
        ).scalar_one()
        stored_bytes = int(stored_value or 0)
        reserved_value = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(StorageQuotaReservationModel.requested_bytes), 0)
                ).where(
                    StorageQuotaReservationModel.status == "reserved",
                    StorageQuotaReservationModel.expires_at > now,
                )
            )
        ).scalar_one()
        reserved_bytes = int(reserved_value or 0)
        used_bytes = max(stored_bytes, observed_used_bytes)
        if used_bytes + reserved_bytes + requested_bytes > total_bytes:
            return None
        token = uuid4()
        self._session.add(
            StorageQuotaReservationModel(
                id=uuid4(),
                attachment_id=attachment_id,
                reservation_token=token,
                requested_bytes=requested_bytes,
                status="reserved",
                expires_at=expires_at,
            )
        )
        return token

    async def commit(self, reservation_token: UUID) -> None:
        await self._set_status(reservation_token, status="committed")

    async def release(self, reservation_token: UUID) -> None:
        await self._set_status(reservation_token, status="released")

    async def _set_status(self, reservation_token: UUID, *, status: str) -> None:
        statement = (
            select(StorageQuotaReservationModel)
            .where(
                StorageQuotaReservationModel.reservation_token == reservation_token,
                StorageQuotaReservationModel.status == "reserved",
            )
            .with_for_update()
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            raise RuntimeError("Storage quota reservation is no longer active.")
        model.status = status
        model.updated_at = datetime.now(UTC)


class SqlAlchemyDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tracked_extractions: dict[UUID, DocumentExtractionModel] = {}

    async def find_version(
        self, *, attachment_id: UUID, content_sha256: str
    ) -> DocumentVersion | None:
        statement = select(DocumentVersionModel).where(
            DocumentVersionModel.attachment_id == attachment_id,
            DocumentVersionModel.content_sha256 == content_sha256,
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._version_to_domain(model)

    async def next_version(self, attachment_id: UUID) -> int:
        statement = select(func.coalesce(func.max(DocumentVersionModel.version), 0)).where(
            DocumentVersionModel.attachment_id == attachment_id
        )
        return int((await self._session.execute(statement)).scalar_one()) + 1

    async def add_version(self, version: DocumentVersion) -> None:
        self._session.add(
            DocumentVersionModel(
                id=version.id,
                attachment_id=version.attachment_id,
                version=version.version,
                content_sha256=version.content_sha256,
                file_name=version.file_name,
                mime_type=version.mime_type,
                size=version.size,
                local_path=version.local_path,
                created_at=version.created_at,
            )
        )

    async def add_extraction(self, extraction: DocumentExtraction) -> None:
        model = DocumentExtractionModel(
            id=extraction.id,
            document_version_id=extraction.document_version_id,
            status=extraction.status,
            extractor_version=extraction.extractor_version,
            page_count=extraction.page_count,
            character_count=extraction.character_count,
            error_code=extraction.error_code,
            started_at=extraction.started_at,
            finished_at=extraction.finished_at,
            created_at=extraction.created_at,
        )
        self._tracked_extractions[extraction.id] = model
        self._session.add(model)

    async def find_latest_extraction(self, document_version_id: UUID) -> DocumentExtraction | None:
        statement = (
            select(DocumentExtractionModel)
            .where(DocumentExtractionModel.document_version_id == document_version_id)
            .order_by(
                DocumentExtractionModel.created_at.desc(),
                DocumentExtractionModel.id.desc(),
            )
            .limit(1)
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._extraction_to_domain(model)

    async def get_extraction_for_update(self, extraction_id: UUID) -> DocumentExtraction | None:
        statement = (
            select(DocumentExtractionModel)
            .where(DocumentExtractionModel.id == extraction_id)
            .with_for_update()
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked_extractions[extraction_id] = model
        return self._extraction_to_domain(model)

    async def save_extraction(self, extraction: DocumentExtraction) -> None:
        model = self._tracked_extractions.get(extraction.id)
        if model is None:
            model = await self._session.get(DocumentExtractionModel, extraction.id)
        if model is None:
            raise RuntimeError(f"DocumentExtraction {extraction.id} is not tracked")
        model.status = extraction.status
        model.extractor_version = extraction.extractor_version
        model.page_count = extraction.page_count
        model.character_count = extraction.character_count
        model.error_code = extraction.error_code
        model.finished_at = extraction.finished_at

    async def get_version(self, version_id: UUID) -> DocumentVersion | None:
        model = await self._session.get(DocumentVersionModel, version_id)
        return None if model is None else self._version_to_domain(model)

    async def add_segments(self, segments: Sequence[DocumentSegment]) -> None:
        self._session.add_all(
            [
                DocumentSegmentModel(
                    id=value.id,
                    extraction_id=value.extraction_id,
                    attachment_id=value.attachment_id,
                    page_number=value.page_number,
                    paragraph_number=value.paragraph_number,
                    start_offset=value.start_offset,
                    end_offset=value.end_offset,
                    content=value.content,
                    content_hash=value.content_hash,
                    created_at=value.created_at,
                )
                for value in segments
            ]
        )

    async def list_latest_segments(
        self, attachment_ids: Sequence[UUID]
    ) -> Sequence[DocumentSegment]:
        if not attachment_ids:
            return []
        statement = (
            select(DocumentSegmentModel, DocumentExtractionModel.created_at)
            .join(
                DocumentExtractionModel,
                DocumentExtractionModel.id == DocumentSegmentModel.extraction_id,
            )
            .where(
                DocumentSegmentModel.attachment_id.in_(list(attachment_ids)),
                DocumentExtractionModel.status == DocumentExtractionStatus.SUCCEEDED,
            )
            .order_by(
                DocumentSegmentModel.attachment_id,
                DocumentExtractionModel.created_at.desc(),
                DocumentSegmentModel.paragraph_number,
            )
        )
        rows = (await self._session.execute(statement)).all()
        latest: dict[UUID, UUID] = {}
        segments: list[DocumentSegment] = []
        for model, _created_at in rows:
            extraction_id = latest.setdefault(model.attachment_id, model.extraction_id)
            if model.extraction_id != extraction_id:
                continue
            segments.append(
                DocumentSegment(
                    id=model.id,
                    extraction_id=model.extraction_id,
                    attachment_id=model.attachment_id,
                    page_number=model.page_number,
                    paragraph_number=model.paragraph_number,
                    start_offset=model.start_offset,
                    end_offset=model.end_offset,
                    content=model.content,
                    content_hash=model.content_hash,
                    created_at=model.created_at,
                )
            )
        return segments

    @staticmethod
    def _version_to_domain(model: DocumentVersionModel) -> DocumentVersion:
        return DocumentVersion(
            id=model.id,
            attachment_id=model.attachment_id,
            version=model.version,
            content_sha256=model.content_sha256,
            file_name=model.file_name,
            mime_type=model.mime_type,
            size=model.size,
            local_path=model.local_path,
            created_at=model.created_at,
        )

    @staticmethod
    def _extraction_to_domain(model: DocumentExtractionModel) -> DocumentExtraction:
        return DocumentExtraction(
            id=model.id,
            document_version_id=model.document_version_id,
            status=model.status,
            extractor_version=model.extractor_version,
            page_count=model.page_count,
            character_count=model.character_count,
            error_code=model.error_code,
            started_at=model.started_at,
            finished_at=model.finished_at,
            created_at=model.created_at,
        )


class SqlAlchemyEvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tracked_runs: dict[UUID, EvaluationRunModel] = {}

    async def get_case(
        self, *, suite_key: str, case_key: str, case_version: int
    ) -> EvaluationCase | None:
        statement = select(EvaluationCaseModel).where(
            EvaluationCaseModel.suite_key == suite_key,
            EvaluationCaseModel.case_key == case_key,
            EvaluationCaseModel.case_version == case_version,
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return None if model is None else self._case_to_domain(model)

    async def add_case(self, case: EvaluationCase) -> None:
        self._session.add(
            EvaluationCaseModel(
                id=case.id,
                suite_key=case.suite_key,
                case_key=case.case_key,
                case_version=case.case_version,
                agent_key=case.agent_key,
                input_payload=case.input_payload,
                expected_output=case.expected_output,
                content_hash=case.content_hash,
                data_classification=case.data_classification,
                created_at=case.created_at,
            )
        )

    async def add_run(self, run: EvaluationRun) -> None:
        model = EvaluationRunModel(
            id=run.id,
            suite_key=run.suite_key,
            suite_version=run.suite_version,
            runtime_type=run.runtime_type,
            agent_key=run.agent_key,
            agent_definition_version=run.agent_definition_version,
            status=run.status,
            requested_by=run.requested_by,
            correlation_id=run.correlation_id,
            allow_real_runtime=run.allow_real_runtime,
            started_at=run.started_at,
            finished_at=run.finished_at,
            metrics=run.metrics,
            failure_code=run.failure_code,
            failure_message=run.failure_message,
            created_at=run.created_at,
        )
        self._tracked_runs[run.id] = model
        self._session.add(model)

    async def get_run(self, run_id: UUID) -> EvaluationRun | None:
        model = await self._session.get(EvaluationRunModel, run_id)
        if model is None:
            return None
        self._tracked_runs[run_id] = model
        return self._run_to_domain(model)

    async def get_run_for_update(self, run_id: UUID) -> EvaluationRun | None:
        statement = (
            select(EvaluationRunModel).where(EvaluationRunModel.id == run_id).with_for_update()
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        self._tracked_runs[run_id] = model
        return self._run_to_domain(model)

    async def save_run(self, run: EvaluationRun) -> None:
        model = self._tracked_runs.get(run.id)
        if model is None:
            model = await self._session.get(EvaluationRunModel, run.id)
        if model is None:
            raise RuntimeError(f"Evaluation run {run.id} is not tracked")
        model.status = run.status
        model.finished_at = run.finished_at
        model.metrics = run.metrics
        model.failure_code = run.failure_code
        model.failure_message = run.failure_message

    async def add_result(self, result: EvaluationResult) -> None:
        self._session.add(
            EvaluationResultModel(
                id=result.id,
                evaluation_run_id=result.evaluation_run_id,
                evaluation_case_id=result.evaluation_case_id,
                result_payload=result.result_payload,
                scores=result.scores,
                expected_relevant=result.expected_relevant,
                candidate_created=result.candidate_created,
                schema_first_pass=result.schema_first_pass,
                duration_ms=result.duration_ms,
                retry_count=result.retry_count,
                failure_code=result.failure_code,
                runtime_version=result.runtime_version,
                runtime_execution_id=result.runtime_execution_id,
                created_at=result.created_at,
            )
        )

    async def list_results(self, run_id: UUID) -> Sequence[EvaluationResult]:
        statement = (
            select(EvaluationResultModel)
            .where(EvaluationResultModel.evaluation_run_id == run_id)
            .order_by(EvaluationResultModel.created_at, EvaluationResultModel.id)
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [self._result_to_domain(model) for model in models]

    @staticmethod
    def _case_to_domain(model: EvaluationCaseModel) -> EvaluationCase:
        return EvaluationCase(
            id=model.id,
            suite_key=model.suite_key,
            case_key=model.case_key,
            case_version=model.case_version,
            agent_key=model.agent_key,
            input_payload=model.input_payload,
            expected_output=model.expected_output,
            content_hash=model.content_hash,
            data_classification=model.data_classification,
            created_at=model.created_at,
        )

    @staticmethod
    def _run_to_domain(model: EvaluationRunModel) -> EvaluationRun:
        return EvaluationRun(
            id=model.id,
            suite_key=model.suite_key,
            suite_version=model.suite_version,
            runtime_type=model.runtime_type,
            agent_key=model.agent_key,
            agent_definition_version=model.agent_definition_version,
            status=model.status,
            requested_by=model.requested_by,
            correlation_id=model.correlation_id,
            started_at=model.started_at,
            allow_real_runtime=model.allow_real_runtime,
            finished_at=model.finished_at,
            metrics=model.metrics,
            failure_code=model.failure_code,
            failure_message=model.failure_message,
            created_at=model.created_at,
        )

    @staticmethod
    def _result_to_domain(model: EvaluationResultModel) -> EvaluationResult:
        return EvaluationResult(
            id=model.id,
            evaluation_run_id=model.evaluation_run_id,
            evaluation_case_id=model.evaluation_case_id,
            result_payload=model.result_payload,
            scores=model.scores,
            expected_relevant=model.expected_relevant,
            candidate_created=model.candidate_created,
            schema_first_pass=model.schema_first_pass,
            duration_ms=model.duration_ms,
            retry_count=model.retry_count,
            failure_code=model.failure_code,
            runtime_version=model.runtime_version,
            runtime_execution_id=model.runtime_execution_id,
            created_at=model.created_at,
        )


class SqlAlchemySetupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tracked_checks: dict[UUID, IntegrationCheckRunModel] = {}

    async def get_setting(self, key: str) -> SystemSetting | None:
        model = await self._session.scalar(
            select(SystemSettingModel).where(SystemSettingModel.key == key)
        )
        return None if model is None else self._setting_to_domain(model)

    async def save_setting(self, value: SystemSetting) -> None:
        model = await self._session.scalar(
            select(SystemSettingModel).where(SystemSettingModel.key == value.key)
        )
        if model is None:
            self._session.add(
                SystemSettingModel(
                    id=value.id,
                    key=value.key,
                    value=value.value,
                    value_type=value.value_type,
                    updated_by=value.updated_by,
                    version=value.version,
                    created_at=value.created_at,
                    updated_at=value.updated_at,
                )
            )
            return
        model.value = value.value
        model.value_type = value.value_type
        model.updated_by = value.updated_by
        model.updated_at = value.updated_at
        model.version = value.version

    async def get_credential(
        self, *, provider: str, credential_kind: str
    ) -> IntegrationCredential | None:
        model = await self._session.scalar(
            select(IntegrationCredentialModel).where(
                IntegrationCredentialModel.provider == provider,
                IntegrationCredentialModel.credential_kind == credential_kind,
            )
        )
        return None if model is None else self._credential_to_domain(model)

    async def save_credential(self, value: IntegrationCredential) -> None:
        model = await self._session.scalar(
            select(IntegrationCredentialModel).where(
                IntegrationCredentialModel.provider == value.provider,
                IntegrationCredentialModel.credential_kind == value.credential_kind,
            )
        )
        if model is None:
            self._session.add(
                IntegrationCredentialModel(
                    id=value.id,
                    provider=value.provider,
                    credential_kind=value.credential_kind,
                    secret_ref=value.secret_ref,
                    configured=value.configured,
                    masked_hint=value.masked_hint,
                    last_validated_at=value.last_validated_at,
                    last_validation_status=value.last_validation_status,
                    last_error_code=value.last_error_code,
                    version=value.version,
                    created_at=value.created_at,
                    updated_at=value.updated_at,
                )
            )
            return
        model.secret_ref = value.secret_ref
        model.configured = value.configured
        model.masked_hint = value.masked_hint
        model.last_validated_at = value.last_validated_at
        model.last_validation_status = value.last_validation_status
        model.last_error_code = value.last_error_code
        model.updated_at = value.updated_at
        model.version = value.version

    async def list_scopes(self, *, provider: str) -> Sequence[IntegrationScope]:
        models = (
            (
                await self._session.execute(
                    select(IntegrationScopeModel)
                    .where(IntegrationScopeModel.provider == provider)
                    .order_by(IntegrationScopeModel.display_name, IntegrationScopeModel.id)
                )
            )
            .scalars()
            .all()
        )
        return [self._scope_to_domain(model) for model in models]

    async def add_check(self, value: IntegrationCheckRun) -> None:
        model = IntegrationCheckRunModel(
            id=value.id,
            provider=value.provider,
            check_kind=value.check_kind,
            status=value.status,
            requested_by=value.requested_by,
            correlation_id=value.correlation_id,
            state=value.state,
            error_code=value.error_code,
            detail=value.detail,
            runtime_version=value.runtime_version,
            started_at=value.started_at,
            finished_at=value.finished_at,
            created_at=value.created_at,
        )
        self._tracked_checks[value.id] = model
        self._session.add(model)

    async def get_check(self, check_run_id: UUID) -> IntegrationCheckRun | None:
        model = await self._session.get(IntegrationCheckRunModel, check_run_id)
        if model is None:
            return None
        self._tracked_checks[check_run_id] = model
        return self._check_to_domain(model)

    async def get_check_for_update(self, check_run_id: UUID) -> IntegrationCheckRun | None:
        model = await self._session.scalar(
            select(IntegrationCheckRunModel)
            .where(IntegrationCheckRunModel.id == check_run_id)
            .with_for_update()
        )
        if model is None:
            return None
        self._tracked_checks[check_run_id] = model
        return self._check_to_domain(model)

    async def save_check(self, value: IntegrationCheckRun) -> None:
        model = self._tracked_checks.get(value.id)
        if model is None:
            model = await self._session.get(IntegrationCheckRunModel, value.id)
        if model is None:
            raise RuntimeError(f"Integration check {value.id} is not tracked")
        model.status = value.status
        model.state = value.state
        model.error_code = value.error_code
        model.detail = value.detail
        model.runtime_version = value.runtime_version
        model.started_at = value.started_at
        model.finished_at = value.finished_at

    async def latest_check(self, *, provider: str, check_kind: str) -> IntegrationCheckRun | None:
        model = await self._session.scalar(
            select(IntegrationCheckRunModel)
            .where(
                IntegrationCheckRunModel.provider == provider,
                IntegrationCheckRunModel.check_kind == check_kind,
            )
            .order_by(IntegrationCheckRunModel.created_at.desc())
            .limit(1)
        )
        return None if model is None else self._check_to_domain(model)

    @staticmethod
    def _setting_to_domain(model: SystemSettingModel) -> SystemSetting:
        return SystemSetting(
            id=model.id,
            key=model.key,
            value=model.value,
            value_type=model.value_type,
            updated_by=model.updated_by,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _credential_to_domain(
        model: IntegrationCredentialModel,
    ) -> IntegrationCredential:
        return IntegrationCredential(
            id=model.id,
            provider=model.provider,
            credential_kind=model.credential_kind,
            secret_ref=model.secret_ref,
            configured=model.configured,
            masked_hint=model.masked_hint,
            last_validated_at=model.last_validated_at,
            last_validation_status=model.last_validation_status,
            last_error_code=model.last_error_code,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _scope_to_domain(model: IntegrationScopeModel) -> IntegrationScope:
        return IntegrationScope(
            id=model.id,
            provider=model.provider,
            external_scope_id=model.external_scope_id,
            display_name=model.display_name,
            status=model.status,
            sync_mode=model.sync_mode,
            last_message_at=model.last_message_at,
            last_error_code=model.last_error_code,
            last_error_message=model.last_error_message,
            last_compensated_at=model.last_compensated_at,
            last_compensation_status=model.last_compensation_status,
            approved_by=model.approved_by,
            approved_at=model.approved_at,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _check_to_domain(model: IntegrationCheckRunModel) -> IntegrationCheckRun:
        return IntegrationCheckRun(
            id=model.id,
            provider=model.provider,
            check_kind=model.check_kind,
            status=model.status,
            requested_by=model.requested_by,
            correlation_id=model.correlation_id,
            started_at=model.started_at,
            state=model.state,
            error_code=model.error_code,
            detail=model.detail,
            runtime_version=model.runtime_version,
            finished_at=model.finished_at,
            created_at=model.created_at,
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
                actor_source=event.actor_source,
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

    async def exists_pending(self, *, event_type: str, aggregate_id: UUID) -> bool:
        statement = select(
            exists().where(
                OutboxEventModel.event_type == event_type,
                OutboxEventModel.aggregate_id == aggregate_id,
                OutboxEventModel.published_at.is_(None),
                OutboxEventModel.dead_lettered_at.is_(None),
            )
        )
        return bool((await self._session.execute(statement)).scalar_one())


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
