from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from legal_workbench.api.errors import (
    domain_error_handler,
    integrity_error_handler,
    stale_data_handler,
)
from legal_workbench.api.middleware import CorrelationIdMiddleware
from legal_workbench.api.router import api_router
from legal_workbench.config import RuntimeEnvironment, get_settings
from legal_workbench.domain.errors import DomainError
from legal_workbench.infrastructure.database import dispose_engine
from legal_workbench.infrastructure.logging import configure_logging
from legal_workbench.infrastructure.redis_client import close_redis_client

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("application_started", environment=settings.environment)
    try:
        yield
    finally:
        await close_redis_client()
        await dispose_engine()
        logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    docs_url=(
        "/docs" if settings.environment != RuntimeEnvironment.PRODUCTION else None
    ),
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(DomainError, domain_error_handler)
app.add_exception_handler(StaleDataError, stale_data_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.include_router(api_router, prefix=settings.api_prefix)
