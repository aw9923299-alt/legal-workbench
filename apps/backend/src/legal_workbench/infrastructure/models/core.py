from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from legal_workbench.domain.enums import (
    BusinessImpact,
    CandidateMatterRelation,
    CandidateStatus,
    Confidentiality,
    LegalRelevance,
    LegalRisk,
    MatterCategory,
    MatterLifecycleStatus,
    MatterWorkStatus,
    MessageRole,
    Priority,
    PrioritySource,
    RecommendedAction,
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


def enum_type(enum_class: type[Any], *, name: str, length: int) -> SqlEnum[Any]:
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

    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    message_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSON_EMPTY_LIST
    )
    file_ids: Mapped[list[str]] = mapped_column(
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
    )
    context_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("context_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
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
    agent_run_id: Mapped[UUID | None] = mapped_column(nullable=True)
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
