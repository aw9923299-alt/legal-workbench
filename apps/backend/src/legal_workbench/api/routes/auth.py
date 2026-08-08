from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from legal_workbench.api.auth import RequestActor, create_session_token
from legal_workbench.api.dependencies import get_request_actor
from legal_workbench.config import RuntimeEnvironment, get_settings

router = APIRouter(prefix="/auth", tags=["authentication"])


def _require_local_session_mode() -> None:
    settings = get_settings()
    if settings.environment not in {
        RuntimeEnvironment.LOCAL,
        RuntimeEnvironment.DEVELOPMENT,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local session initialization is disabled outside explicit local modes.",
        )


def _set_session(
    response: Response,
    *,
    actor_id: str,
    identity_source: str,
) -> dict[str, str]:
    settings = get_settings()
    token = create_session_token(
        actor_id=actor_id,
        identity_source=identity_source,
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
    return {"actorId": actor_id, "identitySource": identity_source}


@router.post("/local-session", status_code=status.HTTP_201_CREATED)
async def create_local_session(response: Response) -> dict[str, str]:
    _require_local_session_mode()
    settings = get_settings()
    return _set_session(
        response,
        actor_id=settings.local_actor_id,
        identity_source="local_session",
    )


@router.post("/local-supervisor-session", status_code=status.HTTP_201_CREATED)
async def create_local_supervisor_session(response: Response) -> dict[str, str]:
    """Issue a distinct audit identity to the loopback-only Mac supervisor."""
    _require_local_session_mode()
    settings = get_settings()
    return _set_session(
        response,
        actor_id=settings.local_supervisor_actor_id,
        identity_source="local_supervisor",
    )


@router.get("/session")
async def get_local_session(
    actor: Annotated[RequestActor, Depends(get_request_actor)],
) -> dict[str, str]:
    return {"actorId": actor.actor_id, "identitySource": actor.identity_source}
