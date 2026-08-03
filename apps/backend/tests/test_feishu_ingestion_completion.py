from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from legal_workbench.config import Settings
from legal_workbench.infrastructure.database import Base
from legal_workbench.infrastructure.models import (  # noqa: F401
    FeishuAttachmentModel,
    FeishuMessageVersionModel,
    IntegrationConnectionModel,
)
from legal_workbench.integrations.feishu_events import (
    FeishuMessageOperation,
    normalize_feishu_event,
)


def envelope(
    *,
    event_type: str = "im.message.receive_v1",
    message_type: str = "text",
    content: object = '{"text":"请法务审核合同"}',
) -> dict[str, object]:
    return {
        "schema": "2.0",
        "header": {
            "event_id": "evt-1",
            "event_type": event_type,
            "tenant_key": "tenant-a",
            "app_id": "cli-test",
            "create_time": "1785596400000",
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou-requester"},
                "sender_type": "user",
            },
            "message": {
                "message_id": "om-1",
                "chat_id": "oc-1",
                "thread_id": "omt-1",
                "root_id": "om-root",
                "parent_id": "om-parent",
                "message_type": message_type,
                "content": content,
                "create_time": "1785596400000",
                "update_time": "1785596460000",
            },
        },
    }


def test_text_message_is_normalized_with_thread_relationships() -> None:
    normalized = normalize_feishu_event(envelope())

    assert normalized.operation == FeishuMessageOperation.CREATE
    assert normalized.supported is True
    assert normalized.message is not None
    assert normalized.message.plain_text == "请法务审核合同"
    assert normalized.message.thread_id == "omt-1"
    assert normalized.message.root_message_id == "om-root"
    assert normalized.message.parent_message_id == "om-parent"
    assert normalized.message.sent_at == datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def test_post_message_flattens_readable_text_without_losing_structure() -> None:
    post = {
        "zh_cn": {
            "title": "合同审核",
            "content": [
                [{"tag": "text", "text": "请审核"}, {"tag": "a", "text": "采购合同"}],
                [{"tag": "at", "user_name": "法务"}],
            ],
        }
    }

    normalized = normalize_feishu_event(envelope(message_type="post", content=post))

    assert normalized.message is not None
    assert normalized.message.plain_text == "合同审核\n请审核 采购合同\n@法务"
    assert normalized.message.structured_content == post


@pytest.mark.parametrize(
    ("message_type", "content", "file_key", "file_name"),
    [
        ("file", {"file_key": "file-1", "file_name": "合同.pdf"}, "file-1", "合同.pdf"),
        ("image", {"image_key": "img-1"}, "img-1", "img-1"),
    ],
)
def test_attachment_message_extracts_metadata(
    message_type: str,
    content: dict[str, object],
    file_key: str,
    file_name: str,
) -> None:
    normalized = normalize_feishu_event(envelope(message_type=message_type, content=content))

    assert normalized.message is not None
    assert normalized.message.attachments[0].file_key == file_key
    assert normalized.message.attachments[0].file_name == file_name
    assert normalized.message.attachments[0].download_status == "pending"


def test_unsupported_message_is_persistable_but_not_analysable() -> None:
    normalized = normalize_feishu_event(
        envelope(message_type="interactive", content={"card": "opaque"})
    )

    assert normalized.message is not None
    assert normalized.supported is False
    assert normalized.should_trigger_analysis is False
    assert normalized.unsupported_reason == "unsupported_message_type:interactive"


@pytest.mark.parametrize(
    ("event_type", "operation"),
    [
        ("im.message.message_edited_v1", FeishuMessageOperation.EDIT),
        ("im.message.recalled_v1", FeishuMessageOperation.RECALL),
    ],
)
def test_edit_and_recall_events_are_classified(
    event_type: str, operation: FeishuMessageOperation
) -> None:
    payload = envelope(event_type=event_type)
    if operation == FeishuMessageOperation.RECALL:
        payload["event"] = {
            "message_id": "om-1",
            "recall_time": "1785596520000",
        }

    normalized = normalize_feishu_event(payload)

    assert normalized.operation == operation
    assert normalized.external_message_id == "om-1"
    assert normalized.should_trigger_analysis is (operation == FeishuMessageOperation.EDIT)


def test_real_long_connection_requires_app_credentials() -> None:
    with pytest.raises(ValidationError, match="app credentials"):
        Settings(
            enable_real_feishu=True,
            feishu_event_source="long_connection",
            feishu_app_id=None,
            feishu_app_secret=None,
            _env_file=None,
        )


def test_real_webhook_requires_verification_token() -> None:
    with pytest.raises(ValidationError, match="verification token"):
        Settings(
            enable_real_feishu=True,
            feishu_event_source="webhook",
            feishu_verification_token=None,
            _env_file=None,
        )


def test_feishu_operational_tables_preserve_connection_versions_and_attachments() -> None:
    connection = Base.metadata.tables["integration_connections"]
    versions = Base.metadata.tables["feishu_message_versions"]
    attachments = Base.metadata.tables["message_attachments"]

    assert {
        "connection_mode",
        "status",
        "last_event_at",
        "last_error_code",
        "reconnect_count",
        "last_reconcile_at",
    }.issubset(connection.columns.keys())
    assert {"revision", "content_hash", "raw_payload", "edited_at", "recalled_at"}.issubset(
        versions.columns.keys()
    )
    assert {
        "file_key",
        "sha256",
        "local_path",
        "download_status",
        "download_error",
        "extraction_status",
        "extractor_version",
        "page_count",
        "character_count",
        "extraction_error_code",
    }.issubset(attachments.columns.keys())
