from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from legal_workbench.domain.enums import (
    AgentAttemptStatus,
    AgentDefinitionStatus,
    AgentExecutionPlanStatus,
    AgentPlanStepStatus,
    AgentRunRole,
    AgentRunSourceType,
    AgentRunStatus,
    AttachmentDownloadStatus,
    AuthorityRole,
    AuthorityStatus,
    AuthorityType,
    BusinessImpact,
    CandidateMatterRelation,
    CandidateStatus,
    CommunicationChannel,
    CommunicationStatus,
    Confidentiality,
    DeadlineSource,
    DeadlineStatus,
    DeadlineType,
    DependencyStatus,
    DependencyType,
    DocumentExtractionStatus,
    DraftArtifactStatus,
    EvaluationRunStatus,
    EvaluationRuntimeType,
    FeishuEventStatus,
    FeishuMessageStatus,
    FeishuTokenRotationPhase,
    FeishuUserAuthorizationStatus,
    IntegrationCheckStatus,
    IntegrationConnectionMode,
    IntegrationConnectionStatus,
    IntegrationIdentityType,
    IntegrationScopeStatus,
    IntegrationScopeType,
    IntegrationSyncMode,
    KnowledgeMetadataStatus,
    LegalRelevance,
    LegalRisk,
    LocalDocumentSourceStatus,
    LocalKnowledgeScanStatus,
    MatterCategory,
    MatterLifecycleStatus,
    MatterUpdateProposalStatus,
    MatterWorkStatus,
    MessageRole,
    Priority,
    PriorityConfirmationStatus,
    PrioritySource,
    RecommendedAction,
    ReviewDecision,
    ReviewPackageStatus,
    ReviewPackageType,
    WorkItemStatus,
)
from legal_workbench.infrastructure.database import Base
from legal_workbench.infrastructure.models.base import (
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionedMixin,
)

JSON_EMPTY_LIST = sql_text("'[]'::jsonb")
JSON_EMPTY_OBJECT = sql_text("'{}'::jsonb")
FALSE_DEFAULT = sql_text("false")


def enum_type(enum_class: type[Any], *, name: str, length: int) -> SqlEnum:
    return SqlEnum(
        enum_class,
        values_callable=lambda values: [item.value for item in values],
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        name=name,
        length=length,
    )


class ContextSnapshotModel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "context_snapshots"
    __table_args__ = (
        Index(
            "ix_context_snapshots_source_hash",
            "source_type",
            "source_id",
            "content_hash",
            unique=True,
        ),
    )

    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    snapshot_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    source_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    message_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    file_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    attachment_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    included_segments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    excluded_segments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    relevant_matter_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    participant_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    permission_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    thread_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    builder_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="1.0.0", server_default="1.0.0"
    )
    selection_policy_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="thread-v1", server_default="thread-v1"
    )
    current_message_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    attachment_version_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    truncation_reason: Mapped[str | None] = mapped_column(Text)
    original_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    included_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    candidates: Mapped[list[MessageCandidateModel]] = relationship(
        back_populates="context_snapshot", cascade="all, delete-orphan"
    )


class MessageCandidateModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "message_candidates"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        Index("ix_message_candidates_status_created_at", "status", "created_at"),
        Index(
            "uq_message_candidates_active_message",
            "feishu_message_id",
            unique=True,
            postgresql_where=sql_text(
                "feishu_message_id IS NOT NULL AND status IN "
                "('pending_analysis', 'pending_confirmation', 'confirmed', 'linked')"
            ),
        ),
    )
    context_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("context_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    feishu_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("feishu_messages.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    status: Mapped[CandidateStatus] = mapped_column(
        enum_type(CandidateStatus, name="candidate_status", length=40), nullable=False
    )
    legal_relevance: Mapped[LegalRelevance] = mapped_column(
        enum_type(LegalRelevance, name="legal_relevance", length=32), nullable=False
    )
    message_role: Mapped[MessageRole] = mapped_column(
        enum_type(MessageRole, name="message_role", length=32), nullable=False
    )
    recommended_action: Mapped[RecommendedAction] = mapped_column(
        enum_type(RecommendedAction, name="recommended_action", length=32), nullable=False
    )
    title_proposal: Mapped[str | None] = mapped_column(String(500))
    category_proposals: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    deadline_proposals: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    related_matter_proposals: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    evidence_refs: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    requires_manual_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sql_text("true")
    )
    analysis_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    confirmed_by: Mapped[str | None] = mapped_column(String(160))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    context_snapshot: Mapped[ContextSnapshotModel] = relationship(back_populates="candidates")
    matter_links: Mapped[list[CandidateMatterLinkModel]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class LegalMatterModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "legal_matters"
    __table_args__ = (
        UniqueConstraint("matter_number"),
        Index("ix_legal_matters_owner_status", "owner_id", "lifecycle_status"),
    )
    matter_number: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    primary_category: Mapped[MatterCategory] = mapped_column(
        enum_type(MatterCategory, name="matter_category", length=40), nullable=False
    )
    secondary_categories: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    lifecycle_status: Mapped[MatterLifecycleStatus] = mapped_column(
        enum_type(MatterLifecycleStatus, name="matter_lifecycle_status", length=24),
        nullable=False,
    )
    work_status: Mapped[MatterWorkStatus] = mapped_column(
        enum_type(MatterWorkStatus, name="matter_work_status", length=24), nullable=False
    )
    owner_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    collaborator_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    requester_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    entity_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    legal_risk: Mapped[LegalRisk] = mapped_column(
        enum_type(LegalRisk, name="legal_risk", length=16), nullable=False
    )
    business_impact: Mapped[BusinessImpact] = mapped_column(
        enum_type(BusinessImpact, name="business_impact", length=20), nullable=False
    )
    priority: Mapped[Priority] = mapped_column(
        enum_type(Priority, name="matter_priority", length=16), nullable=False
    )
    priority_source: Mapped[PrioritySource] = mapped_column(
        enum_type(PrioritySource, name="matter_priority_source", length=24), nullable=False
    )
    target_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_action: Mapped[str | None] = mapped_column(Text)
    confidentiality: Mapped[Confidentiality] = mapped_column(
        enum_type(Confidentiality, name="confidentiality", length=20), nullable=False
    )
    summary: Mapped[str | None] = mapped_column(Text)
    objective: Mapped[str | None] = mapped_column(Text)
    current_stage: Mapped[str | None] = mapped_column(String(160))
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    work_items: Mapped[list[WorkItemModel]] = relationship(
        back_populates="matter",
        cascade="all, delete-orphan",
        order_by="WorkItemModel.sequence_order",
    )
    candidate_links: Mapped[list[CandidateMatterLinkModel]] = relationship(
        back_populates="matter", cascade="all, delete-orphan"
    )


class MatterUpdateProposalModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "matter_update_proposals"
    __table_args__ = (
        Index("ix_matter_update_proposals_status_created", "status", "created_at"),
        Index("ix_matter_update_proposals_matter_status", "matter_id", "status"),
    )

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("message_candidates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    matter_id: Mapped[UUID] = mapped_column(
        ForeignKey("legal_matters.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    base_matter_version: Mapped[int] = mapped_column(Integer, nullable=False)
    proposed_changes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    final_changes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    field_decisions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[MatterUpdateProposalStatus] = mapped_column(
        enum_type(
            MatterUpdateProposalStatus,
            name="matter_update_proposal_status",
            length=24,
        ),
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(160))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)


class WorkItemModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "work_items"
    __table_args__ = (
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0", name="estimated_minutes_positive"
        ),
        Index("ix_work_items_matter_status", "matter_id", "status"),
        Index("ix_work_items_owner_priority", "owner_id", "priority"),
    )
    matter_id: Mapped[UUID] = mapped_column(
        ForeignKey("legal_matters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[WorkItemStatus] = mapped_column(
        enum_type(WorkItemStatus, name="work_item_status", length=24), nullable=False
    )
    owner_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    collaborator_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    priority: Mapped[Priority] = mapped_column(
        enum_type(Priority, name="work_item_priority", length=16), nullable=False
    )
    priority_source: Mapped[PrioritySource] = mapped_column(
        enum_type(PrioritySource, name="priority_source", length=24), nullable=False
    )
    ai_suggested_priority: Mapped[Priority | None] = mapped_column(
        enum_type(Priority, name="ai_suggested_priority", length=16)
    )
    priority_reasons: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    override_reason: Mapped[str | None] = mapped_column(Text)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    next_action: Mapped[str] = mapped_column(Text, nullable=False)
    waiting_party_id: Mapped[str | None] = mapped_column(String(160))
    waiting_reason: Mapped[str | None] = mapped_column(Text)
    waiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_reason: Mapped[str | None] = mapped_column(Text)
    is_blocked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    blocker_reason: Mapped[str | None] = mapped_column(Text)
    blocker_owner_id: Mapped[str | None] = mapped_column(String(160))
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_complete_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    priority_confirmed_by: Mapped[str | None] = mapped_column(String(160))
    priority_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sequence_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    matter: Mapped[LegalMatterModel] = relationship(back_populates="work_items")


class CandidateMatterLinkModel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidate_matter_links"
    __table_args__ = (UniqueConstraint("candidate_id", "matter_id", "relation_type"),)

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("message_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    matter_id: Mapped[UUID] = mapped_column(
        ForeignKey("legal_matters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[CandidateMatterRelation] = mapped_column(
        enum_type(CandidateMatterRelation, name="candidate_matter_relation", length=16),
        nullable=False,
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    confirmed_by: Mapped[str | None] = mapped_column(String(160))

    candidate: Mapped[MessageCandidateModel] = relationship(back_populates="matter_links")
    matter: Mapped[LegalMatterModel] = relationship(back_populates="candidate_links")


class AuditEventModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_aggregate", "aggregate_type", "aggregate_id"),)

    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_source: Mapped[str] = mapped_column(
        String(40), nullable=False, default="system", server_default="system"
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutboxEventModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_pending",
            "occurred_at",
            postgresql_where=sql_text("published_at IS NULL"),
        ),
    )

    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(120))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyRecordModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("operation", "idempotency_key"),)

    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PriorityConfirmationModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "priority_confirmations"
    __table_args__ = (
        Index(
            "ix_priority_confirmations_work_item_created",
            "work_item_id",
            "created_at",
        ),
    )

    work_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proposed_priority: Mapped[Priority] = mapped_column(
        enum_type(Priority, name="proposed_priority", length=16), nullable=False
    )
    confirmed_priority: Mapped[Priority] = mapped_column(
        enum_type(Priority, name="confirmed_priority", length=16), nullable=False
    )
    proposed_complete_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_complete_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reasons: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    override_reason: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[str] = mapped_column(String(160), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[PriorityConfirmationStatus] = mapped_column(
        enum_type(PriorityConfirmationStatus, name="priority_confirmation_status", length=20),
        nullable=False,
    )


class DeadlineModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "deadlines"
    __table_args__ = (
        CheckConstraint(
            "(matter_id IS NOT NULL AND work_item_id IS NULL) OR "
            "(matter_id IS NULL AND work_item_id IS NOT NULL)",
            name="deadline_exactly_one_owner",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="deadline_confidence_range",
        ),
        Index("ix_deadlines_active_due_at", "status", "due_at"),
    )

    matter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("legal_matters.id", ondelete="CASCADE"), nullable=True, index=True
    )
    work_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    deadline_type: Mapped[DeadlineType] = mapped_column(
        enum_type(DeadlineType, name="deadline_type", length=20), nullable=False
    )
    source: Mapped[DeadlineSource] = mapped_column(
        enum_type(DeadlineSource, name="deadline_source", length=32), nullable=False
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    is_hard: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=FALSE_DEFAULT)
    status: Mapped[DeadlineStatus] = mapped_column(
        enum_type(DeadlineStatus, name="deadline_status", length=20), nullable=False
    )
    source_reference: Mapped[str | None] = mapped_column(String(500))
    confidence: Mapped[float | None] = mapped_column(Float)
    reminder_policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    confirmed_by: Mapped[str | None] = mapped_column(String(160))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkItemDependencyModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "work_item_dependencies"
    __table_args__ = (
        CheckConstraint(
            "depends_on_work_item_id IS NULL OR depends_on_work_item_id <> work_item_id",
            name="dependency_not_self",
        ),
        UniqueConstraint(
            "work_item_id",
            "depends_on_work_item_id",
            "dependency_type",
            name="uq_work_item_dependency",
        ),
        Index("ix_work_item_dependencies_active", "work_item_id", "status"),
    )

    work_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    depends_on_work_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_items.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    dependency_type: Mapped[DependencyType] = mapped_column(
        enum_type(DependencyType, name="dependency_type", length=24), nullable=False
    )
    status: Mapped[DependencyStatus] = mapped_column(
        enum_type(DependencyStatus, name="dependency_status", length=20), nullable=False
    )
    external_party_id: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    satisfied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    satisfied_by: Mapped[str | None] = mapped_column(String(160))
    waived_by: Mapped[str | None] = mapped_column(String(160))
    waived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewPackageModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "review_packages"
    __table_args__ = (Index("ix_review_packages_status_created", "status", "created_at"),)

    matter_id: Mapped[UUID] = mapped_column(
        ForeignKey("legal_matters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    package_type: Mapped[ReviewPackageType] = mapped_column(
        enum_type(ReviewPackageType, name="review_package_type", length=24), nullable=False
    )
    status: Mapped[ReviewPackageStatus] = mapped_column(
        enum_type(ReviewPackageStatus, name="review_package_status", length=24), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    background: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_facts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    unconfirmed_facts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    risks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    alternatives: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    grounding_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    proposed_content: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_content_hash: Mapped[str | None] = mapped_column(String(64))


class ReviewRecordModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "review_records"
    __table_args__ = (
        Index(
            "ix_review_records_package_reviewed",
            "review_package_id",
            "reviewed_at",
        ),
    )

    review_package_id: Mapped[UUID] = mapped_column(
        ForeignKey("review_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(String(160), nullable=False)
    decision: Mapped[ReviewDecision] = mapped_column(
        enum_type(ReviewDecision, name="review_decision", length=24), nullable=False
    )
    comments: Mapped[str | None] = mapped_column(Text)
    final_content: Mapped[str | None] = mapped_column(Text)
    final_content_hash: Mapped[str | None] = mapped_column(String(64))
    change_summary: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    reusable_as_example: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CommunicationModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "communications"
    __table_args__ = (
        UniqueConstraint("review_record_id", name="uq_communications_review_record_id"),
        Index("ix_communications_status_created", "status", "created_at"),
    )

    matter_id: Mapped[UUID] = mapped_column(
        ForeignKey("legal_matters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    review_package_id: Mapped[UUID] = mapped_column(
        ForeignKey("review_packages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    review_record_id: Mapped[UUID] = mapped_column(
        ForeignKey("review_records.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel: Mapped[CommunicationChannel] = mapped_column(
        enum_type(CommunicationChannel, name="communication_channel", length=16), nullable=False
    )
    target: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[CommunicationStatus] = mapped_column(
        enum_type(CommunicationStatus, name="communication_status", length=20), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(160))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FeishuEventModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "feishu_events"
    __table_args__ = (
        UniqueConstraint("tenant_key", "event_id", name="uq_feishu_events_tenant_event"),
        Index("ix_feishu_events_status_received", "status", "received_at"),
    )

    event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    tenant_key: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    app_id: Mapped[str | None] = mapped_column(String(160))
    schema_version: Mapped[str | None] = mapped_column(String(24))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[FeishuEventStatus] = mapped_column(
        enum_type(FeishuEventStatus, name="feishu_event_status", length=20), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    source_channel: Mapped[str] = mapped_column(
        String(24), nullable=False, default="app_event", server_default="app_event"
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )


class FeishuMessageModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "feishu_messages"
    __table_args__ = (
        UniqueConstraint("tenant_key", "message_id", name="uq_feishu_messages_tenant_message"),
        Index("ix_feishu_messages_chat_created", "chat_id", "create_time"),
        Index("ix_feishu_messages_status_created", "status", "created_at"),
    )

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("feishu_events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tenant_key: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    message_id: Mapped[str] = mapped_column(String(160), nullable=False)
    chat_id: Mapped[str | None] = mapped_column(String(160), index=True)
    thread_id: Mapped[str | None] = mapped_column(String(160))
    root_id: Mapped[str | None] = mapped_column(String(160))
    parent_id: Mapped[str | None] = mapped_column(String(160))
    sender_id: Mapped[str | None] = mapped_column(String(160), index=True)
    sender_type: Mapped[str | None] = mapped_column(String(40))
    message_type: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    mentions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    create_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    update_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_message: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    plain_text: Mapped[str | None] = mapped_column(Text)
    structured_content: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsupported_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[FeishuMessageStatus] = mapped_column(
        enum_type(FeishuMessageStatus, name="feishu_message_status", length=24), nullable=False
    )
    context_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("context_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    last_agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    analysis_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(Text)
    analysis_disposition: Mapped[str] = mapped_column(
        String(20), nullable=False, default="analyze", server_default="analyze"
    )
    analysis_policy_version: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="legacy-app-event-v1",
        server_default="legacy-app-event-v1",
    )
    analysis_reasons: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    detected_document_links: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    source_channel: Mapped[str] = mapped_column(
        String(24), nullable=False, default="app_event", server_default="app_event"
    )
    source_channels: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: ["app_event"],
        server_default=sql_text("'[\"app_event\"]'::jsonb"),
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )


class IntegrationConnectionModel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint(
            "integration_type",
            "connection_mode",
            name="uq_integration_connections_type_mode",
        ),
    )

    integration_type: Mapped[str] = mapped_column(String(40), nullable=False)
    connection_mode: Mapped[IntegrationConnectionMode] = mapped_column(
        enum_type(IntegrationConnectionMode, name="integration_connection_mode", length=24),
        nullable=False,
    )
    status: Mapped[IntegrationConnectionStatus] = mapped_column(
        enum_type(IntegrationConnectionStatus, name="integration_connection_status", length=24),
        nullable=False,
    )
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    reconnect_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_reconcile_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reconcile_status: Mapped[str | None] = mapped_column(String(40))
    last_reconcile_message: Mapped[str | None] = mapped_column(Text)


class FeishuOAuthAttemptModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "feishu_oauth_attempts"

    state_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    code_verifier_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FeishuUserAuthorizationModel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feishu_user_authorizations"
    __table_args__ = (
        UniqueConstraint("tenant_key", "open_id", name="uq_feishu_user_authorization_identity"),
    )

    open_id: Mapped[str] = mapped_column(String(160), nullable=False)
    union_id: Mapped[str | None] = mapped_column(String(160))
    tenant_key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(240))
    scopes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    access_token_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    refresh_token_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    status: Mapped[FeishuUserAuthorizationStatus] = mapped_column(
        enum_type(
            FeishuUserAuthorizationStatus,
            name="feishu_user_authorization_status",
            length=24,
        ),
        nullable=False,
    )
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    pending_token_version: Mapped[int | None] = mapped_column(Integer)
    pending_token_bundle_ref: Mapped[str | None] = mapped_column(String(120))
    rotation_owner: Mapped[str | None] = mapped_column(String(80))
    rotation_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    rotation_phase: Mapped[FeishuTokenRotationPhase] = mapped_column(
        enum_type(
            FeishuTokenRotationPhase,
            name="feishu_token_rotation_phase",
            length=24,
        ),
        nullable=False,
        default=FeishuTokenRotationPhase.IDLE,
        server_default=FeishuTokenRotationPhase.IDLE.value,
    )
    rotation_request_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    rotation_fence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    rotation_result_written_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    rotation_reauth_reason: Mapped[str | None] = mapped_column(String(100))


class FeishuSyncCheckpointModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "feishu_sync_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "authorization_id",
            "scope_id",
            name="uq_feishu_sync_checkpoint_authorization_scope",
        ),
    )

    authorization_id: Mapped[UUID] = mapped_column(
        ForeignKey("feishu_user_authorizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_id: Mapped[UUID] = mapped_column(
        ForeignKey("integration_scopes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    page_token: Mapped[str | None] = mapped_column(String(400))
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(80))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_fence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FeishuMessageVersionModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "feishu_message_versions"
    __table_args__ = (
        UniqueConstraint(
            "feishu_message_id", "revision", name="uq_feishu_message_versions_revision"
        ),
        Index("ix_feishu_message_versions_message_created", "feishu_message_id", "created_at"),
    )

    feishu_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("feishu_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("feishu_events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    plain_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    structured_content: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_recalled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MessageAttachmentModel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "message_attachments"
    __table_args__ = (
        UniqueConstraint(
            "message_version_id", "file_key", name="uq_message_attachments_version_file"
        ),
        Index("ix_message_attachments_status_created", "download_status", "created_at"),
        Index("ix_message_attachments_extraction_status", "extraction_status", "created_at"),
    )

    feishu_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("feishu_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("feishu_message_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_key: Mapped[str] = mapped_column(String(240), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(160))
    size: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    local_path: Mapped[str | None] = mapped_column(Text)
    download_status: Mapped[AttachmentDownloadStatus] = mapped_column(
        enum_type(AttachmentDownloadStatus, name="attachment_download_status", length=24),
        nullable=False,
    )
    download_error: Mapped[str | None] = mapped_column(Text)
    authorized_for_analysis: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    extraction_status: Mapped[DocumentExtractionStatus] = mapped_column(
        enum_type(
            DocumentExtractionStatus,
            name="message_attachment_extraction_status",
            length=24,
        ),
        nullable=False,
        default=DocumentExtractionStatus.NOT_REQUESTED,
        server_default=DocumentExtractionStatus.NOT_REQUESTED.value,
    )
    extractor_version: Mapped[str | None] = mapped_column(String(80))
    page_count: Mapped[int | None] = mapped_column(Integer)
    character_count: Mapped[int | None] = mapped_column(Integer)
    extraction_error_code: Mapped[str | None] = mapped_column(String(100))


FeishuAttachmentModel = MessageAttachmentModel


class FeishuDocumentModel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feishu_documents"
    __table_args__ = (
        UniqueConstraint(
            "authorization_id",
            "document_token",
            name="uq_feishu_documents_authorization_token",
        ),
        CheckConstraint(
            "document_type IN ('docx','wiki')",
            name="feishu_document_type",
        ),
    )

    authorization_id: Mapped[UUID] = mapped_column(
        ForeignKey("feishu_user_authorizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_token: Mapped[str] = mapped_column(String(200), nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    last_content_hash: Mapped[str | None] = mapped_column(String(64))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))


class FeishuMessageDocumentLinkModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "feishu_message_document_links"
    __table_args__ = (
        UniqueConstraint(
            "feishu_message_id",
            "feishu_document_id",
            name="uq_feishu_message_document_link",
        ),
    )

    feishu_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("feishu_messages.id", ondelete="CASCADE"), nullable=False
    )
    feishu_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("feishu_documents.id", ondelete="CASCADE"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FeishuDocumentSubscriptionModel(
    UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base
):
    __tablename__ = "feishu_document_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "authorization_id",
            "folder_token",
            name="uq_feishu_document_subscription",
        ),
    )

    authorization_id: Mapped[UUID] = mapped_column(
        ForeignKey("feishu_user_authorizations.id", ondelete="CASCADE"), nullable=False
    )
    folder_token: Mapped[str] = mapped_column(String(200), nullable=False)
    recursive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sql_text("true")
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))


class LocalKnowledgeScanModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "local_knowledge_scans"
    __table_args__ = (
        Index("ix_local_knowledge_scans_root_started", "source_root_key", "started_at"),
        Index("ix_local_knowledge_scans_status_started", "status", "started_at"),
    )

    source_root_key: Mapped[str] = mapped_column(String(120), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[LocalKnowledgeScanStatus] = mapped_column(
        enum_type(LocalKnowledgeScanStatus, name="local_knowledge_scan_status", length=20),
        nullable=False,
    )
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    deduplicated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unsupported_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LocalDocumentSourceModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "local_document_sources"
    __table_args__ = (
        UniqueConstraint("source_root_key", "relative_path", name="uq_local_document_source_path"),
        Index("ix_local_document_sources_root_status", "source_root_key", "status"),
    )

    source_root_key: Mapped[str] = mapped_column(String(120), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[LocalDocumentSourceStatus] = mapped_column(
        enum_type(LocalDocumentSourceStatus, name="local_document_source_status", length=20),
        nullable=False,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersionModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(attachment_id, feishu_document_id, local_source_id) = 1",
            name="document_version_exactly_one_source",
        ),
        Index(
            "uq_document_versions_attachment_version",
            "attachment_id",
            "version",
            unique=True,
            postgresql_where=sql_text("attachment_id IS NOT NULL"),
        ),
        Index(
            "uq_document_versions_attachment_sha256",
            "attachment_id",
            "content_sha256",
            unique=True,
            postgresql_where=sql_text("attachment_id IS NOT NULL"),
        ),
        Index(
            "uq_document_versions_feishu_version",
            "feishu_document_id",
            "version",
            unique=True,
            postgresql_where=sql_text("feishu_document_id IS NOT NULL"),
        ),
        Index(
            "uq_document_versions_feishu_sha256",
            "feishu_document_id",
            "content_sha256",
            unique=True,
            postgresql_where=sql_text("feishu_document_id IS NOT NULL"),
        ),
        Index(
            "uq_document_versions_local_version",
            "local_source_id",
            "version",
            unique=True,
            postgresql_where=sql_text("local_source_id IS NOT NULL"),
        ),
        Index(
            "uq_document_versions_local_sha256",
            "local_source_id",
            "content_sha256",
            unique=True,
            postgresql_where=sql_text("local_source_id IS NOT NULL"),
        ),
        Index("ix_document_versions_attachment_created", "attachment_id", "created_at"),
    )

    attachment_id: Mapped[UUID] = mapped_column(
        ForeignKey("message_attachments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    feishu_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("feishu_documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    local_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("local_document_sources.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LocalDocumentObservationModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "local_document_observations"
    __table_args__ = (
        UniqueConstraint("local_source_id", "scan_id", name="uq_local_document_observation_scan"),
        Index("ix_local_document_observations_source_seen", "local_source_id", "observed_at"),
        Index("ix_local_document_observations_sha256", "content_sha256"),
    )

    local_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("local_document_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_id: Mapped[UUID] = mapped_column(
        ForeignKey("local_knowledge_scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    modified_at_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DocumentExtractionModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_extractions"
    __table_args__ = (
        Index(
            "ix_document_extractions_version_created",
            "document_version_id",
            "created_at",
        ),
        Index("ix_document_extractions_status_started", "status", "started_at"),
    )

    document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[DocumentExtractionStatus] = mapped_column(
        enum_type(
            DocumentExtractionStatus,
            name="document_extraction_status",
            length=24,
        ),
        nullable=False,
    )
    extractor_version: Mapped[str] = mapped_column(String(80), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    character_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_code: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DocumentSegmentModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_segments"
    __table_args__ = (
        UniqueConstraint(
            "extraction_id",
            "paragraph_number",
            name="uq_document_segments_extraction_paragraph",
        ),
        Index(
            "ix_document_segments_attachment_order",
            "attachment_id",
            "page_number",
            "paragraph_number",
        ),
        Index(
            "ix_document_segments_feishu_order",
            "feishu_document_id",
            "paragraph_number",
        ),
        Index(
            "ix_document_segments_local_order",
            "local_source_id",
            "paragraph_number",
        ),
        CheckConstraint(
            "num_nonnulls(attachment_id, feishu_document_id, local_source_id) = 1",
            name="document_segment_exactly_one_source",
        ),
    )

    extraction_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_extractions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feishu_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("feishu_documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    attachment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("message_attachments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    local_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("local_document_sources.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    page_number: Mapped[int | None] = mapped_column(Integer)
    paragraph_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeDocumentModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_knowledge_documents_source"),
        Index(
            "ix_knowledge_documents_filters",
            "status",
            "jurisdiction",
            "document_type",
            "source_priority",
        ),
    )

    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    document_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    matter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("legal_matters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    agent_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    matter_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    jurisdiction: Mapped[str] = mapped_column(String(80), nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="active")
    source_priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    internal_precedent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    confidentiality: Mapped[str] = mapped_column(String(24), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(160))
    authority_type: Mapped[AuthorityType] = mapped_column(
        enum_type(AuthorityType, name="authority_type", length=40),
        nullable=False,
        default=AuthorityType.UNKNOWN,
        server_default=AuthorityType.UNKNOWN.value,
    )
    authority_role: Mapped[AuthorityRole | None] = mapped_column(
        enum_type(AuthorityRole, name="authority_role", length=32), nullable=True
    )
    authority_status: Mapped[AuthorityStatus] = mapped_column(
        enum_type(AuthorityStatus, name="authority_status", length=20),
        nullable=False,
        default=AuthorityStatus.UNKNOWN,
        server_default=AuthorityStatus.UNKNOWN.value,
    )
    metadata_status: Mapped[KnowledgeMetadataStatus] = mapped_column(
        enum_type(KnowledgeMetadataStatus, name="knowledge_metadata_status", length=24),
        nullable=False,
        default=KnowledgeMetadataStatus.PENDING_METADATA,
        server_default=KnowledgeMetadataStatus.PENDING_METADATA.value,
    )
    issuer: Mapped[str | None] = mapped_column(String(300))
    document_number: Mapped[str | None] = mapped_column(String(160))
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sql_text("true")
    )


class KnowledgeChunkModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("knowledge_document_id", "sequence", name="uq_knowledge_chunks_sequence"),
        Index("ix_knowledge_chunks_document", "knowledge_document_id", "sequence"),
        Index(
            "ix_knowledge_chunks_trgm",
            "normalized_text",
            postgresql_using="gin",
            postgresql_ops={"normalized_text": "gin_trgm_ops"},
        ),
        Index("ix_knowledge_chunks_fts", "search_vector", postgresql_using="gin"),
    )

    knowledge_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_segment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_segments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    locator: Mapped[str] = mapped_column(String(500), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    estimated_token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    token_estimator: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="utf8-bytes-ceil-div-4-v1",
        server_default="utf8-bytes-ceil-div-4-v1",
    )
    token_count_estimated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sql_text("true")
    )
    search_vector: Mapped[object] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(normalized_text, ''))", persisted=True),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeRetrievalLogModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_retrieval_logs"
    __table_args__ = (
        Index("ix_knowledge_retrieval_logs_run_created", "agent_run_id", "created_at"),
        Index("ix_knowledge_retrieval_logs_correlation", "correlation_id", "created_at"),
    )

    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    selected_chunk_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    component_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    selected_chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    selected_token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    excluded_by_token_budget_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    excluded_duplicate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    budget: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StorageQuotaReservationModel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "storage_quota_reservations"
    __table_args__ = (
        UniqueConstraint("reservation_token", name="uq_storage_quota_reservations_token"),
        Index("ix_storage_quota_reservations_status_expiry", "status", "expires_at"),
    )

    attachment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("message_attachments.id", ondelete="SET NULL"), nullable=True
    )
    reservation_token: Mapped[UUID] = mapped_column(nullable=False)
    requested_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentDefinitionModel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_definitions"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_agent_definitions_key_version"),
        Index("ix_agent_definitions_key_status", "key", "status"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AgentDefinitionStatus] = mapped_column(
        enum_type(AgentDefinitionStatus, name="agent_definition_status", length=20),
        nullable=False,
    )
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    output_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    allowed_tools: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    allowed_knowledge_scopes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sql_text("true")
    )


class AgentExecutionPlanModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "agent_execution_plans"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_agent_execution_plans_idempotency"),
        Index("ix_agent_execution_plans_matter_created", "matter_id", "created_at"),
        Index("ix_agent_execution_plans_status_created", "status", "created_at"),
        Index("ix_agent_execution_plans_correlation", "correlation_id"),
    )

    matter_id: Mapped[UUID] = mapped_column(
        ForeignKey("legal_matters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AgentExecutionPlanStatus] = mapped_column(
        enum_type(AgentExecutionPlanStatus, name="agent_execution_plan_status", length=24),
        nullable=False,
    )
    task_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    synthesis_strategy: Mapped[str] = mapped_column(Text, nullable=False)
    missing_information: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    requires_user_input: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    planning_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    synthesis_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    analysis_jurisdiction: Mapped[str] = mapped_column(
        String(64), nullable=False, default="CN", server_default="CN"
    )
    analysis_effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    historical_as_of: Mapped[date | None] = mapped_column(Date)


class AgentPlanStepModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "agent_plan_steps"
    __table_args__ = (
        UniqueConstraint("execution_plan_id", "step_id", name="uq_agent_plan_steps_step_id"),
        UniqueConstraint("execution_plan_id", "sequence", name="uq_agent_plan_steps_sequence"),
        Index("ix_agent_plan_steps_plan_status", "execution_plan_id", "status"),
    )

    execution_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_execution_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[str] = mapped_column(String(120), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_key: Mapped[str] = mapped_column(String(120), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    depends_on: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    context_requirements: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    status: Mapped[AgentPlanStepStatus] = mapped_column(
        enum_type(AgentPlanStepStatus, name="agent_plan_step_status", length=24),
        nullable=False,
    )
    latest_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    latest_valid_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(Text)


class AgentRunModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_status_created", "status", "created_at"),
        Index("ix_agent_runs_message_created", "feishu_message_id", "created_at"),
        Index("ix_agent_runs_correlation", "correlation_id"),
    )

    agent_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_definitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    matter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("legal_matters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    work_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feishu_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("feishu_messages.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    context_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("context_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_type(AgentRunStatus, name="agent_run_status", length=32), nullable=False
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    output_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    raw_stdout: Mapped[str | None] = mapped_column(Text)
    raw_stderr: Mapped[str | None] = mapped_column(Text)
    prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    working_directory: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(80), index=True)
    failure_message: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    runtime_version: Mapped[str | None] = mapped_column(String(80))
    agent_definition_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="", server_default=""
    )
    prompt_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="", server_default=""
    )
    validation_errors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    repair_attempted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    worker_id: Mapped[str | None] = mapped_column(String(160), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    execution_plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_execution_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    plan_step_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_plan_steps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    retry_of_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    run_role: Mapped[AgentRunRole] = mapped_column(
        enum_type(AgentRunRole, name="agent_run_role", length=24),
        nullable=False,
        default=AgentRunRole.STANDALONE,
        server_default=AgentRunRole.STANDALONE.value,
    )
    dependency_run_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )


class AgentRunAttemptModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "agent_run_attempts"
    __table_args__ = (
        CheckConstraint("attempt_number > 0", name="attempt_number"),
        UniqueConstraint("agent_run_id", "attempt_number", name="uq_agent_run_attempts_number"),
        UniqueConstraint("lease_token", name="uq_agent_run_attempts_lease_token"),
        Index(
            "ix_agent_run_attempts_status_expiry",
            "status",
            "lease_expires_at",
        ),
    )

    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_token: Mapped[UUID] = mapped_column(nullable=False)
    worker_id: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[AgentAttemptStatus] = mapped_column(
        enum_type(AgentAttemptStatus, name="agent_attempt_status", length=20),
        nullable=False,
    )
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(Text)


class AgentRunStatusEventModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "agent_run_status_events"
    __table_args__ = (
        Index("ix_agent_run_status_events_run_changed", "agent_run_id", "changed_at"),
    )

    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[AgentRunStatus | None] = mapped_column(
        enum_type(AgentRunStatus, name="agent_run_from_status", length=32)
    )
    to_status: Mapped[AgentRunStatus] = mapped_column(
        enum_type(AgentRunStatus, name="agent_run_to_status", length=32), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(Text)


class CandidateRevisionModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "candidate_revisions"
    __table_args__ = (
        UniqueConstraint("candidate_id", "revision", name="uq_candidate_revisions_revision"),
        Index("ix_candidate_revisions_candidate_created", "candidate_id", "created_at"),
    )

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("message_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    analysis_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("candidate_revisions.id", ondelete="SET NULL")
    )


class AgentRunSourceModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "agent_run_sources"
    __table_args__ = (
        UniqueConstraint(
            "agent_run_id",
            "source_type",
            "source_id",
            "source_hash",
            name="uq_agent_run_sources_exact_source",
        ),
        Index("ix_agent_run_sources_run", "agent_run_id", "created_at"),
    )

    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[AgentRunSourceType] = mapped_column(
        enum_type(AgentRunSourceType, name="agent_run_source_type", length=32), nullable=False
    )
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(80))
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    citation_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DraftArtifactModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "draft_artifacts"
    __table_args__ = (Index("ix_draft_artifacts_run_status", "agent_run_id", "status"),)

    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    status: Mapped[DraftArtifactStatus] = mapped_column(
        enum_type(DraftArtifactStatus, name="draft_artifact_status", length=20), nullable=False
    )


class OutboxDeadLetterModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "outbox_dead_letters"
    __table_args__ = (Index("ix_outbox_dead_letters_failed_at", "failed_at"),)

    original_event_id: Mapped[UUID] = mapped_column(nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    requeued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requeued_event_id: Mapped[UUID | None] = mapped_column()


class EvaluationCaseModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (
        UniqueConstraint(
            "suite_key",
            "case_key",
            "case_version",
            name="uq_evaluation_cases_identity",
        ),
        CheckConstraint("case_version > 0", name="evaluation_case_version_positive"),
        CheckConstraint(
            "data_classification = 'synthetic_non_sensitive'",
            name="evaluation_case_synthetic_only",
        ),
        Index("ix_evaluation_cases_suite", "suite_key", "case_key"),
    )

    suite_key: Mapped[str] = mapped_column(String(120), nullable=False)
    case_key: Mapped[str] = mapped_column(String(120), nullable=False)
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_key: Mapped[str] = mapped_column(String(80), nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expected_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data_classification: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvaluationRunModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint("suite_version > 0", name="evaluation_suite_version_positive"),
        Index("ix_evaluation_runs_suite_created", "suite_key", "created_at"),
        Index("ix_evaluation_runs_status_created", "status", "created_at"),
    )

    suite_key: Mapped[str] = mapped_column(String(120), nullable=False)
    suite_version: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_type: Mapped[EvaluationRuntimeType] = mapped_column(
        enum_type(EvaluationRuntimeType, name="evaluation_runtime_type", length=16),
        nullable=False,
    )
    agent_key: Mapped[str] = mapped_column(String(80), nullable=False)
    agent_definition_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[EvaluationRunStatus] = mapped_column(
        enum_type(EvaluationRunStatus, name="evaluation_run_status", length=20), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    allow_real_runtime: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvaluationResultModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id",
            "evaluation_case_id",
            name="uq_evaluation_results_run_case",
        ),
        CheckConstraint("duration_ms >= 0", name="evaluation_result_duration_nonnegative"),
        CheckConstraint("retry_count >= 0", name="evaluation_result_retry_nonnegative"),
        Index("ix_evaluation_results_run", "evaluation_run_id", "created_at"),
    )

    evaluation_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False
    )
    evaluation_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluation_cases.id", ondelete="RESTRICT"), nullable=False
    )
    result_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT
    )
    expected_relevant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    candidate_created: Mapped[bool] = mapped_column(Boolean, nullable=False)
    schema_first_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    runtime_version: Mapped[str | None] = mapped_column(String(80))
    runtime_execution_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SystemSettingModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(String(24), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(160), nullable=False)


class IntegrationCredentialModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "integration_credentials"
    __table_args__ = (
        UniqueConstraint("provider", "credential_kind", name="uq_integration_credential"),
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    credential_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    secret_ref: Mapped[str | None] = mapped_column(String(120))
    configured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    masked_hint: Mapped[str | None] = mapped_column(String(40))
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_validation_status: Mapped[str | None] = mapped_column(String(40))
    last_error_code: Mapped[str | None] = mapped_column(String(100))


class IntegrationScopeModel(UuidPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "integration_scopes"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "identity_type",
            "authorization_id",
            "scope_type",
            "external_scope_id",
            name="uq_integration_scope",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_integration_scopes_provider_status", "provider", "status"),
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    external_scope_id: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(240))
    identity_type: Mapped[IntegrationIdentityType] = mapped_column(
        enum_type(IntegrationIdentityType, name="integration_identity_type", length=12),
        nullable=False,
        default=IntegrationIdentityType.APP,
        server_default=IntegrationIdentityType.APP.value,
    )
    scope_type: Mapped[IntegrationScopeType] = mapped_column(
        enum_type(IntegrationScopeType, name="integration_scope_type", length=12),
        nullable=False,
        default=IntegrationScopeType.GROUP,
        server_default=IntegrationScopeType.GROUP.value,
    )
    authorization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("feishu_user_authorizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    backfill_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default="7"
    )
    high_value_legal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    status: Mapped[IntegrationScopeStatus] = mapped_column(
        enum_type(IntegrationScopeStatus, name="integration_scope_status", length=20),
        nullable=False,
    )
    sync_mode: Mapped[IntegrationSyncMode] = mapped_column(
        enum_type(IntegrationSyncMode, name="integration_sync_mode", length=24),
        nullable=False,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    last_compensated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_compensation_status: Mapped[str | None] = mapped_column(String(40))
    approved_by: Mapped[str | None] = mapped_column(String(160))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrationCheckRunModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "integration_check_runs"
    __table_args__ = (
        Index(
            "ix_integration_check_runs_provider_kind_created",
            "provider",
            "check_kind",
            "created_at",
        ),
        Index("ix_integration_check_runs_status", "status", "created_at"),
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    check_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[IntegrationCheckStatus] = mapped_column(
        enum_type(IntegrationCheckStatus, name="integration_check_status", length=20),
        nullable=False,
    )
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(40), nullable=False, server_default="pending")
    error_code: Mapped[str | None] = mapped_column(String(100))
    detail: Mapped[str | None] = mapped_column(Text)
    runtime_version: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
