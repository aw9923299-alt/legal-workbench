from enum import StrEnum


class CandidateStatus(StrEnum):
    PENDING_ANALYSIS = "pending_analysis"
    PENDING_REVIEW = "pending_review"
    CONFIRMED_NEW_MATTER = "confirmed_new_matter"
    CONFIRMED_EXISTING_MATTER = "confirmed_existing_matter"
    INFORMATION_ONLY = "information_only"
    IGNORED = "ignored"


class MatterStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"
    CANCELLED = "cancelled"


class WorkItemStatus(StrEnum):
    READY = "ready"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    BLOCKED = "blocked"
    PENDING_REVIEW = "pending_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


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
