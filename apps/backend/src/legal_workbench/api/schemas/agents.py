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
    correlation_id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    version: int
    sources: list[AgentRunSourceResponse]


class ContextSnapshotSummaryResponse(ApiModel):
    id: UUID
    snapshot_version: int
    message_ids: list[str]
    attachment_ids: list[str]
    participant_ids: list[str]
    content_hash: str
    truncated: bool
    created_at: datetime


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
