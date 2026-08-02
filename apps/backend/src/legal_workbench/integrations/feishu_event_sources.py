from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol


class EventSourceStatus(StrEnum):
    DISABLED = "disabled"
    STARTING = "starting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class EventSourceHealth:
    status: EventSourceStatus
    last_connected_at: datetime | None = None
    last_disconnected_at: datetime | None = None
    last_event_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    reconnect_count: int = 0


class FeishuEventSource(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def health(self) -> EventSourceHealth: ...


class ReconnectBackoff:
    def __init__(self, *, maximum_seconds: int = 30) -> None:
        if maximum_seconds < 1:
            raise ValueError("maximum_seconds must be positive")
        self._maximum = maximum_seconds
        self._attempt = 0

    def next_delay(self) -> int:
        delay = min(2**self._attempt, self._maximum)
        self._attempt += 1
        return int(delay)

    def reset(self) -> None:
        self._attempt = 0


StateChanged = Callable[[EventSourceHealth], Awaitable[None]]
Connect = Callable[[], Awaitable[None]]
Disconnect = Callable[[], object]
Sleep = Callable[[float], Awaitable[None]]


class LongConnectionFeishuEventSource:
    """Managed lifecycle around the blocking official SDK connection.

    The injected ``connect`` coroutine owns authentication, heartbeats, and the
    blocking SDK loop. This class persists observable lifecycle state and adds
    bounded retry when that loop exits or raises.
    """

    def __init__(
        self,
        *,
        connect: Connect,
        disconnect: Disconnect,
        state_changed: StateChanged | None = None,
        sleep: Sleep = asyncio.sleep,
        maximum_backoff_seconds: int = 30,
    ) -> None:
        self._connect = connect
        self._disconnect = disconnect
        self._state_changed = state_changed
        self._sleep = sleep
        self._backoff = ReconnectBackoff(maximum_seconds=maximum_backoff_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = False
        self._health = EventSourceHealth(status=EventSourceStatus.DISCONNECTED)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_requested = False
        await self._set_health(status=EventSourceStatus.STARTING)
        self._task = asyncio.create_task(self._run(), name="feishu-long-connection")

    async def stop(self) -> None:
        self._stop_requested = True
        result = self._disconnect()
        if inspect.isawaitable(result):
            await result
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._task = None
        await self._set_health(
            status=EventSourceStatus.DISCONNECTED,
            last_disconnected_at=datetime.now(UTC),
        )

    async def health(self) -> EventSourceHealth:
        return self._health

    async def record_event(self) -> None:
        await self._set_health(last_event_at=datetime.now(UTC))

    async def record_reconnecting(self) -> None:
        await self._set_health(
            status=EventSourceStatus.DEGRADED,
            last_disconnected_at=datetime.now(UTC),
            reconnect_count=self._health.reconnect_count + 1,
        )

    async def record_reconnected(self) -> None:
        self._backoff.reset()
        await self._set_health(
            status=EventSourceStatus.CONNECTED,
            last_connected_at=datetime.now(UTC),
            last_error_code=None,
            last_error_message=None,
        )

    async def _run(self) -> None:
        while not self._stop_requested:
            try:
                await self._set_health(
                    status=EventSourceStatus.STARTING,
                    last_error_code=None,
                    last_error_message=None,
                )
                await self._connect()
                if not self._stop_requested:
                    raise ConnectionError("Feishu long connection exited unexpectedly")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                reconnect_count = self._health.reconnect_count + 1
                await self._set_health(
                    status=EventSourceStatus.DEGRADED,
                    last_disconnected_at=datetime.now(UTC),
                    last_error_code=type(exc).__name__,
                    last_error_message=str(exc)[:1000],
                    reconnect_count=reconnect_count,
                )
                await self._sleep(self._backoff.next_delay())
            else:
                self._backoff.reset()

    async def _set_health(self, **changes: object) -> None:
        current = self._health
        values: dict[str, object] = {
            "status": current.status,
            "last_connected_at": current.last_connected_at,
            "last_disconnected_at": current.last_disconnected_at,
            "last_event_at": current.last_event_at,
            "last_error_code": current.last_error_code,
            "last_error_message": current.last_error_message,
            "reconnect_count": current.reconnect_count,
        }
        values.update(changes)
        self._health = EventSourceHealth(**values)  # type: ignore[arg-type]
        if self._state_changed is not None:
            await self._state_changed(self._health)
