from enum import StrEnum


class CandidateStatus(StrEnum):
    PENDING_ANALYSIS = "pending_analysis"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    LINKED = "linked"
    INFORMATION_ONLY = "information_only"
    IGNORED = "ignored"
    REJECTED = "rejected"


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
    WAITING = "waiting"
    BLOCKED = "blocked"
    PENDING_REVIEW = "pending_review"
    DONE = "done"
    CANCELLED = "cancelled"


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
    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    CONFLICT = "conflict"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


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
    ANALYZED = "analyzed"
    IGNORED = "ignored"
    FAILED = "failed"
