from datetime import datetime

from pydantic import Field

from legal_workbench.api.schemas.base import ApiModel
from legal_workbench.application.dashboard import DashboardGroup
from legal_workbench.domain.enums import LegalRisk, Priority


class DashboardItemResponse(ApiModel):
    id: str
    group: DashboardGroup
    object_type: str
    title: str
    description: str
    href: str
    status: str
    created_at: datetime
    due_at: datetime | None
    is_hard_deadline: bool
    is_overdue: bool
    legal_risk: LegalRisk
    confirmed_priority: Priority | None
    ai_suggested_priority: Priority | None
    waiting_since: datetime | None
    waiting_seconds: int = Field(ge=0)
    ranking_reasons: tuple[str, ...]


class DashboardTodayResponse(ApiModel):
    generated_at: datetime
    today_must_handle: tuple[DashboardItemResponse, ...]
    overdue: tuple[DashboardItemResponse, ...]
    pending_candidates: tuple[DashboardItemResponse, ...]
    analysis_failed: tuple[DashboardItemResponse, ...]
    waiting_others: tuple[DashboardItemResponse, ...]
    upcoming_deadlines: tuple[DashboardItemResponse, ...]
    pending_outbound_review: tuple[DashboardItemResponse, ...]
    system_abnormal: tuple[DashboardItemResponse, ...]
