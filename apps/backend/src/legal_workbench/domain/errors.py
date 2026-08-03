from typing import Any


class DomainError(Exception):
    code = "DOMAIN_ERROR"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DomainValidationError(DomainError):
    code = "DOMAIN_VALIDATION_ERROR"


class EntityNotFoundError(DomainError):
    code = "ENTITY_NOT_FOUND"


class EntityVersionConflictError(DomainError):
    code = "ENTITY_VERSION_CONFLICT"


class InvalidStateTransitionError(DomainError):
    code = "INVALID_STATE_TRANSITION"


class IdempotencyConflictError(DomainError):
    code = "IDEMPOTENCY_CONFLICT"


class StaleAgentAttemptError(DomainError):
    code = "STALE_AGENT_ATTEMPT"


class StorageQuotaExceededError(DomainError):
    code = "ATTACHMENT_STORAGE_QUOTA_EXCEEDED"
