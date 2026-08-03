from enum import StrEnum


class CandidateStatus(StrEnum):
    PENDING_ANALYSIS = "pending_analysis"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    LINKED = "linked"
    INFORMATION_ONLY = "information_only"
    IGNORED = "ignored"
    REJECTED = "rejected"


class CandidateResolutionAction(StrEnum):
    LINK_EXISTING = "link_existing"
    UPDATE_EXISTING = "update_existing"
    INFORMATION_ONLY = "information_only"
    IGNORE = "ignore"


class MatterUpdateProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ProposalFieldDecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class LegalRelevance(StrEnum):
    RELEVANT = "relevant"
    POSSIBLY_RELEVANT = "possibly_relevant"
    NOT_RELEVANT = "not_relevant"
    UNKNOWN = "unknown"


class MessageRole(StrEnum):
    NEW_REQUEST = "new_request"
    PROGRESS_UPDATE = "progress_update"
    MATERIAL_UPDATE = "material_update"
    DECISION = "decision"
    DEADLINE_CHANGE = "deadline_change"
    CLOSURE_SIGNAL = "closure_signal"
    INFORMATION = "information"


class RecommendedAction(StrEnum):
    CREATE_MATTER = "create_matter"
    LINK_MATTER = "link_matter"
    UPDATE_MATTER = "update_matter"
    ADD_MATERIAL = "add_material"
    REOPEN_MATTER = "reopen_matter"
    INFORMATION_ONLY = "information_only"
    IGNORE = "ignore"
    NEEDS_CONFIRMATION = "needs_confirmation"


class MatterCategory(StrEnum):
    CONTRACT = "contract"
    COPY_REVIEW = "copy_review"
    EMPLOYMENT = "employment"
    DISPUTE = "dispute"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    PLATFORM_RULES = "platform_rules"
    GENERAL_CONSULTATION = "general_consultation"


class MatterLifecycleStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"
    CANCELLED = "cancelled"


class MatterWorkStatus(StrEnum):
    READY = "ready"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    BLOCKED = "blocked"
    DONE = "done"


class LegalRisk(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    PENDING = "pending"


class BusinessImpact(StrEnum):
    COMPANY = "company"
    DEPARTMENT = "department"
    PROJECT = "project"
    GENERAL = "general"


class Confidentiality(StrEnum):
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class WorkItemStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    WAITING = "waiting"
    BLOCKED = "blocked"
    PENDING_REVIEW = "pending_review"
    DONE = "done"
    CANCELLED = "cancelled"


class WorkItemAction(StrEnum):
    START = "start"
    PAUSE = "pause"
    WAIT = "wait"
    BLOCK = "block"
    RESUME = "resume"
    COMPLETE = "complete"
    CANCEL = "cancel"
    REOPEN = "reopen"
    CHANGE_OWNER = "change_owner"
    CHANGE_DEADLINE = "change_deadline"
    CHANGE_NEXT_ACTION = "change_next_action"


class Priority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PrioritySource(StrEnum):
    SYSTEM = "system"
    AGENT_SUGGESTED = "agent_suggested"
    LEGAL_CONFIRMED = "legal_confirmed"


class PriorityConfirmationStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class DeadlineType(StrEnum):
    LEGAL = "legal"
    PLATFORM = "platform"
    CONTRACTUAL = "contractual"
    BUSINESS = "business"
    INTERNAL = "internal"
    REMINDER = "reminder"


class DeadlineSource(StrEnum):
    MESSAGE_EXTRACTED = "message_extracted"
    DOCUMENT_EXTRACTED = "document_extracted"
    SYSTEM_RULE = "system_rule"
    AGENT_SUGGESTED = "agent_suggested"
    LEGAL_CONFIRMED = "legal_confirmed"


class DeadlineStatus(StrEnum):
    ACTIVE = "active"
    SATISFIED = "satisfied"
    MISSED = "missed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class DependencyType(StrEnum):
    FINISH_TO_START = "finish_to_start"
    START_TO_START = "start_to_start"
    EXTERNAL_INPUT = "external_input"
    APPROVAL = "approval"
    MATERIAL = "material"


class DependencyStatus(StrEnum):
    ACTIVE = "active"
    SATISFIED = "satisfied"
    WAIVED = "waived"
    CANCELLED = "cancelled"


class CandidateMatterRelation(StrEnum):
    CREATED = "created"
    LINKED = "linked"
    UPDATED = "updated"


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    NEEDS_MORE_INFORMATION = "needs_more_information"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"


class AgentAttemptStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class MessageAnalysisFailureCode(StrEnum):
    FEISHU_MESSAGE_NOT_FOUND = "FEISHU_MESSAGE_NOT_FOUND"
    FEISHU_MESSAGE_NOT_AUTHORIZED = "FEISHU_MESSAGE_NOT_AUTHORIZED"
    CONTEXT_BUILD_FAILED = "CONTEXT_BUILD_FAILED"
    AGENT_DEFINITION_NOT_FOUND = "AGENT_DEFINITION_NOT_FOUND"
    AGENT_DEFINITION_DISABLED = "AGENT_DEFINITION_DISABLED"
    AGENT_RUNTIME_START_FAILED = "AGENT_RUNTIME_START_FAILED"
    AGENT_RUNTIME_TIMEOUT = "AGENT_RUNTIME_TIMEOUT"
    AGENT_RUNTIME_CANCELLED = "AGENT_RUNTIME_CANCELLED"
    AGENT_LEASE_EXPIRED = "AGENT_LEASE_EXPIRED"
    AGENT_OUTPUT_MISSING = "AGENT_OUTPUT_MISSING"
    AGENT_OUTPUT_INVALID_JSON = "AGENT_OUTPUT_INVALID_JSON"
    AGENT_OUTPUT_SCHEMA_INVALID = "AGENT_OUTPUT_SCHEMA_INVALID"
    AGENT_OUTPUT_BUSINESS_RULE_INVALID = "AGENT_OUTPUT_BUSINESS_RULE_INVALID"
    CANDIDATE_ALREADY_EXISTS = "CANDIDATE_ALREADY_EXISTS"
    UNSUPPORTED_OUTBOX_EVENT = "UNSUPPORTED_OUTBOX_EVENT"


class AgentDefinitionStatus(StrEnum):
    DRAFT = "draft"
    TRIAL = "trial"
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


class AgentRunSourceType(StrEnum):
    FEISHU_MESSAGE = "feishu_message"
    CONTEXT_SNAPSHOT = "context_snapshot"
    ATTACHMENT = "attachment"
    KNOWLEDGE_DOCUMENT = "knowledge_document"
    HISTORICAL_MATTER = "historical_matter"
    APPROVED_EXAMPLE = "approved_example"


class DraftArtifactStatus(StrEnum):
    DRAFT = "draft"
    SUPERSEDED = "superseded"
    APPROVED = "approved"


class ReviewPackageType(StrEnum):
    EXTERNAL_MESSAGE = "external_message"
    INTERNAL_MESSAGE = "internal_message"
    LEGAL_ANALYSIS = "legal_analysis"
    CONTRACT_REVIEW = "contract_review"
    COPY_REVIEW = "copy_review"


class ReviewPackageStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_INFORMATION = "needs_information"
    SUPERSEDED = "superseded"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    APPROVED_WITH_EDITS = "approved_with_edits"
    REJECTED = "rejected"
    NEEDS_INFORMATION = "needs_information"


class CommunicationChannel(StrEnum):
    FEISHU = "feishu"


class CommunicationStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    UNKNOWN = "unknown"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class FeishuEventStatus(StrEnum):
    RECEIVED = "received"
    DUPLICATE = "duplicate"
    PROCESSED = "processed"
    IGNORED = "ignored"
    FAILED = "failed"


class FeishuMessageStatus(StrEnum):
    RECEIVED = "received"
    QUEUED_FOR_ANALYSIS = "queued_for_analysis"
    CONTEXT_PREPARED = "context_prepared"
    AGENT_QUEUED = "agent_queued"
    ANALYSING = "analysing"
    CANDIDATE_CREATED = "candidate_created"
    IGNORED = "ignored"
    ANALYSIS_FAILED = "analysis_failed"
    DEAD_LETTER = "dead_letter"
    UNSUPPORTED = "unsupported"


class IntegrationConnectionMode(StrEnum):
    LONG_CONNECTION = "long_connection"
    WEBHOOK = "webhook"


class IntegrationConnectionStatus(StrEnum):
    DISABLED = "disabled"
    STARTING = "starting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


class AttachmentDownloadStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    FAILED = "failed"
    NOT_REQUESTED = "not_requested"


class DocumentExtractionStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    EXTRACTING = "extracting"
    SUCCEEDED = "succeeded"
    BODY_UNAVAILABLE = "body_unavailable"
    FAILED = "failed"


class EvaluationRuntimeType(StrEnum):
    FAKE = "fake"
    REAL = "real"


class EvaluationRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
