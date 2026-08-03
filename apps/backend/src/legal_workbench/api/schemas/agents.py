from datetime import datetime
from uuid import UUID

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.domain.enums import AgentRunSourceType, AgentRunStatus, FeishuMessageStatus


class AgentRunSourceResponse(ApiModel):
    source_type: AgentRunSourceType
    source_id: str
    source_version: str | None
    source_hash: str
    display_name: str
    citation_metadata: dict[str, object]


class AgentRunStatusEventResponse(ApiModel):
    id: UUID
    from_status: AgentRunStatus | None
    to_status: AgentRunStatus
    changed_at: datetime
    correlation_id: str
    attempt_number: int
    failure_code: str | None
    failure_message: str | None


class AgentRunResponse(ApiModel):
    id: UUID
    agent_key: str
    agent_version: str
    feishu_message_id: UUID | None
    context_snapshot_id: UUID
    status: AgentRunStatus
    objective: str
    input_payload: dict[str, object]
    output_payload: dict[str, object] | None
    raw_stdout: str | None
    raw_stderr: str | None
    prompt_snapshot: str
    working_directory: str
    started_at: datetime | None
    heartbeat_at: datetime | None
    finished_at: datetime | None
    timeout_at: datetime | None
    attempt_number: int
    max_attempts: int
    failure_code: str | None
    failure_message: str | None
    runtime_version: str | None
    agent_definition_version: str
    prompt_version: str
    validation_errors: list[str]
    repair_attempted: bool
    token_usage: dict[str, int] | None
    worker_id: str | None
    lease_expires_at: datetime | None
    correlation_id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    version: int
    sources: list[AgentRunSourceResponse]
    status_events: list[AgentRunStatusEventResponse]
    candidate_id: UUID | None


class ContextSnapshotSummaryResponse(ApiModel):
    id: UUID
    snapshot_version: int
    message_ids: list[str]
    attachment_ids: list[str]
    included_segments: list[dict[str, object]]
    excluded_segments: list[dict[str, object]]
    participant_ids: list[str]
    content_hash: str
    truncated: bool
    truncation_reason: str | None
    original_size: int
    included_size: int
    builder_version: str
    selection_policy_version: str
    created_at: datetime


class AgentRunOperationResponse(ApiModel):
    run_id: UUID
    status: AgentRunStatus
    idempotent_replay: bool


class FeishuMessageSourceResponse(ApiModel):
    id: UUID
    message_id: str
    sender_id: str | None
    message_type: str
    content: dict[str, object]
    create_time: datetime | None


class MessageAnalysisResponse(ApiModel):
    message: FeishuMessageSourceResponse
    message_status: FeishuMessageStatus
    context_snapshot: ContextSnapshotSummaryResponse | None
    agent_run: AgentRunResponse | None
    analysis_result: dict[str, object] | None
    candidate_id: UUID | None
    failure_code: str | None
    failure_message: str | None
    can_retry: bool


class MessageAnalysisRequestedResponse(ApiModel):
    message_id: UUID
    message_status: FeishuMessageStatus
    idempotent_replay: bool
