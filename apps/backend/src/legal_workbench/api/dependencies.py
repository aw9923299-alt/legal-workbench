from functools import lru_cache
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from legal_workbench.api.auth import InvalidSessionError, RequestActor, decode_session_token
from legal_workbench.config import RuntimeEnvironment, get_settings
from legal_workbench.domain.entities import AuthenticatedActorId
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory


@lru_cache(maxsize=1)
def get_uow_factory() -> SqlAlchemyUnitOfWorkFactory:
    return SqlAlchemyUnitOfWorkFactory()


async def get_request_actor(
    request: Request,
    x_actor_id: Annotated[str | None, Header(alias="X-Actor-ID")] = None,
) -> RequestActor:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        try:
            return decode_session_token(token=token, secret=settings.session_secret)
        except InvalidSessionError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication session is invalid or expired.",
            ) from exc
    actor_id = (x_actor_id or "").strip()
    if (
        actor_id
        and settings.environment
        in {RuntimeEnvironment.LOCAL, RuntimeEnvironment.DEVELOPMENT}
        and settings.allow_development_actor_header
    ):
        if len(actor_id) > 160:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Actor-ID must not exceed 160 characters.",
            )
        return RequestActor(actor_id=actor_id, identity_source="development_header")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authenticated local session is required.",
    )


async def get_actor_id(
    request: Request,
    x_actor_id: Annotated[str | None, Header(alias="X-Actor-ID")] = None,
) -> str:
    actor = await get_request_actor(request=request, x_actor_id=x_actor_id)
    if len(actor.actor_id) > 160:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authenticated actor ID must not exceed 160 characters.",
        )
    return AuthenticatedActorId(actor.actor_id, identity_source=actor.identity_source)


async def get_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required.",
        )
    key = idempotency_key.strip()
    if len(key) > 160:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must not exceed 160 characters.",
        )
    return key


def get_correlation_id(request: Request) -> str:
    return str(request.state.correlation_id)
