from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from legal_workbench.api.dependencies import get_actor_id
from legal_workbench.api.schemas.dashboard import DashboardTodayResponse
from legal_workbench.application.dashboard import DashboardQueueService
from legal_workbench.config import Settings, get_settings
from legal_workbench.infrastructure.dashboard import (
    CompositeDashboardDataSource,
    OperationalHealthDashboardDataSource,
    SqlAlchemyDashboardDataSource,
)
from legal_workbench.infrastructure.database import get_session_factory

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_dashboard_service() -> DashboardQueueService:
    return DashboardQueueService(
        CompositeDashboardDataSource(
            SqlAlchemyDashboardDataSource(get_session_factory()),
            OperationalHealthDashboardDataSource(),
        )
    )


@router.get("/today", response_model=DashboardTodayResponse)
async def get_today_dashboard(
    actor_id: Annotated[str, Depends(get_actor_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[DashboardQueueService, Depends(get_dashboard_service)],
) -> DashboardTodayResponse:
    result = await service.get_today(
        actor_id=actor_id,
        now=datetime.now(ZoneInfo(settings.local_timezone)),
    )
    return DashboardTodayResponse.model_validate(result)
