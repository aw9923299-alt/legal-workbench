from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from legal_workbench.api.auth import RequestActor, create_session_token
from legal_workbench.api.dependencies import get_request_actor
from legal_workbench.config import RuntimeEnvironment, get_settings

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/local-session", status_code=status.HTTP_201_CREATED)
async def create_local_session(response: Response) -> dict[str, str]:
    settings = get_settings()
    if settings.environment not in {
        RuntimeEnvironment.LOCAL,
        RuntimeEnvironment.DEVELOPMENT,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local session initialization is disabled outside explicit local modes.",
        )
    token = create_session_token(
        actor_id=settings.local_actor_id,
        identity_source="local_session",
        secret=settings.session_secret,
        ttl_seconds=settings.session_ttl_seconds,
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=False,
        samesite="strict",
        path="/",
    )
    return {"actorId": settings.local_actor_id, "identitySource": "local_session"}


@router.get("/session")
async def get_local_session(
    actor: Annotated[RequestActor, Depends(get_request_actor)],
) -> dict[str, str]:
    return {"actorId": actor.actor_id, "identitySource": actor.identity_source}
