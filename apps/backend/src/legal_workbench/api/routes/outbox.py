from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from legal_workbench.api.dependencies import get_actor_id
from legal_workbench.api.schemas.outbox import (
    OutboxDeadLetterResponse,
    RequeueDeadLetterResponse,
)
from legal_workbench.infrastructure.outbox import OutboxDispatcher

router = APIRouter(prefix="/system/outbox", tags=["outbox"])


@router.get("/dead-letters", response_model=list[OutboxDeadLetterResponse])
async def list_dead_letters(
    _: Annotated[str, Depends(get_actor_id)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[OutboxDeadLetterResponse]:
    values = await OutboxDispatcher().list_dead_letters(limit=limit)
    return [OutboxDeadLetterResponse.model_validate(value) for value in values]


@router.post(
    "/dead-letters/{dead_letter_id}/requeue",
    response_model=RequeueDeadLetterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def requeue_dead_letter(
    dead_letter_id: UUID,
    _: Annotated[str, Depends(get_actor_id)],
) -> RequeueDeadLetterResponse:
    try:
        outbox_event_id = await OutboxDispatcher().requeue_dead_letter(dead_letter_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RequeueDeadLetterResponse(
        dead_letter_id=dead_letter_id,
        outbox_event_id=outbox_event_id,
    )
