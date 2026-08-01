from datetime import datetime
from uuid import UUID

from legal_workbench.api.schemas.base import ApiModel


class OutboxDeadLetterResponse(ApiModel):
    id: UUID
    original_event_id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, object]
    correlation_id: str
    attempts: int
    last_error: str
    failed_at: datetime
    requeued_at: datetime | None
    requeued_event_id: UUID | None


class RequeueDeadLetterResponse(ApiModel):
    dead_letter_id: UUID
    outbox_event_id: UUID
