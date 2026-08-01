from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date, datetime
from enum import Enum

import structlog
from lark_oapi.channel import FeishuChannel  # type: ignore[import-untyped]
from lark_oapi.event.dispatcher_handler import (  # type: ignore[import-untyped]
    EventDispatcherHandler,
)

logger = structlog.get_logger(__name__)

PayloadSink = Callable[[dict[str, object]], Awaitable[None]]
TransportCallback = Callable[[], Awaitable[None]]


def _to_json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_to_json_value(item) for item in value]

    attributes: dict[str, object] = {}
    candidate_names = set(getattr(value, "_types", {}).keys())
    candidate_names.update(
        name for name in dir(value) if not name.startswith("_")
    )
    for name in sorted(candidate_names):
        try:
            item = getattr(value, name)
        except Exception:
            continue
        if callable(item) or item is None:
            continue
        attributes[name] = _to_json_value(item)
    return attributes


def sdk_event_to_payload(data: object, *, event_type: str) -> dict[str, object]:
    """Convert generated Lark SDK event objects into an auditable JSON envelope."""

    converted = _to_json_value(data)
    payload = dict(converted) if isinstance(converted, dict) else {"event": converted}
    payload.setdefault("schema", "2.0")
    header = payload.get("header")
    if not isinstance(header, dict):
        header = {}
        payload["header"] = header
    header.setdefault("event_type", event_type)
    return payload


class PersistingFeishuChannel(FeishuChannel):  # type: ignore[misc]
    """Official SDK channel whose callbacks synchronously persist raw events.

    Feishu long-connection callbacks have a short acknowledgement budget. The
    callback waits at most 2.5 seconds for the application service to commit;
    a timeout is raised so the platform can redeliver the event. PostgreSQL
    remains the final deduplication authority.
    """

    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        encrypt_key: str | None,
        verification_token: str | None,
        sink: PayloadSink,
    ) -> None:
        self._payload_sink = sink
        super().__init__(
            app_id=app_id,
            app_secret=app_secret,
            encrypt_key=encrypt_key,
            verification_token=verification_token,
            transport="ws",
        )

    def _build_dispatcher(self) -> EventDispatcherHandler:
        builder = EventDispatcherHandler.builder(
            self.config.encrypt_key or "",
            self.config.verification_token or "",
            self.config.log_level,
        )
        builder = builder.register_p2_im_message_receive_v1(
            lambda data: self._persist_callback(data, "im.message.receive_v1")
        )
        builder = builder.register_p2_im_message_recalled_v1(
            lambda data: self._persist_callback(data, "im.message.recalled_v1")
        )
        # Feishu currently exposes edits through a customized event envelope in
        # SDK releases that do not generate a typed processor for this event.
        builder = builder.register_p2_customized_event(
            "im.message.message_edited_v1",
            lambda data: self._persist_callback(data, "im.message.message_edited_v1"),
        )
        return builder.build()

    def _persist_callback(self, data: object, event_type: str) -> None:
        payload = sdk_event_to_payload(data, event_type=event_type)
        future = self.schedule(self._payload_sink(payload))
        try:
            future.result(timeout=2.5)
        except concurrent.futures.TimeoutError:
            future.cancel()
            logger.error("feishu_event_persist_timeout", event_type=event_type)
            raise


class OfficialFeishuSdkConnection:
    """Restartable adapter around the official SDK's blocking WS lifecycle."""

    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        encrypt_key: str | None,
        verification_token: str | None,
        sink: PayloadSink,
        on_reconnecting: TransportCallback | None = None,
        on_reconnected: TransportCallback | None = None,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._encrypt_key = encrypt_key
        self._verification_token = verification_token
        self._sink = sink
        self._on_reconnecting = on_reconnecting
        self._on_reconnected = on_reconnected
        self._channel: PersistingFeishuChannel | None = None
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None

    async def connect(self) -> None:
        self._owner_loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        channel = PersistingFeishuChannel(
            app_id=self._app_id,
            app_secret=self._app_secret,
            encrypt_key=self._encrypt_key,
            verification_token=self._verification_token,
            sink=self._sink,
        )
        channel.on("reconnecting", lambda *_: self._notify(self._on_reconnecting))
        channel.on("reconnected", lambda *_: self._notify(self._on_reconnected))
        self._channel = channel
        await channel.start_background()
        if self._on_reconnected is not None:
            await self._on_reconnected()
        await self._stop_event.wait()

    async def disconnect(self) -> None:
        channel = self._channel
        self._channel = None
        if self._stop_event is not None:
            self._stop_event.set()
        if channel is not None:
            await channel.disconnect()

    def _notify(self, callback: TransportCallback | None) -> None:
        loop = self._owner_loop
        if callback is None or loop is None or loop.is_closed():
            return
        async def invoke() -> None:
            await callback()

        asyncio.run_coroutine_threadsafe(invoke(), loop)
