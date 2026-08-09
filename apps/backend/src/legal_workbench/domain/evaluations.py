from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from legal_workbench.domain.common import (
    require_aware,
    utc_now,
)
from legal_workbench.domain.enums import (
    EvaluationRunStatus,
    EvaluationRuntimeType,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    InvalidStateTransitionError,
)


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
