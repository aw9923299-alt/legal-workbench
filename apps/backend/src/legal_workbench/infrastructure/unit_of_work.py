from __future__ import annotations

from types import TracebackType

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from legal_workbench.infrastructure.database import get_session_factory
from legal_workbench.infrastructure.repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyContextSnapshotRepository,
    SqlAlchemyIdempotencyRepository,
    SqlAlchemyLegalMatterRepository,
    SqlAlchemyMessageCandidateRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyWorkItemRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.context_snapshots: SqlAlchemyContextSnapshotRepository
        self.candidates: SqlAlchemyMessageCandidateRepository
        self.matters: SqlAlchemyLegalMatterRepository
        self.work_items: SqlAlchemyWorkItemRepository
        self.audit_events: SqlAlchemyAuditEventRepository
        self.outbox_events: SqlAlchemyOutboxEventRepository
        self.idempotency: SqlAlchemyIdempotencyRepository

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self.context_snapshots = SqlAlchemyContextSnapshotRepository(self._session)
        self.candidates = SqlAlchemyMessageCandidateRepository(self._session)
        self.matters = SqlAlchemyLegalMatterRepository(self._session)
        self.work_items = SqlAlchemyWorkItemRepository(self._session)
        self.audit_events = SqlAlchemyAuditEventRepository(self._session)
        self.outbox_events = SqlAlchemyOutboxEventRepository(self._session)
        self.idempotency = SqlAlchemyIdempotencyRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        if self._session is None:
            return None
        try:
            if exc_type is not None:
                await self._session.rollback()
        finally:
            await self._session.close()
        return None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Unit of work has not been entered")
        return self._session

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        lock_key = f"{operation}:{key}"
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


class SqlAlchemyUnitOfWorkFactory:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None = None
    ) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory or get_session_factory())
