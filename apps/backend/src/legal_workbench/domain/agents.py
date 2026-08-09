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
    AgentAttemptStatus,
    AgentDefinitionStatus,
    AgentExecutionPlanStatus,
    AgentPlanStepStatus,
    AgentRunRole,
    AgentRunSourceType,
    AgentRunStatus,
    DraftArtifactStatus,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    InvalidStateTransitionError,
    StaleAgentAttemptError,
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
    execution_plan_id: UUID | None = None
    plan_step_id: UUID | None = None
    parent_run_id: UUID | None = None
    retry_of_run_id: UUID | None = None
    run_role: AgentRunRole = AgentRunRole.STANDALONE
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


@dataclass(slots=True)
class AgentPlanStep:
    id: UUID
    execution_plan_id: UUID
    step_id: str
    sequence: int
    agent_key: str
    objective: str
    depends_on: list[str]
    context_requirements: list[str]
    status: AgentPlanStepStatus = AgentPlanStepStatus.PENDING
    latest_run_id: UUID | None = None
    attempt_count: int = 0
    failure_code: str | None = None
    failure_message: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    def __post_init__(self) -> None:
        if not self.step_id.strip() or not self.agent_key.strip():
            raise DomainValidationError("Agent plan step ID and Agent key are required.")
        if not self.objective.strip():
            raise DomainValidationError("Agent plan step objective is required.")
        if self.sequence < 0 or self.attempt_count < 0:
            raise DomainValidationError("Agent plan step counters cannot be negative.")


@dataclass(slots=True)
class AgentExecutionPlan:
    id: UUID
    matter_id: UUID
    work_item_id: UUID | None
    objective: str
    status: AgentExecutionPlanStatus
    task_types: list[str]
    synthesis_strategy: str
    missing_information: list[str]
    requires_user_input: bool
    correlation_id: str
    idempotency_key: str
    created_by: str
    steps: list[AgentPlanStep] = field(default_factory=list)
    planning_run_id: UUID | None = None
    synthesis_run_id: UUID | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    def __post_init__(self) -> None:
        if not self.objective.strip() or not self.synthesis_strategy.strip():
            raise DomainValidationError(
                "Execution plan objective and synthesis strategy are required."
            )
        if not self.correlation_id.strip() or not self.idempotency_key.strip():
            raise DomainValidationError(
                "Execution plan correlation and idempotency keys are required."
            )

    def validate_steps(self, registered_agent_keys: set[str] | frozenset[str]) -> None:
        if not 1 <= len(self.steps) <= 4:
            raise DomainValidationError("An execution plan must contain one to four steps.")
        if any(step.execution_plan_id != self.id for step in self.steps):
            raise DomainValidationError("Every Agent step must belong to the execution plan.")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise DomainValidationError("Agent execution plan step IDs must be unique.")
        invalid_agents = sorted(
            {step.agent_key for step in self.steps if step.agent_key not in registered_agent_keys}
        )
        if invalid_agents:
            raise DomainValidationError(
                "Execution plan references an unregistered specialist Agent.",
                details={"agentKeys": invalid_agents},
            )
        known = set(step_ids)
        unknown_dependencies = sorted(
            {
                dependency
                for step in self.steps
                for dependency in step.depends_on
                if dependency not in known
            }
        )
        if unknown_dependencies:
            raise DomainValidationError(
                "Execution plan references an unknown dependency.",
                details={"stepIds": unknown_dependencies},
            )
        self._topological_waves()

    def ready_waves(self) -> list[list[AgentPlanStep]]:
        return self._topological_waves()

    def _topological_waves(self) -> list[list[AgentPlanStep]]:
        by_id = {step.step_id: step for step in self.steps}
        remaining = set(by_id)
        completed: set[str] = set()
        waves: list[list[AgentPlanStep]] = []
        while remaining:
            ready = sorted(
                (
                    by_id[step_id]
                    for step_id in remaining
                    if set(by_id[step_id].depends_on) <= completed
                ),
                key=lambda step: (step.sequence, step.step_id),
            )
            if not ready:
                raise DomainValidationError("Agent execution plan cannot contain a cycle.")
            waves.append(ready)
            ready_ids = {step.step_id for step in ready}
            remaining -= ready_ids
            completed |= ready_ids
        return waves


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
