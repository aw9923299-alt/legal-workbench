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


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    APPROVED_WITH_EDITS = "approved_with_edits"
    REJECTED = "rejected"
    NEEDS_INFORMATION = "needs_information"


class CommunicationStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SENDING = "sending"
    SENT = "sent"
    UNKNOWN = "unknown"
    FAILED = "failed"
