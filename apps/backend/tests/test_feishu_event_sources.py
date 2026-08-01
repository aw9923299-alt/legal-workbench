from __future__ import annotations

import asyncio

import pytest

from legal_workbench.integrations.feishu_event_sources import (
    EventSourceStatus,
    LongConnectionFeishuEventSource,
    ReconnectBackoff,
)
from legal_workbench.integrations.feishu_sdk import sdk_event_to_payload


def test_reconnect_backoff_is_bounded_and_resets_after_success() -> None:
    backoff = ReconnectBackoff(maximum_seconds=30)

    assert [backoff.next_delay() for _ in range(7)] == [1, 2, 4, 8, 16, 30, 30]
    backoff.reset()
    assert backoff.next_delay() == 1


@pytest.mark.asyncio
async def test_long_connection_retries_without_fast_loop_and_stops_gracefully() -> None:
    attempts = 0
    sleeps: list[float] = []
    connected = asyncio.Event()

    async def connect() -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError(f"failure-{attempts}")
        await source.record_reconnected()
        connected.set()
        await asyncio.Event().wait()

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    source = LongConnectionFeishuEventSource(
        connect=connect,
        disconnect=lambda: None,
        sleep=sleep,
    )

    await source.start()
    await asyncio.wait_for(connected.wait(), timeout=1)
    health = await source.health()
    await source.stop()

    assert attempts == 3
    assert sleeps == [1, 2]
    assert health.status == EventSourceStatus.CONNECTED
    assert health.reconnect_count == 2
    assert (await source.health()).status == EventSourceStatus.DISCONNECTED


def test_sdk_event_payload_preserves_header_and_nested_event() -> None:
    class Header:
        event_id = "evt-sdk-1"
        event_type = "im.message.receive_v1"
        tenant_key = "tenant-sdk"

    class Message:
        message_id = "om-sdk-1"
        content = '{"text":"hello"}'

    class Event:
        message = Message()

    class Envelope:
        schema = "2.0"
        header = Header()
        event = Event()

    payload = sdk_event_to_payload(Envelope(), event_type="im.message.receive_v1")

    assert payload["header"]["event_id"] == "evt-sdk-1"  # type: ignore[index]
    assert payload["event"]["message"]["message_id"] == "om-sdk-1"  # type: ignore[index]
