from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentRole(StrEnum):
    CORE = "core"
    PROFESSIONAL = "professional"
    SUPPORT = "support"


class AgentDefinitionStatus(StrEnum):
    DRAFT = "draft"
    TRIAL = "trial"
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


class AgentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    role: AgentRole
    description: str
    version: str
    prompt_version: str
    input_schema_version: str
    output_schema_version: str
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_knowledge_scopes: list[str] = Field(default_factory=list)
    allowed_artifact_types: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(ge=1, le=3600)
    max_retries: int = Field(ge=0, le=10)
    concurrency_limit: int = Field(ge=1, le=20)
    requires_human_review: bool = True
    status: AgentDefinitionStatus = AgentDefinitionStatus.DRAFT


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_version: str = "1.0"
    run_id: str
    agent_id: str
    objective: str
    matter_id: str
    matter_version: int = Field(ge=1)
    work_item_id: str | None = None
    context_snapshot_id: str
    confirmed_facts: list[dict[str, Any]] = Field(default_factory=list)
    unconfirmed_facts: list[dict[str, Any]] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    permitted_file_ids: list[str] = Field(default_factory=list)
    requested_outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    idempotency_key: str


class AgentResultStatus(StrEnum):
    COMPLETED = "completed"
    NEEDS_MORE_INFORMATION = "needs_more_information"
    CONFLICT_DETECTED = "conflict_detected"
    OUT_OF_SCOPE = "out_of_scope"
    FAILED = "failed"


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_version: str = "1.0"
    run_id: str
    agent_id: str
    agent_version: str
    status: AgentResultStatus
    executive_summary: str
    findings: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    missing_information: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    draft_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
