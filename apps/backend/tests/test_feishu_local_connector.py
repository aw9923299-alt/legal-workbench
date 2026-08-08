from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import UUID

import pytest

from legal_workbench.application.feishu_personal_sync import LocalMessageIngestionAdapter
from legal_workbench.application.results import FeishuEventIngestedResult
from legal_workbench.integrations.feishu_local_connector import LocalFeishuConnector


class CapturingHandler:
    def __init__(self) -> None:
        self.commands = []

    async def execute(self, command):  # type: ignore[no-untyped-def]
        self.commands.append(command)
        return FeishuEventIngestedResult(
            event_id=UUID("00000000-0000-0000-0000-000000000301"),
            message_id=UUID("00000000-0000-0000-0000-000000000302"),
            duplicate=False,
        )


def create_readable_local_database(path: Path, attachment_path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE messages (
                account_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                chat_type TEXT NOT NULL,
                message_id TEXT NOT NULL,
                version TEXT NOT NULL,
                sender_id TEXT,
                message_type TEXT NOT NULL,
                content TEXT NOT NULL,
                create_time TEXT NOT NULL,
                update_time TEXT,
                thread_id TEXT,
                root_id TEXT,
                parent_id TEXT
            );
            CREATE TABLE message_attachments (
                message_id TEXT NOT NULL,
                file_key TEXT NOT NULL,
                file_name TEXT NOT NULL,
                mime_type TEXT,
                size INTEGER,
                local_path TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO messages VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                "account-test",
                "oc-local-p2p",
                "p2p",
                "om-local-1",
                "1",
                "ou-sender",
                "text",
                '{"text":"非敏感测试消息"}',
                "1786176000000",
                "1786176000000",
                None,
                None,
                None,
            ),
        )
        connection.execute(
            "INSERT INTO message_attachments VALUES (?, ?, ?, ?, ?, ?)",
            (
                "om-local-1",
                "file-local-1",
                "test.txt",
                "text/plain",
                attachment_path.stat().st_size,
                str(attachment_path),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_local_discovery_is_read_only_and_excludes_credential_locations(
    tmp_path: Path,
) -> None:
    root = tmp_path / "LarkData"
    root.mkdir()
    attachment = root / "downloaded-test.txt"
    attachment.write_text("safe attachment", encoding="utf-8")
    database = root / "messages.db"
    create_readable_local_database(database, attachment)
    opaque = root / "im.db"
    opaque.write_bytes(b"opaque-encrypted-database")
    credential_directory = root / "Cookies"
    credential_directory.mkdir()
    (credential_directory / "Cookies.db").write_bytes(b"sensitive-cookie-material")
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    connector = LocalFeishuConnector(roots=(root,))
    report = connector.discover()
    records = connector.read_messages()
    after = hashlib.sha256(database.read_bytes()).hexdigest()
    rendered = json.dumps(report.to_dict(), ensure_ascii=False)

    assert before == after
    assert report.readable_message_databases == 1
    assert report.readable_attachment_indexes == 1
    assert report.opaque_or_encrypted_databases == 1
    assert len(report.macos_user_hash) == 64
    assert records[0].message_id == "om-local-1"
    assert records[0].chat_type == "p2p"
    assert "sensitive-cookie-material" not in rendered
    assert "Cookies.db" not in rendered
    assert "access_token" not in rendered.lower()
    assert "refresh_token" not in rendered.lower()


@pytest.mark.asyncio
async def test_local_record_enters_only_the_unified_ingestion_handler(
    tmp_path: Path,
) -> None:
    root = tmp_path / "LarkData"
    root.mkdir()
    attachment = root / "downloaded-test.txt"
    attachment.write_text("safe attachment", encoding="utf-8")
    create_readable_local_database(root / "messages.db", attachment)
    record = LocalFeishuConnector(roots=(root,)).read_messages()[0]
    handler = CapturingHandler()

    await LocalMessageIngestionAdapter(handler).ingest(
        record=record,
        tenant_key="tenant-local",
        analysis_disposition="store_only",
        correlation_id="local-test",
    )

    command = handler.commands[0]
    assert command.event_id.startswith("local:")
    assert command.raw_payload["source_channel"] == "local_client"
    assert command.raw_payload["event"]["message"]["message_id"] == "om-local-1"
    assert "safe attachment" not in json.dumps(command.raw_payload)


def test_local_attachment_index_requires_exact_message_association(
    tmp_path: Path,
) -> None:
    root = tmp_path / "LarkData"
    root.mkdir()
    attachment = root / "downloaded-test.txt"
    attachment.write_text("safe attachment", encoding="utf-8")
    create_readable_local_database(root / "messages.db", attachment)
    connector = LocalFeishuConnector(roots=(root,))

    matched = connector.find_attachment(
        message_id="om-local-1", file_key="file-local-1"
    )
    unrelated = connector.find_attachment(
        message_id="om-other", file_key="file-local-1"
    )

    assert matched is not None and matched.local_path == attachment
    assert unrelated is None


def test_unknown_sqlite_schema_is_refused_without_writes(tmp_path: Path) -> None:
    root = tmp_path / "LarkData"
    root.mkdir()
    database = root / "unknown.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE unknown_payload (value TEXT)")
    connection.execute("INSERT INTO unknown_payload VALUES ('opaque')")
    connection.commit()
    connection.close()
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    connector = LocalFeishuConnector(roots=(root,))

    assert connector.read_messages() == ()
    assert connector.discover().findings[0].known_schema is None
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_message_shaped_table_at_unknown_path_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "LarkData"
    root.mkdir()
    attachment = root / "downloaded-test.txt"
    attachment.write_text("safe attachment", encoding="utf-8")
    cache = root / "cache"
    cache.mkdir()
    create_readable_local_database(cache / "messages.db", attachment)

    connector = LocalFeishuConnector(roots=(root,))

    assert connector.read_messages() == ()
    finding = next(
        value
        for value in connector.discover().findings
        if value.database_type == "sqlite"
    )
    assert finding.known_schema is None


def test_message_schema_with_extra_sensitive_column_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "LarkData"
    root.mkdir()
    database = root / "messages.db"
    connection = sqlite3.connect(database)
    columns = ", ".join(
        (
            "account_id TEXT",
            "chat_id TEXT",
            "chat_type TEXT",
            "message_id TEXT",
            "version TEXT",
            "sender_id TEXT",
            "message_type TEXT",
            "content TEXT",
            "create_time TEXT",
            "update_time TEXT",
            "thread_id TEXT",
            "root_id TEXT",
            "parent_id TEXT",
            "access_token TEXT",
        )
    )
    connection.execute(f"CREATE TABLE messages ({columns})")
    connection.commit()
    connection.close()

    connector = LocalFeishuConnector(roots=(root,))

    assert connector.read_messages() == ()
    assert connector.discover().findings[0].known_schema is None


def test_opaque_database_is_reported_but_never_decrypted(tmp_path: Path) -> None:
    root = tmp_path / "LarkData"
    root.mkdir()
    opaque = root / "encrypted.db"
    opaque.write_bytes(b"not-a-sqlite-header encrypted bytes")

    connector = LocalFeishuConnector(roots=(root,))
    report = connector.discover()

    assert report.opaque_or_encrypted_databases == 1
    assert connector.read_messages() == ()
    assert opaque.read_bytes() == b"not-a-sqlite-header encrypted bytes"
