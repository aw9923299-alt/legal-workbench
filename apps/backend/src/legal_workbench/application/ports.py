from collections.abc import AsyncIterator
from typing import Protocol, TypeVar

T = TypeVar("T")


class Repository(Protocol[T]):
    async def get(self, entity_id: str) -> T | None: ...

    async def add(self, entity: T) -> None: ...


class UnitOfWork(Protocol):
    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> bool | None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class AgentRuntime(Protocol):
    async def execute(self, run_id: str) -> None: ...


class EventPublisher(Protocol):
    async def publish_pending(self) -> AsyncIterator[str]: ...
