from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from legal_workbench.domain.enums import (
    AgentDefinitionStatus,
    AgentRunSourceType,
    AgentRunStatus,
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
    DraftArtifactStatus,
    FeishuEventStatus,
    FeishuMessageStatus,
    LegalRelevance,
    LegalRisk,
    MatterCategory,
    MatterLifecycleStatus,
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
    is_blocked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=FALSE_DEFAULT
    )
    blocker_reason: Mapped[str | None] = mapped_column(Text)
    blocker_owner_id: Mapped[str | None] = mapped_column(String(160))
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_complete_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
        UniqueConstraint("event_id", name="uq_feishu_events_event_id"),
        Index("ix_feishu_events_status_received", "status", "received_at"),
    )

    event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    tenant_key: Mapped[str | None] = mapped_column(String(160))
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
    tenant_key: Mapped[str | None] = mapped_column(String(160))
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
