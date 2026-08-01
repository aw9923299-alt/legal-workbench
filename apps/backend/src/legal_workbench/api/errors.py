from typing import cast

from fastapi import Request, status
from fastapi.responses import JSONResponse

from legal_workbench.domain.errors import (
    DomainError,
    EntityNotFoundError,
    EntityVersionConflictError,
    IdempotencyConflictError,
    InvalidStateTransitionError,
)


def _correlation_id(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "unknown"))


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "correlationId": _correlation_id(request),
            }
        },
    )


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    domain_error = cast(DomainError, exc)
    if isinstance(domain_error, EntityNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(
        domain_error,
        (
            EntityVersionConflictError,
            IdempotencyConflictError,
            InvalidStateTransitionError,
        ),
    ):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return _error_response(
        request,
        status_code=status_code,
        code=domain_error.code,
        message=domain_error.message,
        details=domain_error.details,
    )


async def stale_data_handler(request: Request, _: Exception) -> JSONResponse:
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        code="ENTITY_VERSION_CONFLICT",
        message="The entity was changed by another operation.",
    )


async def integrity_error_handler(request: Request, _: Exception) -> JSONResponse:
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        code="DATA_INTEGRITY_CONFLICT",
        message="The operation conflicts with an existing record.",
    )
