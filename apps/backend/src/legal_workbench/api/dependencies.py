from functools import lru_cache
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory


@lru_cache(maxsize=1)
def get_uow_factory() -> SqlAlchemyUnitOfWorkFactory:
    return SqlAlchemyUnitOfWorkFactory()


async def get_actor_id(
    x_actor_id: Annotated[str | None, Header(alias="X-Actor-ID")] = None,
) -> str:
    if not x_actor_id or not x_actor_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Actor-ID header is required.",
        )
    actor_id = x_actor_id.strip()
    if len(actor_id) > 160:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Actor-ID must not exceed 160 characters.",
        )
    return actor_id


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
