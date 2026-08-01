from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from legal_workbench.infrastructure.database import database_is_ready
from legal_workbench.infrastructure.redis_client import redis_is_ready

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: bool
    redis: bool


@router.get("/live", response_model=LivenessResponse)
async def live() -> LivenessResponse:
    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse)
async def ready(response: Response) -> ReadinessResponse:
    database_ready, redis_ready = await database_is_ready(), await redis_is_ready()
    ready_state = database_ready and redis_ready
    if not ready_state:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready_state else "not_ready",
        database=database_ready,
        redis=redis_ready,
    )
