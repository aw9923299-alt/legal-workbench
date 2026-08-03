from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import ClassVar
from uuid import UUID, uuid4

from legal_workbench.domain.enums import (
    AgentAttemptStatus,
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
    DocumentExtractionStatus,
    DraftArtifactStatus,
    EvaluationRunStatus,
    EvaluationRuntimeType,
    FeishuEventStatus,
    FeishuMessageStatus,
    IntegrationCheckStatus,
    IntegrationConnectionMode,
    IntegrationConnectionStatus,
    IntegrationScopeStatus,
    IntegrationSyncMode,
    LegalRelevance,
    LegalRisk,
    MatterCategory,
    MatterLifecycleStatus,
    MatterUpdateProposalStatus,
    MatterWorkStatus,
    MessageRole,
    Priority,
    PriorityConfirmationStatus,
    PrioritySource,
    ProposalFieldDecisionType,
    RecommendedAction,
    ReviewDecision,
    ReviewPackageStatus,
    ReviewPackageType,
    WorkItemAction,
    WorkItemStatus,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityVersionConflictError,
    InvalidStateTransitionError,
    StaleAgentAttemptError,
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
    priority: Priority = Priority.MEDIUM
    priority_source: PrioritySource = PrioritySource.SYSTEM
    target_deadline_at: datetime | None = None
    next_action: str | None = None
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

    def apply_confirmed_changes(
        self,
        *,
        changes: dict[str, object],
        actor_id: str,
        expected_version: int,
    ) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError(
                "The legal matter was changed by another operation.",
                details={"expectedVersion": expected_version, "actualVersion": self.version},
            )
        unsupported = set(changes) - {
            "title",
            "category",
            "priority",
            "deadline",
            "owner",
            "currentStatus",
            "nextAction",
        }
        if unsupported:
            raise DomainValidationError(
                "Matter update contains unsupported fields.",
                details={"fields": sorted(unsupported)},
            )
        next_title = self.title
        next_category = self.primary_category
        next_priority = self.priority
        next_priority_source = self.priority_source
        next_deadline = self.target_deadline_at
        next_owner = self.owner_id
        next_status = self.work_status
        next_action = self.next_action
        if "title" in changes:
            next_title = str(changes["title"] or "").strip()
            if not next_title:
                raise DomainValidationError("Matter title is required.")
        try:
            if "category" in changes:
                next_category = MatterCategory(str(changes["category"]))
            if "priority" in changes:
                next_priority = Priority(str(changes["priority"]))
                next_priority_source = PrioritySource.LEGAL_CONFIRMED
            if "currentStatus" in changes:
                next_status = MatterWorkStatus(str(changes["currentStatus"]))
        except ValueError as exc:
            raise DomainValidationError("Matter update contains an invalid enum value.") from exc
        if "deadline" in changes:
            deadline = changes["deadline"]
            if not isinstance(deadline, datetime):
                raise DomainValidationError("Matter deadline must be a datetime.")
            require_aware(deadline, field_name="deadline")
            next_deadline = deadline
        if "owner" in changes:
            next_owner = str(changes["owner"] or "").strip()
            if not next_owner:
                raise DomainValidationError("Matter owner is required.")
        if "nextAction" in changes:
            next_action = str(changes["nextAction"] or "").strip()
            if not next_action:
                raise DomainValidationError("Matter next action is required.")
        if changes:
            self.title = next_title
            self.primary_category = next_category
            self.priority = next_priority
            self.priority_source = next_priority_source
            self.target_deadline_at = next_deadline
            self.owner_id = next_owner
            self.work_status = next_status
            self.next_action = next_action
            self.version += 1


@dataclass(frozen=True, slots=True)
class ProposalFieldDecision:
    field_name: str
    decision: ProposalFieldDecisionType
    final_value: object | None


@dataclass(slots=True)
class MatterUpdateProposal:
    ALLOWED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "title",
            "category",
            "priority",
            "deadline",
            "owner",
            "currentStatus",
            "nextAction",
            "newWorkItems",
        }
    )

    id: UUID
    candidate_id: UUID
    matter_id: UUID
    base_matter_version: int
    proposed_changes: dict[str, dict[str, object]]
    reason: str
    status: MatterUpdateProposalStatus
    created_by: str
    final_changes: dict[str, object] = field(default_factory=dict)
    field_decisions: list[dict[str, object]] = field(default_factory=list)
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        candidate_id: UUID,
        matter_id: UUID,
        base_matter_version: int,
        proposed_changes: dict[str, dict[str, object]],
        reason: str,
        created_by: str,
    ) -> MatterUpdateProposal:
        unsupported = set(proposed_changes) - cls.ALLOWED_FIELDS
        if unsupported:
            raise DomainValidationError(
                "Matter update proposal contains unsupported fields.",
                details={"fields": sorted(unsupported)},
            )
        if not proposed_changes:
            raise DomainValidationError("Matter update proposal requires at least one field.")
        required_value_keys = {
            "currentValue",
            "messageExtractedValue",
            "aiSuggestedValue",
        }
        for field_name, values in proposed_changes.items():
            if not isinstance(values, dict) or set(values) != required_value_keys:
                raise DomainValidationError(
                    "Each proposed field requires current, message-extracted and AI values.",
                    details={"field": field_name},
                )
        normalized_reason = reason.strip()
        normalized_actor = created_by.strip()
        if not normalized_reason or not normalized_actor:
            raise DomainValidationError("Proposal reason and creator are required.")
        return cls(
            id=uuid4(),
            candidate_id=candidate_id,
            matter_id=matter_id,
            base_matter_version=base_matter_version,
            proposed_changes=proposed_changes,
            reason=normalized_reason,
            status=MatterUpdateProposalStatus.PENDING,
            created_by=normalized_actor,
        )

    def review(
        self,
        *,
        decisions: list[ProposalFieldDecision],
        reviewer_id: str,
        rejection_reason: str | None,
        expected_version: int,
    ) -> dict[str, object]:
        if self.version != expected_version:
            raise EntityVersionConflictError(
                "The matter update proposal was changed by another operation.",
                details={"expectedVersion": expected_version, "actualVersion": self.version},
            )
        if self.status != MatterUpdateProposalStatus.PENDING:
            raise InvalidStateTransitionError(
                "Only a pending matter update proposal can be reviewed."
            )
        fields = [item.field_name for item in decisions]
        if len(fields) != len(set(fields)):
            raise DomainValidationError("Each proposal field may be reviewed only once.")
        unsupported = set(fields) - set(self.proposed_changes)
        if unsupported:
            raise DomainValidationError(
                "A decision refers to a field outside this proposal.",
                details={"fields": sorted(unsupported)},
            )
        if decisions and set(fields) != set(self.proposed_changes):
            raise DomainValidationError(
                "Every proposed field requires an explicit review decision.",
                details={"missingFields": sorted(set(self.proposed_changes) - set(fields))},
            )
        approved = {
            item.field_name: item.final_value
            for item in decisions
            if item.decision == ProposalFieldDecisionType.APPROVE
        }
        if any(value is None for value in approved.values()):
            raise DomainValidationError("Approved fields require a legal final value.")
        normalized_rejection = rejection_reason.strip() if rejection_reason else None
        normalized_reviewer = reviewer_id.strip()
        if not normalized_reviewer:
            raise DomainValidationError("Proposal reviewer is required.")
        if not approved:
            if not normalized_rejection:
                raise DomainValidationError("Rejecting a proposal requires a reason.")
            self.status = MatterUpdateProposalStatus.REJECTED
        elif len(approved) == len(self.proposed_changes) and all(
            item.decision == ProposalFieldDecisionType.APPROVE for item in decisions
        ):
            self.status = MatterUpdateProposalStatus.APPROVED
        else:
            self.status = MatterUpdateProposalStatus.PARTIALLY_APPROVED
        self.final_changes = approved
        self.field_decisions = [
            {
                "fieldName": item.field_name,
                "decision": item.decision.value,
                "finalValue": item.final_value,
            }
            for item in decisions
        ]
        self.reviewed_by = normalized_reviewer
        self.reviewed_at = utc_now()
        self.rejection_reason = normalized_rejection
        self.version += 1
        return approved

    def supersede(self, *, expected_version: int) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError("The proposal version is stale.")
        if self.status != MatterUpdateProposalStatus.PENDING:
            raise InvalidStateTransitionError("Only a pending proposal can be superseded.")
        self.status = MatterUpdateProposalStatus.SUPERSEDED
        self.version += 1


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
    paused_reason: str | None = None
    is_blocked: bool = False
    blocker_reason: str | None = None
    blocker_owner_id: str | None = None
    planned_start_at: datetime | None = None
    planned_complete_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
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

    def apply(
        self,
        *,
        action: WorkItemAction,
        actor_id: str,
        reason: str | None,
        expected_version: int,
        open_dependencies: list[WorkItemDependency],
        owner_id: str | None = None,
        deadline: datetime | None = None,
        next_action: str | None = None,
        waiting_party_id: str | None = None,
        blocker_owner_id: str | None = None,
    ) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError(
                "The work item was changed by another operation.",
                details={"expectedVersion": expected_version, "actualVersion": self.version},
            )
        if not actor_id.strip():
            raise DomainValidationError("Work item actor is required.")
        normalized_reason = reason.strip() if reason else None
        if (
            action
            in {
                WorkItemAction.PAUSE,
                WorkItemAction.WAIT,
                WorkItemAction.BLOCK,
                WorkItemAction.CANCEL,
                WorkItemAction.REOPEN,
            }
            and not normalized_reason
        ):
            raise DomainValidationError(f"Work item action {action.value} requires a reason.")

        if action == WorkItemAction.START:
            self._require_status(action, {WorkItemStatus.TODO, WorkItemStatus.PAUSED})
            self._clear_transient_status()
            self.status = WorkItemStatus.IN_PROGRESS
            self.planned_start_at = self.planned_start_at or utc_now()
        elif action == WorkItemAction.PAUSE:
            self._require_status(action, {WorkItemStatus.IN_PROGRESS})
            self._clear_transient_status()
            self.status = WorkItemStatus.PAUSED
            self.paused_reason = normalized_reason
        elif action == WorkItemAction.WAIT:
            self._require_status(action, {WorkItemStatus.TODO, WorkItemStatus.IN_PROGRESS})
            if not open_dependencies:
                raise InvalidStateTransitionError(
                    "A work item cannot wait without an active dependency."
                )
            self._clear_transient_status()
            self.status = WorkItemStatus.WAITING
            self.waiting_reason = normalized_reason
            self.waiting_party_id = (
                waiting_party_id.strip() if waiting_party_id and waiting_party_id.strip() else None
            ) or next(
                (value.external_party_id for value in open_dependencies if value.external_party_id),
                None,
            )
            self.waiting_since = utc_now()
        elif action == WorkItemAction.BLOCK:
            self._require_status(
                action,
                {
                    WorkItemStatus.TODO,
                    WorkItemStatus.IN_PROGRESS,
                    WorkItemStatus.PAUSED,
                    WorkItemStatus.WAITING,
                },
            )
            normalized_blocker_owner = blocker_owner_id.strip() if blocker_owner_id else None
            if not normalized_blocker_owner:
                raise DomainValidationError("Blocking a work item requires a responsible owner.")
            self._clear_transient_status()
            self.status = WorkItemStatus.BLOCKED
            self.is_blocked = True
            self.blocker_reason = normalized_reason
            self.blocker_owner_id = normalized_blocker_owner
        elif action == WorkItemAction.RESUME:
            self._require_status(
                action,
                {WorkItemStatus.PAUSED, WorkItemStatus.WAITING, WorkItemStatus.BLOCKED},
            )
            if self.status == WorkItemStatus.WAITING and open_dependencies:
                raise InvalidStateTransitionError(
                    "Resolve active dependencies before resuming a waiting work item."
                )
            self._clear_transient_status()
            self.status = WorkItemStatus.IN_PROGRESS
        elif action == WorkItemAction.COMPLETE:
            self._require_status(
                action, {WorkItemStatus.IN_PROGRESS, WorkItemStatus.PENDING_REVIEW}
            )
            if open_dependencies:
                raise InvalidStateTransitionError(
                    "A work item with active dependencies cannot be completed."
                )
            self._clear_transient_status()
            self.status = WorkItemStatus.DONE
            self.completed_at = utc_now()
        elif action == WorkItemAction.CANCEL:
            if self.status in {WorkItemStatus.DONE, WorkItemStatus.CANCELLED}:
                raise InvalidStateTransitionError(
                    "A completed or cancelled work item cannot be cancelled."
                )
            self._clear_transient_status()
            self.status = WorkItemStatus.CANCELLED
            self.cancel_reason = normalized_reason
            self.cancelled_at = utc_now()
        elif action == WorkItemAction.REOPEN:
            self._require_status(action, {WorkItemStatus.DONE, WorkItemStatus.CANCELLED})
            self._clear_transient_status()
            self.status = WorkItemStatus.TODO
            self.completed_at = None
            self.cancel_reason = None
            self.cancelled_at = None
        elif action == WorkItemAction.CHANGE_OWNER:
            self._require_editable()
            normalized_owner = owner_id.strip() if owner_id else None
            if not normalized_owner:
                raise DomainValidationError("A new work item owner is required.")
            self.owner_id = normalized_owner
        elif action == WorkItemAction.CHANGE_DEADLINE:
            self._require_editable()
            if deadline is None:
                raise DomainValidationError("A new work item deadline is required.")
            require_aware(deadline, field_name="deadline")
            self.planned_complete_at = deadline
        elif action == WorkItemAction.CHANGE_NEXT_ACTION:
            self._require_editable()
            normalized_action = next_action.strip() if next_action else None
            if not normalized_action:
                raise DomainValidationError("A new next action is required.")
            self.next_action = normalized_action
        else:
            raise DomainValidationError(
                "Unsupported work item action.", details={"action": action.value}
            )
        self.version += 1

    def touch_dependency_change(self, *, expected_version: int) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError(
                "The work item was changed by another operation.",
                details={"expectedVersion": expected_version, "actualVersion": self.version},
            )
        if self.status in {WorkItemStatus.DONE, WorkItemStatus.CANCELLED}:
            raise InvalidStateTransitionError(
                "Dependencies cannot be changed on a terminal work item."
            )
        self.version += 1

    def _require_status(self, action: WorkItemAction, allowed: set[WorkItemStatus]) -> None:
        if self.status not in allowed:
            raise InvalidStateTransitionError(
                f"Work item action {action.value} is not allowed from {self.status.value}.",
                details={
                    "action": action.value,
                    "status": self.status.value,
                    "allowedStatuses": sorted(value.value for value in allowed),
                },
            )

    def _require_editable(self) -> None:
        if self.status in {WorkItemStatus.DONE, WorkItemStatus.CANCELLED}:
            raise InvalidStateTransitionError(
                "A completed or cancelled work item cannot be edited."
            )

    def _clear_transient_status(self) -> None:
        self.paused_reason = None
        self.waiting_party_id = None
        self.waiting_reason = None
        self.waiting_since = None
        self.is_blocked = False
        self.blocker_reason = None
        self.blocker_owner_id = None


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
    satisfied_by: str | None = None
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

    def resolve(self, *, actor_id: str, expected_version: int) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError(
                "The work item dependency was changed by another operation.",
                details={"expectedVersion": expected_version, "actualVersion": self.version},
            )
        if self.status != DependencyStatus.ACTIVE:
            raise InvalidStateTransitionError(
                "Only an active work item dependency can be resolved."
            )
        normalized_actor = actor_id.strip()
        if not normalized_actor:
            raise DomainValidationError("Dependency resolver is required.")
        self.status = DependencyStatus.SATISFIED
        self.satisfied_by = normalized_actor
        self.satisfied_at = utc_now()
        self.version += 1


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
    included_segments: list[dict[str, object]] = field(default_factory=list)
    excluded_segments: list[dict[str, object]] = field(default_factory=list)
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


@dataclass(frozen=True, slots=True)
class AgentAttemptLease:
    run_id: UUID
    attempt_number: int
    lease_token: UUID


@dataclass(slots=True)
class AgentRunAttempt:
    id: UUID
    run_id: UUID
    attempt_number: int
    lease_token: UUID
    worker_id: str
    status: AgentAttemptStatus
    lease_expires_at: datetime
    started_at: datetime
    heartbeat_at: datetime
    finished_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise DomainValidationError("Agent attempt number must be positive.")
        if not self.worker_id.strip():
            raise DomainValidationError("Agent attempt worker ID is required.")
        require_aware(self.lease_expires_at, field_name="Agent attempt lease expiry")
        require_aware(self.started_at, field_name="Agent attempt start time")
        require_aware(self.heartbeat_at, field_name="Agent attempt heartbeat")
        if self.finished_at is not None:
            require_aware(self.finished_at, field_name="Agent attempt finish time")

    @classmethod
    def start(
        cls,
        *,
        run_id: UUID,
        attempt_number: int,
        lease_token: UUID,
        worker_id: str,
        lease_expires_at: datetime,
        now: datetime | None = None,
    ) -> AgentRunAttempt:
        started_at = now or utc_now()
        return cls(
            id=uuid4(),
            run_id=run_id,
            attempt_number=attempt_number,
            lease_token=lease_token,
            worker_id=worker_id,
            status=AgentAttemptStatus.RUNNING,
            lease_expires_at=lease_expires_at,
            started_at=started_at,
            heartbeat_at=started_at,
        )

    @property
    def lease(self) -> AgentAttemptLease:
        return AgentAttemptLease(
            run_id=self.run_id,
            attempt_number=self.attempt_number,
            lease_token=self.lease_token,
        )

    def ensure_current(self, lease: AgentAttemptLease) -> None:
        if self.status != AgentAttemptStatus.RUNNING or lease != self.lease:
            raise StaleAgentAttemptError(
                "The Agent Attempt lease is stale and cannot update this run.",
                details={
                    "runId": str(lease.run_id),
                    "attemptNumber": lease.attempt_number,
                },
            )

    def complete(self, lease: AgentAttemptLease, *, now: datetime | None = None) -> None:
        self.ensure_current(lease)
        finished_at = now or utc_now()
        require_aware(finished_at, field_name="Agent attempt completion time")
        self.status = AgentAttemptStatus.COMPLETED
        self.finished_at = finished_at
        self.lease_expires_at = finished_at

    def heartbeat(
        self,
        lease: AgentAttemptLease,
        *,
        heartbeat_at: datetime,
        lease_expires_at: datetime,
    ) -> None:
        self.ensure_current(lease)
        require_aware(heartbeat_at, field_name="Agent attempt heartbeat")
        require_aware(lease_expires_at, field_name="Agent attempt lease expiry")
        if lease_expires_at <= heartbeat_at:
            raise DomainValidationError("Agent attempt lease expiry must follow its heartbeat.")
        self.heartbeat_at = heartbeat_at
        self.lease_expires_at = lease_expires_at

    def fail(
        self,
        lease: AgentAttemptLease,
        *,
        status: AgentAttemptStatus,
        failure_code: str,
        failure_message: str,
        now: datetime | None = None,
    ) -> None:
        self.ensure_current(lease)
        if status not in {
            AgentAttemptStatus.FAILED,
            AgentAttemptStatus.TIMED_OUT,
            AgentAttemptStatus.CANCELLED,
        }:
            raise DomainValidationError("Agent attempt failure requires a failure terminal status.")
        finished_at = now or utc_now()
        require_aware(finished_at, field_name="Agent attempt failure time")
        self.status = status
        self.finished_at = finished_at
        self.lease_expires_at = finished_at
        self.failure_code = failure_code
        self.failure_message = failure_message

    def expire(self, *, now: datetime | None = None) -> None:
        if self.status != AgentAttemptStatus.RUNNING:
            raise StaleAgentAttemptError(
                "Only a running Agent Attempt can expire.",
                details={"runId": str(self.run_id), "attemptNumber": self.attempt_number},
            )
        finished_at = now or utc_now()
        require_aware(finished_at, field_name="Agent attempt expiry time")
        self.status = AgentAttemptStatus.EXPIRED
        self.finished_at = finished_at
        self.lease_expires_at = finished_at
        self.failure_code = "AGENT_LEASE_EXPIRED"
        self.failure_message = "Agent worker heartbeat lease expired."


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
    pending_status_changes: list[AgentRunStatusChange] = field(default_factory=list, repr=False)

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
class MessageAttachment:
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
    extraction_status: DocumentExtractionStatus = DocumentExtractionStatus.NOT_REQUESTED
    extractor_version: str | None = None
    page_count: int | None = None
    character_count: int | None = None
    extraction_error_code: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


FeishuAttachment = MessageAttachment


@dataclass(frozen=True, slots=True)
class ExtractedSegment:
    page_number: int | None
    paragraph_number: int
    start_offset: int
    end_offset: int
    content: str
    content_hash: str

    def __post_init__(self) -> None:
        if self.paragraph_number < 1:
            raise DomainValidationError("Document paragraph number must be positive.")
        if self.page_number is not None and self.page_number < 1:
            raise DomainValidationError("Document page number must be positive.")
        if self.start_offset < 0 or self.end_offset < self.start_offset:
            raise DomainValidationError("Document segment offsets are invalid.")
        if self.end_offset - self.start_offset != len(self.content):
            raise DomainValidationError("Document segment offsets do not match its content.")
        if text_hash(self.content) != self.content_hash:
            raise DomainValidationError("Document segment content hash is invalid.")


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    status: DocumentExtractionStatus
    segments: tuple[ExtractedSegment, ...]
    page_count: int | None
    character_count: int
    extractor_version: str = "document-text-v1"
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    id: UUID
    attachment_id: UUID
    version: int
    content_sha256: str
    file_name: str
    mime_type: str
    size: int
    local_path: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.version < 1 or self.size < 0:
            raise DomainValidationError("Document version metadata is invalid.")
        if len(self.content_sha256) != 64:
            raise DomainValidationError("Document version SHA-256 is invalid.")


@dataclass(slots=True)
class DocumentExtraction:
    id: UUID
    document_version_id: UUID
    status: DocumentExtractionStatus
    extractor_version: str
    page_count: int | None = None
    character_count: int = 0
    error_code: str | None = None
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)

    def complete(
        self,
        result: ExtractedDocument,
        *,
        now: datetime | None = None,
    ) -> None:
        if self.status != DocumentExtractionStatus.EXTRACTING:
            raise InvalidStateTransitionError("Only an extracting document can complete.")
        if result.status not in {
            DocumentExtractionStatus.SUCCEEDED,
            DocumentExtractionStatus.BODY_UNAVAILABLE,
        }:
            raise DomainValidationError("Document completion result is not successful.")
        self.status = result.status
        self.extractor_version = result.extractor_version
        self.page_count = result.page_count
        self.character_count = result.character_count
        self.error_code = result.error_code
        self.finished_at = now or utc_now()

    def fail(self, error_code: str, *, now: datetime | None = None) -> None:
        if self.status != DocumentExtractionStatus.EXTRACTING:
            raise InvalidStateTransitionError("Only an extracting document can fail.")
        self.status = DocumentExtractionStatus.FAILED
        self.error_code = error_code
        self.finished_at = now or utc_now()


@dataclass(frozen=True, slots=True)
class DocumentSegment:
    id: UUID
    extraction_id: UUID
    attachment_id: UUID
    page_number: int | None
    paragraph_number: int
    start_offset: int
    end_offset: int
    content: str
    content_hash: str
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def from_extracted(
        cls,
        *,
        extraction_id: UUID,
        attachment_id: UUID,
        segment: ExtractedSegment,
    ) -> DocumentSegment:
        return cls(
            id=uuid4(),
            extraction_id=extraction_id,
            attachment_id=attachment_id,
            page_number=segment.page_number,
            paragraph_number=segment.paragraph_number,
            start_offset=segment.start_offset,
            end_offset=segment.end_offset,
            content=segment.content,
            content_hash=segment.content_hash,
        )


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


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    id: UUID
    suite_key: str
    case_key: str
    case_version: int
    agent_key: str
    input_payload: dict[str, object]
    expected_output: dict[str, object]
    content_hash: str
    data_classification: str = "synthetic_non_sensitive"
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.suite_key.strip() or not self.case_key.strip() or not self.agent_key.strip():
            raise DomainValidationError("Evaluation case identity is required.")
        if self.case_version < 1:
            raise DomainValidationError("Evaluation case version must be positive.")
        if len(self.content_hash) != 64:
            raise DomainValidationError("Evaluation case content hash must be SHA-256.")
        if self.data_classification != "synthetic_non_sensitive":
            raise DomainValidationError("Evaluation fixtures must be synthetic and non-sensitive.")


@dataclass(slots=True)
class EvaluationRun:
    id: UUID
    suite_key: str
    suite_version: int
    runtime_type: EvaluationRuntimeType
    agent_key: str
    agent_definition_version: str
    status: EvaluationRunStatus
    requested_by: str
    correlation_id: str
    started_at: datetime
    allow_real_runtime: bool = False
    finished_at: datetime | None = None
    metrics: dict[str, object] = field(default_factory=dict)
    failure_code: str | None = None
    failure_message: str | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.suite_version < 1:
            raise DomainValidationError("Evaluation suite version must be positive.")
        require_aware(self.started_at, field_name="Evaluation run start time")
        if self.finished_at is not None:
            require_aware(self.finished_at, field_name="Evaluation run finish time")
        if self.runtime_type == EvaluationRuntimeType.REAL and not self.allow_real_runtime:
            raise DomainValidationError("Real evaluation runtime requires explicit approval.")

    def complete(self, *, metrics: dict[str, object], now: datetime | None = None) -> None:
        if self.status != EvaluationRunStatus.RUNNING:
            raise InvalidStateTransitionError("Only a running evaluation can complete.")
        self.status = EvaluationRunStatus.COMPLETED
        self.metrics = metrics
        self.finished_at = now or utc_now()

    def fail(
        self,
        *,
        code: str,
        message: str,
        metrics: dict[str, object],
        now: datetime | None = None,
    ) -> None:
        if self.status != EvaluationRunStatus.RUNNING:
            raise InvalidStateTransitionError("Only a running evaluation can fail.")
        self.status = EvaluationRunStatus.FAILED
        self.failure_code = code
        self.failure_message = message
        self.metrics = metrics
        self.finished_at = now or utc_now()


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    id: UUID
    evaluation_run_id: UUID
    evaluation_case_id: UUID
    result_payload: dict[str, object]
    scores: dict[str, object]
    expected_relevant: bool
    candidate_created: bool
    schema_first_pass: bool
    duration_ms: int
    retry_count: int
    failure_code: str | None = None
    runtime_version: str | None = None
    runtime_execution_id: UUID | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.duration_ms < 0 or self.retry_count < 0:
            raise DomainValidationError("Evaluation timing and retry counts cannot be negative.")


@dataclass(slots=True)
class SystemSetting:
    id: UUID
    key: str
    value: object
    value_type: str
    updated_by: str
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(cls, *, key: str, value: object, updated_by: str) -> SystemSetting:
        normalized = key.strip()
        if not normalized or not updated_by.strip():
            raise DomainValidationError("Setting key and actor are required.")
        if isinstance(value, bool):
            value_type = "boolean"
        elif isinstance(value, int | float):
            value_type = "number"
        elif isinstance(value, dict | list):
            value_type = "json"
        else:
            value_type = "string"
        return cls(
            id=uuid4(),
            key=normalized,
            value=value,
            value_type=value_type,
            updated_by=updated_by.strip(),
        )


@dataclass(slots=True)
class IntegrationCredential:
    id: UUID
    provider: str
    credential_kind: str
    secret_ref: str | None
    configured: bool
    masked_hint: str | None = None
    last_validated_at: datetime | None = None
    last_validation_status: str | None = None
    last_error_code: str | None = None
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.credential_kind.strip():
            raise DomainValidationError("Integration credential identity is required.")
        if self.configured and not self.secret_ref:
            raise DomainValidationError("Configured credentials require a secret reference.")


@dataclass(slots=True)
class IntegrationScope:
    id: UUID
    provider: str
    external_scope_id: str
    display_name: str | None
    status: IntegrationScopeStatus = IntegrationScopeStatus.UNAPPROVED
    sync_mode: IntegrationSyncMode = IntegrationSyncMode.DISABLED
    last_message_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_compensated_at: datetime | None = None
    last_compensation_status: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class IntegrationCheckRun:
    id: UUID
    provider: str
    check_kind: str
    status: IntegrationCheckStatus
    requested_by: str
    correlation_id: str
    started_at: datetime
    state: str = "pending"
    error_code: str | None = None
    detail: str | None = None
    runtime_version: str | None = None
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)

    def start(self, *, now: datetime | None = None) -> None:
        if self.status != IntegrationCheckStatus.PENDING:
            raise InvalidStateTransitionError("Only a pending integration check can start.")
        self.status = IntegrationCheckStatus.RUNNING
        self.started_at = now or utc_now()

    def finish(
        self,
        *,
        state: str,
        error_code: str | None,
        detail: str,
        runtime_version: str | None = None,
        now: datetime | None = None,
    ) -> None:
        if self.status not in {IntegrationCheckStatus.PENDING, IntegrationCheckStatus.RUNNING}:
            raise InvalidStateTransitionError("Integration check is already final.")
        self.status = (
            IntegrationCheckStatus.COMPLETED
            if error_code is None
            else IntegrationCheckStatus.FAILED
        )
        self.state = state
        self.error_code = error_code
        self.detail = detail
        self.runtime_version = runtime_version
        self.finished_at = now or utc_now()
