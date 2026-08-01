from uuid import UUID

from legal_workbench.api.schemas.base import ApiModel


class FeishuEventIngestedResponse(ApiModel):
    event_id: UUID
    message_id: UUID | None
    duplicate: bool
