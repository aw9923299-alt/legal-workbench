from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from legal_workbench.domain.common import (
    utc_now,
)


class AuthenticatedActorId(str):
    """String-compatible actor identifier carrying its verified identity source."""

    identity_source: str

    def __new__(cls, value: str, *, identity_source: str) -> AuthenticatedActorId:
        instance = super().__new__(cls, value)
        instance.identity_source = identity_source
        return instance


@dataclass(slots=True)
class AuditEvent:
    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_type: str
    actor_id: str
    payload: dict[str, object]
    correlation_id: str
    actor_source: str = "system"
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.actor_source == "system" and isinstance(self.actor_id, AuthenticatedActorId):
            self.actor_source = self.actor_id.identity_source


@dataclass(slots=True)
class OutboxEvent:
    id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, object]
    correlation_id: str
    occurred_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class IdempotencyRecord:
    id: UUID
    operation: str
    idempotency_key: str
    request_hash: str
    response_payload: dict[str, object]
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
