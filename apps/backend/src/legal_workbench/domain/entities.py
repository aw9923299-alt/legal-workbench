from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import ClassVar
from uuid import UUID, uuid4

from legal_workbench.domain.enums import (
    AgentDefinitionStatus,
    AgentRunSourceType,
    AgentRunStatus,
    AttachmentDownloadStatus,
    BusinessImpact,
    CandidateResolutionAction,
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
    IntegrationConnectionMode,
    IntegrationConnectionStatus,
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


class AuthenticatedActorId(str):
    """String-compatible actor identifier carrying its verified identity source."""

    identity_source: str

    def __new__(cls, value: str, *, identity_source: str) -> AuthenticatedActorId:
        instance = super().__new__(cls, value)
        instance.identity_source = identity_source
        return instance


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
    feishu_message_id: UUID | None = None
    requires_manual_review: bool = True
    analysis_payload: dict[str, object] = field(default_factory=dict)
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

    def resolve(
        self,
        *,
        action: CandidateResolutionAction,
        actor_id: str,
        expected_version: int,
    ) -> None:
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
                "Only a pending candidate can be resolved.",
                details={"candidateId": str(self.id), "status": self.status.value},
            )
        self.status = {
            CandidateResolutionAction.LINK_EXISTING: CandidateStatus.LINKED,
            CandidateResolutionAction.UPDATE_EXISTING: CandidateStatus.LINKED,
            CandidateResolutionAction.INFORMATION_ONLY: CandidateStatus.INFORMATION_ONLY,
            CandidateResolutionAction.IGNORE: CandidateStatus.IGNORED,
        }[action]
        self.confirmed_by = actor_id
        self.confirmed_at = utc_now()
        self.version += 1

    def replace_pending_analysis(
        self,
        *,
        context_snapshot_id: UUID,
        legal_relevance: LegalRelevance,
        message_role: MessageRole,
        recommended_action: RecommendedAction,
        confidence: float,
        title_proposal: str | None,
        category_proposals: list[dict[str, object]],
        deadline_proposals: list[dict[str, object]],
        evidence_refs: list[str],
        agent_run_id: UUID,
        requires_manual_review: bool,
        analysis_payload: dict[str, object],
    ) -> None:
        if self.status not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise InvalidStateTransitionError(
                "Only a pending candidate can be replaced by a later AgentRun.",
                details={"candidateId": str(self.id), "status": self.status.value},
            )
        if not 0 <= confidence <= 1:
            raise DomainValidationError("Candidate confidence must be between 0 and 1.")
        self.context_snapshot_id = context_snapshot_id
        self.status = CandidateStatus.PENDING_CONFIRMATION
        self.legal_relevance = legal_relevance
        self.message_role = message_role
        self.recommended_action = recommended_action
        self.confidence = confidence
        self.title_proposal = title_proposal.strip() if title_proposal else None
        self.category_proposals = category_proposals
        self.deadline_proposals = deadline_proposals
        self.evidence_refs = evidence_refs
        self.agent_run_id = agent_run_id
        self.requires_manual_review = requires_manual_review
        self.analysis_payload = analysis_payload
        self.version += 1

    def reject_superseded_analysis(self) -> None:
        if self.status not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise InvalidStateTransitionError(
                "Only a pending candidate can be superseded by a later analysis.",
                details={"candidateId": str(self.id), "status": self.status.value},
            )
        self.status = CandidateStatus.REJECTED
        self.version += 1


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
    source_id: str | None = None
    snapshot_version: int = 1
    attachment_ids: list[str] = field(default_factory=list)
    thread_metadata: dict[str, object] = field(default_factory=dict)
    content: dict[str, object] = field(default_factory=dict)
    builder_version: str = "1.0.0"
    selection_policy_version: str = "thread-v1"
    current_message_version: int = 1
    attachment_version_hash: str = ""
    truncated: bool = False
    truncation_reason: str | None = None
    original_size: int = 0
    included_size: int = 0
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class AgentRunStatusChange:
    id: UUID
    agent_run_id: UUID
    from_status: AgentRunStatus | None
    to_status: AgentRunStatus
    changed_at: datetime
    correlation_id: str
    attempt_number: int
    failure_code: str | None = None
    failure_message: str | None = None


@dataclass(slots=True)
class CandidateRevision:
    id: UUID
    candidate_id: UUID
    revision: int
    agent_run_id: UUID
    analysis_payload: dict[str, object]
    created_at: datetime = field(default_factory=utc_now)
    superseded_at: datetime | None = None
    superseded_by: UUID | None = None


@dataclass(slots=True)
class AgentDefinition:
    id: UUID
    key: str
    name: str
    version: str
    description: str
    status: AgentDefinitionStatus
    prompt_template: str
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    allowed_tools: list[str]
    allowed_knowledge_scopes: list[str]
    timeout_seconds: int
    max_retries: int
    requires_human_review: bool
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.version.strip():
            raise DomainValidationError("Agent key and version are required.")
        if self.timeout_seconds < 1:
            raise DomainValidationError("Agent timeout must be positive.")
        if self.max_retries < 0:
            raise DomainValidationError("Agent retries cannot be negative.")

    def ensure_executable(self) -> None:
        if self.status != AgentDefinitionStatus.ACTIVE:
            raise InvalidStateTransitionError(
                "Only an active AgentDefinition can execute.",
                details={"agentKey": self.key, "status": self.status.value},
            )


@dataclass(slots=True)
class AgentRun:
    id: UUID
    agent_definition_id: UUID
    context_snapshot_id: UUID
    status: AgentRunStatus
    objective: str
    prompt_snapshot: str
    working_directory: str
    attempt_number: int
    max_attempts: int
    correlation_id: str
    created_by: str
    matter_id: UUID | None = None
    work_item_id: UUID | None = None
    feishu_message_id: UUID | None = None
    input_payload: dict[str, object] = field(default_factory=dict)
    output_payload: dict[str, object] = field(default_factory=dict)
    raw_stdout: str | None = None
    raw_stderr: str | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    timeout_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    runtime_version: str | None = None
    agent_definition_version: str = ""
    prompt_version: str = ""
    validation_errors: list[str] = field(default_factory=list)
    repair_attempted: bool = False
    token_usage: dict[str, int] | None = None
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1
    pending_status_changes: list[AgentRunStatusChange] = field(
        default_factory=list, repr=False
    )

    _TRANSITIONS: ClassVar[dict[AgentRunStatus, set[AgentRunStatus]]] = {
        AgentRunStatus.QUEUED: {
            AgentRunStatus.PREPARING,
            AgentRunStatus.CANCELLED,
        },
        AgentRunStatus.PREPARING: {
            AgentRunStatus.RUNNING,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        },
        AgentRunStatus.RUNNING: {
            AgentRunStatus.VALIDATING,
            AgentRunStatus.FAILED,
            AgentRunStatus.TIMED_OUT,
            AgentRunStatus.CANCELLED,
        },
        AgentRunStatus.VALIDATING: {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.NEEDS_MORE_INFORMATION,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        },
        AgentRunStatus.FAILED: {
            AgentRunStatus.QUEUED,
            AgentRunStatus.DEAD_LETTER,
        },
        AgentRunStatus.TIMED_OUT: {
            AgentRunStatus.QUEUED,
            AgentRunStatus.DEAD_LETTER,
        },
        AgentRunStatus.COMPLETED: set(),
        AgentRunStatus.NEEDS_MORE_INFORMATION: set(),
        AgentRunStatus.CANCELLED: set(),
        AgentRunStatus.DEAD_LETTER: set(),
    }
    _TERMINAL: ClassVar[set[AgentRunStatus]] = {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.NEEDS_MORE_INFORMATION,
        AgentRunStatus.CANCELLED,
        AgentRunStatus.DEAD_LETTER,
    }

    def __post_init__(self) -> None:
        if self.attempt_number < 1 or self.max_attempts < self.attempt_number:
            raise DomainValidationError("Agent attempt numbers are invalid.")
        if not self.prompt_snapshot.strip():
            raise DomainValidationError("Agent prompt snapshot is required.")

    def transition_to(self, target: AgentRunStatus, *, now: datetime | None = None) -> None:
        previous_status = self.status
        if target not in self._TRANSITIONS[previous_status]:
            raise InvalidStateTransitionError(
                f"AgentRun cannot transition from {self.status.value} to {target.value}."
            )
        changed_at = now or utc_now()
        require_aware(changed_at, field_name="AgentRun transition time")
        self.status = target
        if target == AgentRunStatus.RUNNING and self.started_at is None:
            self.started_at = changed_at
            self.heartbeat_at = changed_at
        if target in self._TERMINAL or target in {
            AgentRunStatus.FAILED,
            AgentRunStatus.TIMED_OUT,
        }:
            self.finished_at = changed_at
        self.updated_at = changed_at
        self.version += 1
        self.pending_status_changes.append(
            AgentRunStatusChange(
                id=uuid4(),
                agent_run_id=self.id,
                from_status=previous_status,
                to_status=target,
                changed_at=changed_at,
                correlation_id=self.correlation_id,
                attempt_number=self.attempt_number,
                failure_code=self.failure_code,
                failure_message=self.failure_message,
            )
        )

    def drain_status_changes(self) -> list[AgentRunStatusChange]:
        changes = list(self.pending_status_changes)
        self.pending_status_changes.clear()
        return changes

    def heartbeat(self, *, now: datetime | None = None) -> None:
        if self.status not in {AgentRunStatus.PREPARING, AgentRunStatus.RUNNING}:
            raise InvalidStateTransitionError(
                "Heartbeat is allowed only while preparing or running."
            )
        changed_at = now or utc_now()
        require_aware(changed_at, field_name="AgentRun heartbeat")
        self.heartbeat_at = changed_at
        self.updated_at = changed_at
        self.version += 1


@dataclass(frozen=True, slots=True)
class AgentRunSource:
    id: UUID
    agent_run_id: UUID
    source_type: AgentRunSourceType
    source_id: str
    source_version: str | None
    source_hash: str
    display_name: str
    citation_metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class DraftArtifact:
    id: UUID
    agent_run_id: UUID
    artifact_type: str
    title: str
    content: str
    structured_payload: dict[str, object]
    status: DraftArtifactStatus = DraftArtifactStatus.DRAFT
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


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
class IntegrationConnection:
    id: UUID
    integration_type: str
    connection_mode: IntegrationConnectionMode
    status: IntegrationConnectionStatus
    last_connected_at: datetime | None = None
    last_disconnected_at: datetime | None = None
    last_event_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    reconnect_count: int = 0
    last_reconcile_at: datetime | None = None
    last_reconcile_status: str | None = None
    last_reconcile_message: str | None = None
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class FeishuMessageVersion:
    id: UUID
    feishu_message_id: UUID
    event_id: UUID
    revision: int
    raw_payload: dict[str, object]
    content_hash: str
    plain_text: str
    structured_content: dict[str, object]
    attachments: list[dict[str, object]]
    edited_at: datetime | None = None
    recalled_at: datetime | None = None
    is_recalled: bool = False
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class FeishuAttachment:
    id: UUID
    feishu_message_id: UUID
    message_version_id: UUID
    file_key: str
    file_name: str
    mime_type: str | None
    size: int | None
    download_status: AttachmentDownloadStatus
    sha256: str | None = None
    local_path: str | None = None
    download_error: str | None = None
    authorized_for_analysis: bool = False
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


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
    context_snapshot_id: UUID | None = None
    last_agent_run_id: UUID | None = None
    analysis_attempts: int = 0
    failure_code: str | None = None
    failure_message: str | None = None
    version: int = 1
    plain_text: str | None = None
    structured_content: dict[str, object] = field(default_factory=dict)
    attachments: list[dict[str, object]] = field(default_factory=list)
    content_hash: str | None = None
    edited_at: datetime | None = None
    recalled_at: datetime | None = None
    unsupported_reason: str | None = None

    _TRANSITIONS: ClassVar[dict[FeishuMessageStatus, set[FeishuMessageStatus]]] = {
        FeishuMessageStatus.RECEIVED: {FeishuMessageStatus.QUEUED_FOR_ANALYSIS},
        FeishuMessageStatus.QUEUED_FOR_ANALYSIS: {
            FeishuMessageStatus.CONTEXT_PREPARED,
            FeishuMessageStatus.ANALYSIS_FAILED,
            FeishuMessageStatus.DEAD_LETTER,
        },
        FeishuMessageStatus.CONTEXT_PREPARED: {
            FeishuMessageStatus.AGENT_QUEUED,
            FeishuMessageStatus.ANALYSIS_FAILED,
        },
        FeishuMessageStatus.AGENT_QUEUED: {
            FeishuMessageStatus.ANALYSING,
            FeishuMessageStatus.ANALYSIS_FAILED,
        },
        FeishuMessageStatus.ANALYSING: {
            FeishuMessageStatus.CANDIDATE_CREATED,
            FeishuMessageStatus.IGNORED,
            FeishuMessageStatus.ANALYSIS_FAILED,
        },
        FeishuMessageStatus.ANALYSIS_FAILED: {
            FeishuMessageStatus.QUEUED_FOR_ANALYSIS,
            FeishuMessageStatus.DEAD_LETTER,
        },
        FeishuMessageStatus.CANDIDATE_CREATED: {
            FeishuMessageStatus.QUEUED_FOR_ANALYSIS,
        },
        FeishuMessageStatus.IGNORED: {FeishuMessageStatus.QUEUED_FOR_ANALYSIS},
        FeishuMessageStatus.DEAD_LETTER: {FeishuMessageStatus.QUEUED_FOR_ANALYSIS},
    }

    def transition_to(
        self,
        target: FeishuMessageStatus,
        *,
        failure_code: str | None = None,
        failure_message: str | None = None,
    ) -> None:
        if target not in self._TRANSITIONS[self.status]:
            raise InvalidStateTransitionError(
                f"FeishuMessage cannot transition from {self.status.value} to {target.value}."
            )
        if target in {
            FeishuMessageStatus.ANALYSIS_FAILED,
            FeishuMessageStatus.DEAD_LETTER,
        } and (not failure_code or not failure_message):
            raise DomainValidationError("A failure code and failure message are required.")
        self.status = target
        self.failure_code = failure_code
        self.failure_message = failure_message
        if target == FeishuMessageStatus.ANALYSING:
            self.analysis_attempts += 1
        self.version += 1


@dataclass(slots=True)
class AuditEvent:
    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_type: str
    actor_id: str
    payload: dict[str, object]
    correlation_id: str
    actor_source: str = "system"
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.actor_source == "system" and isinstance(self.actor_id, AuthenticatedActorId):
            self.actor_source = self.actor_id.identity_source


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
