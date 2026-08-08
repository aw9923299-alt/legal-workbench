from __future__ import annotations

from types import TracebackType

import pytest

from legal_workbench.application.commands import IngestFeishuEventCommand
from legal_workbench.application.feishu_handlers import IngestFeishuEventHandler
from legal_workbench.domain.entities import FeishuMessage, FeishuRawEvent


class Collector:
    def __init__(self) -> None:
        self.values: list[object] = []

    async def add(self, value: object) -> None:
        self.values.append(value)


class FeishuRepository:
    def __init__(self) -> None:
        self.events: list[FeishuRawEvent] = []
        self.messages: list[FeishuMessage] = []
        self.versions: list[object] = []

    async def get_event_by_external_id(
        self, event_id: str, *, tenant_key: str | None = None
    ) -> FeishuRawEvent | None:
        return next(
            (
                value
                for value in self.events
                if value.event_id == event_id
                and (tenant_key is None or value.tenant_key == tenant_key)
            ),
            None,
        )

    async def add_event(self, value: FeishuRawEvent) -> None:
        self.events.append(value)

    async def get_message(
        self, *, tenant_key: str | None, message_id: str
    ) -> FeishuMessage | None:
        return next(
            (
                value
                for value in self.messages
                if value.tenant_key == tenant_key and value.message_id == message_id
            ),
            None,
        )

    async def add_message(self, value: FeishuMessage) -> None:
        self.messages.append(value)

    async def save_message(self, value: FeishuMessage) -> None:
        assert value in self.messages

    async def next_message_revision(self, message_id: object) -> int:
        return len(self.versions) + 1

    async def add_message_version(self, value: object) -> None:
        self.versions.append(value)

    async def add_attachments(self, values: object) -> None:
        del values


class UnitOfWork:
    def __init__(self, repository: FeishuRepository) -> None:
        self.feishu = repository
        self.outbox_events = Collector()
        self.audit_events = Collector()

    async def __aenter__(self) -> UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        del operation, key

    async def commit(self) -> None:
        return None


def command(*, event_id: str, source_channel: str, text: str) -> IngestFeishuEventCommand:
    payload: dict[str, object] = {
        "schema": "2.0",
        "source_channel": source_channel,
        "provenance": {"connector": source_channel, "contentHash": text},
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant-source-priority",
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou-sender"},
                "sender_type": "user",
            },
            "message": {
                "message_id": "om-shared",
                "chat_id": "oc-test",
                "message_type": "text",
                "content": {"text": text},
                "create_time": "1786176000000",
                "update_time": "1786176000000",
            },
        },
    }
    return IngestFeishuEventCommand(
        actor_id="test",
        correlation_id=event_id,
        event_id=event_id,
        event_type="im.message.receive_v1",
        tenant_key="tenant-source-priority",
        app_id=None,
        schema_version="2.0",
        raw_payload=payload,
    )


@pytest.mark.asyncio
async def test_official_source_upgrades_local_record_without_duplicate_message() -> None:
    repository = FeishuRepository()
    handler = IngestFeishuEventHandler(lambda: UnitOfWork(repository))

    local = await handler.execute(
        command(event_id="local:test:om-shared:1", source_channel="local_client", text="缓存正文")
    )
    official = await handler.execute(
        command(event_id="uat:test:om-shared:1", source_channel="user_api", text="官方正文")
    )
    later_local = await handler.execute(
        command(event_id="local:test:om-shared:2", source_channel="local_client", text="旧缓存")
    )

    assert len(repository.messages) == 1
    message = repository.messages[0]
    assert message.id == local.message_id == official.message_id == later_local.message_id
    assert message.plain_text == "官方正文"
    assert message.source_channel == "user_api"
    assert message.source_channels == ["local_client", "user_api"]
    assert message.provenance["connector"] == "user_api"
    assert official.duplicate is False
    assert later_local.duplicate is True
    assert [event.source_channel for event in repository.events] == [
        "local_client",
        "user_api",
        "local_client",
    ]
