from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar
from uuid import UUID, uuid4

from legal_workbench.domain.common import (
    require_aware,
    utc_now,
)
from legal_workbench.domain.enums import (
    BusinessImpact,
    Confidentiality,
    LegalRisk,
    MatterCategory,
    MatterLifecycleStatus,
    MatterUpdateProposalStatus,
    MatterWorkStatus,
    Priority,
    PrioritySource,
    ProposalFieldDecisionType,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityVersionConflictError,
    InvalidStateTransitionError,
)


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
