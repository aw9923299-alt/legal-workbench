from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from legal_workbench.api.auth import RequestActor
from legal_workbench.api.dependencies import (
    get_actor_id,
    get_correlation_id,
    get_idempotency_key,
    get_request_actor,
)
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
    request: Request,
    response: Response,
    actor: Annotated[RequestActor, Depends(get_request_actor)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
) -> RequeueDeadLetterResponse:
    try:
        result = await OutboxDispatcher().requeue_dead_letter(
            dead_letter_id,
            actor_id=actor.actor_id,
            actor_source=actor.identity_source,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return RequeueDeadLetterResponse(
        dead_letter_id=dead_letter_id,
        outbox_event_id=result.outbox_event_id,
        idempotent_replay=result.idempotent_replay,
    )
