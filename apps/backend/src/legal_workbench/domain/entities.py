from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from legal_workbench.domain.enums import (
    BusinessImpact,
    CandidateStatus,
    CommunicationChannel,
    CommunicationStatus,
    Confidentiality,
    DeadlineSource,
    DeadlineStatus,
    DeadlineType,
    DependencyStatus,
    DependencyType,
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
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityVersionConflictError,
    InvalidStateTransitionError,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def text_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{field_name} must be timezone-aware.")


@dataclass(slots=True)
class MessageCandidate:
    id: UUID
    context_snapshot_id: UUID
    status: CandidateStatus
    legal_relevance: LegalRelevance
    message_role: MessageRole
    recommended_action: RecommendedAction
    confidence: float
    title_proposal: str | None = None
    category_proposals: list[dict[str, object]] = field(default_factory=list)
    deadline_proposals: list[dict[str, object]] = field(default_factory=list)
    related_matter_proposals: list[dict[str, object]] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    agent_run_id: UUID | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise DomainValidationError(
                "Candidate confidence must be between 0 and 1.",
                details={"confidence": self.confidence},
            )

    @classmethod
    def create(
        cls,
        *,
        context_snapshot_id: UUID,
        status: CandidateStatus,
        legal_relevance: LegalRelevance,
        message_role: MessageRole,
        recommended_action: RecommendedAction,
        confidence: float,
        title_proposal: str | None,
        category_proposals: list[dict[str, object]],
        deadline_proposals: list[dict[str, object]],
        related_matter_proposals: list[dict[str, object]],
        evidence_refs: list[str],
        agent_run_id: UUID | None,
    ) -> MessageCandidate:
        if status not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise DomainValidationError(
                "A new message candidate must start in a pending status.",
                details={"status": status.value},
            )
        normalized_title = title_proposal.strip() if title_proposal else None
        return cls(
            id=uuid4(),
            context_snapshot_id=context_snapshot_id,
            status=status,
            legal_relevance=legal_relevance,
            message_role=message_role,
            recommended_action=recommended_action,
            confidence=confidence,
            title_proposal=normalized_title or None,
            category_proposals=category_proposals,
            deadline_proposals=deadline_proposals,
            related_matter_proposals=related_matter_proposals,
            evidence_refs=evidence_refs,
            agent_run_id=agent_run_id,
        )

    def confirm_create_matter(self, *, actor_id: str, expected_version: int) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError(
                "The message candidate was changed by another operation.",
                details={"expectedVersion": expected_version, "actualVersion": self.version},
            )
        if self.status not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise InvalidStateTransitionError(
                "Only a pending candidate can create a legal matter.",
                details={"candidateId": str(self.id), "status": self.status.value},
            )
        if self.legal_relevance not in {
            LegalRelevance.RELEVANT,
            LegalRelevance.POSSIBLY_RELEVANT,
        }:
            raise InvalidStateTransitionError(
                "A non-legal candidate cannot create a legal matter.",
                details={"legalRelevance": self.legal_relevance.value},
            )
        self.status = CandidateStatus.CONFIRMED
        self.confirmed_by = actor_id
        self.confirmed_at = utc_now()


@dataclass(slots=True)
class LegalMatter:
    id: UUID
    matter_number: str
    title: str
    primary_category: MatterCategory
    owner_id: str
    legal_risk: LegalRisk
    business_impact: BusinessImpact
    secondary_categories: list[MatterCategory] = field(default_factory=list)
    lifecycle_status: MatterLifecycleStatus = MatterLifecycleStatus.OPEN
    work_status: MatterWorkStatus = MatterWorkStatus.READY
    collaborator_ids: list[str] = field(default_factory=list)
    requester_ids: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    confidentiality: Confidentiality = Confidentiality.INTERNAL
    summary: str | None = None
    objective: str | None = None
    current_stage: str | None = None
    opened_at: datetime = field(default_factory=utc_now)
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    reopened_at: datetime | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        title: str,
        primary_category: MatterCategory,
        secondary_categories: list[MatterCategory],
        owner_id: str,
        legal_risk: LegalRisk,
        business_impact: BusinessImpact,
        confidentiality: Confidentiality,
        requester_ids: list[str],
        summary: str | None,
        objective: str | None,
    ) -> LegalMatter:
        normalized_title = title.strip()
        normalized_owner = owner_id.strip()
        if not normalized_title:
            raise DomainValidationError("Matter title is required.")
        if not normalized_owner:
            raise DomainValidationError("Matter owner is required.")
        matter_id = uuid4()
        date_part = utc_now().strftime("%Y%m%d")
        unique_secondary_categories = [
            category
            for category in dict.fromkeys(secondary_categories)
            if category != primary_category
        ]
        return cls(
            id=matter_id,
            matter_number=f"LW-{date_part}-{matter_id.hex[:8].upper()}",
            title=normalized_title,
            primary_category=primary_category,
            secondary_categories=unique_secondary_categories,
            owner_id=normalized_owner,
            legal_risk=legal_risk,
            business_impact=business_impact,
            confidentiality=confidentiality,
            requester_ids=list(dict.fromkeys(requester_ids)),
            summary=summary,
            objective=objective,
        )


@dataclass(slots=True)
class WorkItem:
    id: UUID
    matter_id: UUID
    title: str
    owner_id: str
    priority: Priority
    priority_source: PrioritySource
    next_action: str
    status: WorkItemStatus = WorkItemStatus.TODO
    collaborator_ids: list[str] = field(default_factory=list)
    ai_suggested_priority: Priority | None = None
    priority_reasons: list[str] = field(default_factory=list)
    override_reason: str | None = None
    estimated_minutes: int | None = None
    waiting_party_id: str | None = None
    waiting_reason: str | None = None
    waiting_since: datetime | None = None
    is_blocked: bool = False
    blocker_reason: str | None = None
    blocker_owner_id: str | None = None
    planned_start_at: datetime | None = None
    planned_complete_at: datetime | None = None
    completed_at: datetime | None = None
    sequence_order: int = 0
    priority_confirmed_by: str | None = None
    priority_confirmed_at: datetime | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        matter_id: UUID,
        title: str,
        owner_id: str,
        priority: Priority,
        priority_source: PrioritySource,
        next_action: str,
        priority_reasons: list[str],
        ai_suggested_priority: Priority | None = None,
        estimated_minutes: int | None = None,
        planned_complete_at: datetime | None = None,
        sequence_order: int = 0,
    ) -> WorkItem:
        normalized_title = title.strip()
        normalized_owner = owner_id.strip()
        normalized_next_action = next_action.strip()
        if not normalized_title:
            raise DomainValidationError("Work item title is required.")
        if not normalized_owner:
            raise DomainValidationError("Work item owner is required.")
        if not normalized_next_action:
            raise DomainValidationError("Work item next action is required.")
        if estimated_minutes is not None and estimated_minutes <= 0:
            raise DomainValidationError(
                "Estimated minutes must be positive.",
                details={"estimatedMinutes": estimated_minutes},
            )
        if planned_complete_at is not None:
            require_aware(planned_complete_at, field_name="planned_complete_at")
        return cls(
            id=uuid4(),
            matter_id=matter_id,
            title=normalized_title,
            owner_id=normalized_owner,
            priority=priority,
            priority_source=priority_source,
            next_action=normalized_next_action,
            priority_reasons=priority_reasons,
            ai_suggested_priority=ai_suggested_priority,
            estimated_minutes=estimated_minutes,
            planned_complete_at=planned_complete_at,
            sequence_order=sequence_order,
        )

    def confirm_priority(
        self,
        *,
        actor_id: str,
        priority: Priority,
        planned_complete_at: datetime | None,
        reasons: list[str],
        override_reason: str | None,
        expected_version: int,
    ) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError(
                "The work item was changed by another operation.",
                details={"expectedVersion": expected_version, "actualVersion": self.version},
            )
        if self.status in {WorkItemStatus.DONE, WorkItemStatus.CANCELLED}:
            raise InvalidStateTransitionError(
                "A completed or cancelled work item cannot be reprioritized."
            )
        if planned_complete_at is not None:
            require_aware(planned_complete_at, field_name="planned_complete_at")
        self.priority = priority
        self.priority_source = PrioritySource.LEGAL_CONFIRMED
        self.priority_reasons = list(
            dict.fromkeys(reason.strip() for reason in reasons if reason.strip())
        )
        self.override_reason = override_reason.strip() if override_reason else None
        self.planned_complete_at = planned_complete_at
        self.priority_confirmed_by = actor_id
        self.priority_confirmed_at = utc_now()


@dataclass(slots=True)
class PriorityConfirmation:
    id: UUID
    work_item_id: UUID
    proposed_priority: Priority
    confirmed_priority: Priority
    proposed_complete_at: datetime | None
    confirmed_complete_at: datetime | None
    reasons: list[str]
    confirmed_by: str
    status: PriorityConfirmationStatus = PriorityConfirmationStatus.CONFIRMED
    override_reason: str | None = None
    confirmed_at: datetime = field(default_factory=utc_now)
    version: int = 1


@dataclass(slots=True)
class Deadline:
    id: UUID
    deadline_type: DeadlineType
    source: DeadlineSource
    due_at: datetime
    timezone: str
    is_hard: bool
    status: DeadlineStatus = DeadlineStatus.ACTIVE
    matter_id: UUID | None = None
    work_item_id: UUID | None = None
    source_reference: str | None = None
    confidence: float | None = None
    reminder_policy: dict[str, object] = field(default_factory=dict)
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        deadline_type: DeadlineType,
        source: DeadlineSource,
        due_at: datetime,
        timezone: str,
        is_hard: bool,
        matter_id: UUID | None,
        work_item_id: UUID | None,
        source_reference: str | None,
        confidence: float | None,
        reminder_policy: dict[str, object],
        actor_id: str | None,
    ) -> Deadline:
        if (matter_id is None) == (work_item_id is None):
            raise DomainValidationError(
                "A deadline must belong to exactly one matter or work item."
            )
        require_aware(due_at, field_name="due_at")
        if confidence is not None and not 0 <= confidence <= 1:
            raise DomainValidationError("Deadline confidence must be between 0 and 1.")
        normalized_timezone = timezone.strip()
        if not normalized_timezone:
            raise DomainValidationError("Deadline timezone is required.")
        return cls(
            id=uuid4(),
            deadline_type=deadline_type,
            source=source,
            due_at=due_at,
            timezone=normalized_timezone,
            is_hard=is_hard,
            matter_id=matter_id,
            work_item_id=work_item_id,
            source_reference=source_reference,
            confidence=confidence,
            reminder_policy=reminder_policy,
            confirmed_by=actor_id,
            confirmed_at=utc_now() if actor_id else None,
        )


@dataclass(slots=True)
class WorkItemDependency:
    id: UUID
    work_item_id: UUID
    dependency_type: DependencyType
    status: DependencyStatus = DependencyStatus.ACTIVE
    depends_on_work_item_id: UUID | None = None
    external_party_id: str | None = None
    description: str | None = None
    satisfied_at: datetime | None = None
    waived_by: str | None = None
    waived_at: datetime | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        work_item_id: UUID,
        dependency_type: DependencyType,
        depends_on_work_item_id: UUID | None,
        external_party_id: str | None,
        description: str | None,
    ) -> WorkItemDependency:
        if depends_on_work_item_id == work_item_id:
            raise DomainValidationError("A work item cannot depend on itself.")
        if depends_on_work_item_id is None and not (external_party_id or description):
            raise DomainValidationError(
                "A dependency requires a predecessor work item or an external "
                "dependency description."
            )
        return cls(
            id=uuid4(),
            work_item_id=work_item_id,
            dependency_type=dependency_type,
            depends_on_work_item_id=depends_on_work_item_id,
            external_party_id=external_party_id.strip() if external_party_id else None,
            description=description.strip() if description else None,
        )


@dataclass(slots=True)
class ReviewPackage:
    id: UUID
    matter_id: UUID
    package_type: ReviewPackageType
    title: str
    background: str
    confirmed_facts: list[dict[str, object]]
    unconfirmed_facts: list[dict[str, object]]
    reasoning: str
    risks: list[dict[str, object]]
    alternatives: list[dict[str, object]]
    citations: list[dict[str, object]]
    proposed_content: str
    target: dict[str, object]
    created_by: str
    work_item_id: UUID | None = None
    status: ReviewPackageStatus = ReviewPackageStatus.DRAFT
    submitted_at: datetime | None = None
    approved_content_hash: str | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        matter_id: UUID,
        work_item_id: UUID | None,
        package_type: ReviewPackageType,
        title: str,
        background: str,
        confirmed_facts: list[dict[str, object]],
        unconfirmed_facts: list[dict[str, object]],
        reasoning: str,
        risks: list[dict[str, object]],
        alternatives: list[dict[str, object]],
        citations: list[dict[str, object]],
        proposed_content: str,
        target: dict[str, object],
        created_by: str,
    ) -> ReviewPackage:
        if not title.strip() or not background.strip() or not reasoning.strip():
            raise DomainValidationError(
                "Review package title, background and reasoning are required."
            )
        if not proposed_content.strip():
            raise DomainValidationError("Review package proposed content is required.")
        if not target:
            raise DomainValidationError("Review package target is required.")
        if package_type == ReviewPackageType.EXTERNAL_MESSAGE:
            reply_to = str(target.get("replyToMessageId") or "").strip()
            receive_id = str(target.get("receiveId") or "").strip()
            if not reply_to and not receive_id:
                raise DomainValidationError(
                    "An external message requires replyToMessageId or receiveId."
                )
        return cls(
            id=uuid4(),
            matter_id=matter_id,
            work_item_id=work_item_id,
            package_type=package_type,
            title=title.strip(),
            background=background.strip(),
            confirmed_facts=confirmed_facts,
            unconfirmed_facts=unconfirmed_facts,
            reasoning=reasoning.strip(),
            risks=risks,
            alternatives=alternatives,
            citations=citations,
            proposed_content=proposed_content.strip(),
            target=target,
            created_by=created_by,
        )

    def submit(self, *, expected_version: int) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError("The review package was changed by another operation.")
        if self.status != ReviewPackageStatus.DRAFT:
            raise InvalidStateTransitionError("Only a draft review package can be submitted.")
        self.status = ReviewPackageStatus.PENDING_REVIEW
        self.submitted_at = utc_now()

    def apply_review(
        self,
        *,
        decision: ReviewDecision,
        final_content: str | None,
        expected_version: int,
    ) -> str | None:
        if self.version != expected_version:
            raise EntityVersionConflictError("The review package was changed by another operation.")
        if self.status != ReviewPackageStatus.PENDING_REVIEW:
            raise InvalidStateTransitionError("Only a pending review package can be reviewed.")
        approved_content: str | None = None
        if decision in {ReviewDecision.APPROVED, ReviewDecision.APPROVED_WITH_EDITS}:
            approved_content = (final_content or self.proposed_content).strip()
            if not approved_content:
                raise DomainValidationError("Approved content cannot be empty.")
            self.status = ReviewPackageStatus.APPROVED
            self.approved_content_hash = text_hash(approved_content)
        elif decision == ReviewDecision.REJECTED:
            self.status = ReviewPackageStatus.REJECTED
        else:
            self.status = ReviewPackageStatus.NEEDS_INFORMATION
        return approved_content


@dataclass(slots=True)
class ReviewRecord:
    id: UUID
    review_package_id: UUID
    reviewer_id: str
    decision: ReviewDecision
    comments: str | None
    final_content: str | None
    final_content_hash: str | None
    change_summary: list[dict[str, object]]
    reusable_as_example: bool
    reviewed_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Communication:
    id: UUID
    matter_id: UUID
    review_package_id: UUID
    review_record_id: UUID
    channel: CommunicationChannel
    target: dict[str, object]
    content: str
    content_hash: str
    status: CommunicationStatus
    requested_by: str
    correlation_id: str
    work_item_id: UUID | None = None
    external_message_id: str | None = None
    attempts: int = 0
    last_error: str | None = None
    queued_at: datetime | None = None
    sent_at: datetime | None = None
    version: int = 1

    @classmethod
    def create_from_approved_review(
        cls,
        *,
        package: ReviewPackage,
        record: ReviewRecord,
        actor_id: str,
        correlation_id: str,
    ) -> Communication:
        if package.status != ReviewPackageStatus.APPROVED:
            raise InvalidStateTransitionError("Only an approved review package can be sent.")
        if record.decision not in {
            ReviewDecision.APPROVED,
            ReviewDecision.APPROVED_WITH_EDITS,
        }:
            raise InvalidStateTransitionError("The latest review record does not approve sending.")
        content = (record.final_content or package.proposed_content).strip()
        content_digest = text_hash(content)
        if package.approved_content_hash != content_digest:
            raise InvalidStateTransitionError(
                "The message content no longer matches the approved review version."
            )
        return cls(
            id=uuid4(),
            matter_id=package.matter_id,
            work_item_id=package.work_item_id,
            review_package_id=package.id,
            review_record_id=record.id,
            channel=CommunicationChannel.FEISHU,
            target=package.target,
            content=content,
            content_hash=content_digest,
            status=CommunicationStatus.QUEUED,
            requested_by=actor_id,
            correlation_id=correlation_id,
            queued_at=utc_now(),
        )


@dataclass(slots=True)
class ContextSnapshot:
    id: UUID
    source_type: str
    source_ids: list[str]
    message_ids: list[str]
    file_ids: list[str]
    relevant_matter_ids: list[str]
    participant_ids: list[str]
    permission_snapshot: dict[str, object]
    generated_at: datetime
    content_hash: str


@dataclass(slots=True)
class FeishuRawEvent:
    id: UUID
    event_id: str
    event_type: str
    tenant_key: str | None
    app_id: str | None
    schema_version: str | None
    raw_payload: dict[str, object]
    payload_hash: str
    status: FeishuEventStatus = FeishuEventStatus.RECEIVED
    received_at: datetime = field(default_factory=utc_now)
    processed_at: datetime | None = None
    last_error: str | None = None


@dataclass(slots=True)
class FeishuMessage:
    id: UUID
    event_id: UUID
    tenant_key: str | None
    message_id: str
    chat_id: str | None
    thread_id: str | None
    root_id: str | None
    parent_id: str | None
    sender_id: str | None
    sender_type: str | None
    message_type: str
    content: dict[str, object]
    mentions: list[dict[str, object]]
    create_time: datetime | None
    update_time: datetime | None
    raw_message: dict[str, object]
    status: FeishuMessageStatus = FeishuMessageStatus.RECEIVED


@dataclass(slots=True)
class AuditEvent:
    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_type: str
    actor_id: str
    payload: dict[str, object]
    correlation_id: str
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class OutboxEvent:
    id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, object]
    correlation_id: str
    occurred_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class IdempotencyRecord:
    id: UUID
    operation: str
    idempotency_key: str
    request_hash: str
    response_payload: dict[str, object]
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
