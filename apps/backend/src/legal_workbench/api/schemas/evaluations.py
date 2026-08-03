from datetime import datetime
from uuid import UUID

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.domain.enums import EvaluationRunStatus, EvaluationRuntimeType


class RunEvaluationRequest(ApiModel):
    suite_key: str = "message_judgement_v1"
    runtime_type: EvaluationRuntimeType = EvaluationRuntimeType.FAKE
    allow_real_runtime: bool = False


class EvaluationMetricsResponse(ApiModel):
    case_count: int
    legal_relevance_accuracy: float
    category_accuracy: float
    deadline_accuracy: float
    message_role_accuracy: float
    facts_accuracy: float
    fact_citation_accuracy: float
    inference_false_positive_rate: float
    missing_information_accuracy: float
    irrelevant_candidate_false_positive_rate: float
    schema_first_pass_rate: float
    average_latency_ms: float
    failure_rate: float
    retry_rate: float


class EvaluationResultResponse(ApiModel):
    id: UUID
    evaluation_case_id: UUID
    result_payload: dict[str, object]
    scores: dict[str, object]
    expected_relevant: bool
    candidate_created: bool
    schema_first_pass: bool
    duration_ms: int
    retry_count: int
    failure_code: str | None
    runtime_version: str | None
    runtime_execution_id: UUID | None
    created_at: datetime


class EvaluationRunResponse(ApiModel):
    id: UUID
    suite_key: str
    suite_version: int
    runtime_type: EvaluationRuntimeType
    agent_key: str
    agent_definition_version: str
    status: EvaluationRunStatus
    requested_by: str
    correlation_id: str
    allow_real_runtime: bool
    started_at: datetime
    finished_at: datetime | None
    metrics: EvaluationMetricsResponse | None
    failure_code: str | None
    results: list[EvaluationResultResponse]
