from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from legal_workbench.domain.common import (
    require_aware,
    utc_now,
)
from legal_workbench.domain.enums import (
    DeadlineSource,
    DeadlineStatus,
    DeadlineType,
    DependencyStatus,
    DependencyType,
    Priority,
    PriorityConfirmationStatus,
    PrioritySource,
    WorkItemAction,
    WorkItemStatus,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityVersionConflictError,
    InvalidStateTransitionError,
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
