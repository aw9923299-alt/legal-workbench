from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import plistlib
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

_SQLITE_HEADER = b"SQLite format 3\x00"
_EXCLUDED_COMPONENTS = {
    "auth",
    "cookies",
    "cookie",
    "credentials",
    "keychain",
    "local storage",
    "login data",
    "passport",
    "tokens",
    "token",
}
_MESSAGE_COLUMNS = {
    "account_id",
    "chat_id",
    "chat_type",
    "message_id",
    "version",
    "sender_id",
    "message_type",
    "content",
    "create_time",
    "update_time",
    "thread_id",
    "root_id",
    "parent_id",
}
_ATTACHMENT_COLUMNS = {
    "message_id",
    "file_key",
    "file_name",
    "mime_type",
    "size",
    "local_path",
}
_SUPPORTED_MESSAGE_SCHEMA_PATHS = {
    "messages_v1": frozenset({"messages.db"}),
}
_SUPPORTED_MESSAGE_SCHEMA_TABLES = frozenset(
    {"messages", "message_attachments"}
)


def default_feishu_roots() -> tuple[Path, ...]:
    library = Path.home() / "Library"
    return (
        library / "Containers" / "com.bytedance.macos.feishu",
        library / "Group Containers" / "XY6NLV7YTS.com.bytedance.macos.feishu",
        library / "Group Containers" / "XY6NLV7YTS.feishu",
    )


@dataclass(frozen=True, slots=True)
class LocalDatabaseFinding:
    location_type: str
    relative_path_hash: str
    size: int
    modified_at: str
    database_type: str
    table_count: int
    known_schema: str | None
    readable_attachment_index: bool


@dataclass(frozen=True, slots=True)
class LocalFeishuDiscoveryReport:
    generated_at: str
    client_installed: bool
    client_version: str | None
    macos_user_hash: str
    roots_checked: int
    roots_readable: int
    database_files: int
    readable_message_databases: int
    readable_attachment_indexes: int
    opaque_or_encrypted_databases: int
    cache_file_count: int
    potential_attachment_cache_files: int
    cache_file_types: dict[str, int]
    findings: tuple[LocalDatabaseFinding, ...]
    credential_locations_excluded: bool = True
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LocalFeishuRecord:
    account_id: str
    chat_id: str
    chat_type: str
    message_id: str
    version: str
    sender_id: str | None
    message_type: str
    content: dict[str, object]
    create_time: str
    update_time: str | None
    thread_id: str | None
    root_id: str | None
    parent_id: str | None
    database_path_hash: str


@dataclass(frozen=True, slots=True)
class LocalFeishuAttachment:
    message_id: str
    file_key: str
    file_name: str
    mime_type: str | None
    size: int | None
    local_path: Path


class LocalFeishuConnector:
    """Read-only adapter for already-visible local Feishu client data."""

    def __init__(self, *, roots: tuple[Path, ...] | None = None) -> None:
        self._roots = tuple(path.resolve() for path in (roots or default_feishu_roots()))

    def discover(self) -> LocalFeishuDiscoveryReport:
        findings: list[LocalDatabaseFinding] = []
        cache_file_count = 0
        potential_attachment_cache_files = 0
        cache_file_types: dict[str, int] = {}
        roots_readable = 0
        for root in self._roots:
            if not root.is_dir() or not os.access(root, os.R_OK):
                continue
            roots_readable += 1
            for path in self._iter_safe_files(root):
                if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
                    try:
                        findings.append(self._inspect_database(root, path))
                    except OSError:
                        continue
                else:
                    cache_file_count += 1
                    suffix = path.suffix.lower() or "no_extension"
                    cache_file_types[suffix] = cache_file_types.get(suffix, 0) + 1
                    if suffix in {
                        ".doc",
                        ".docx",
                        ".pdf",
                        ".ppt",
                        ".pptx",
                        ".txt",
                        ".xls",
                        ".xlsx",
                        ".zip",
                    }:
                        potential_attachment_cache_files += 1
        readable = sum(value.known_schema == "messages_v1" for value in findings)
        attachment_indexes = sum(
            value.readable_attachment_index for value in findings
        )
        opaque = sum(value.database_type == "opaque_or_encrypted" for value in findings)
        return LocalFeishuDiscoveryReport(
            generated_at=datetime.now(UTC).isoformat(),
            client_installed=Path("/Applications/Lark.app").is_dir(),
            client_version=self._client_version(),
            macos_user_hash=hashlib.sha256(
                str(Path.home()).encode("utf-8")
            ).hexdigest(),
            roots_checked=len(self._roots),
            roots_readable=roots_readable,
            database_files=len(findings),
            readable_message_databases=readable,
            readable_attachment_indexes=attachment_indexes,
            opaque_or_encrypted_databases=opaque,
            cache_file_count=cache_file_count,
            potential_attachment_cache_files=potential_attachment_cache_files,
            cache_file_types=dict(sorted(cache_file_types.items())),
            findings=tuple(findings),
        )

    def read_messages(self) -> tuple[LocalFeishuRecord, ...]:
        records: list[LocalFeishuRecord] = []
        for root, database in self._readable_message_databases():
            database_hash = self._relative_hash(root, database)
            with self._connect_read_only(database) as connection:
                rows = connection.execute(
                    """
                    SELECT account_id, chat_id, chat_type, message_id, version,
                           sender_id, message_type, content, create_time, update_time,
                           thread_id, root_id, parent_id
                    FROM messages
                    ORDER BY create_time, message_id
                    """
                ).fetchall()
            for row in rows:
                content = self._json_object(row[7])
                records.append(
                    LocalFeishuRecord(
                        account_id=str(row[0]),
                        chat_id=str(row[1]),
                        chat_type=str(row[2]),
                        message_id=str(row[3]),
                        version=str(row[4]),
                        sender_id=str(row[5]) if row[5] is not None else None,
                        message_type=str(row[6]),
                        content=content,
                        create_time=str(row[8]),
                        update_time=str(row[9]) if row[9] is not None else None,
                        thread_id=str(row[10]) if row[10] is not None else None,
                        root_id=str(row[11]) if row[11] is not None else None,
                        parent_id=str(row[12]) if row[12] is not None else None,
                        database_path_hash=database_hash,
                    )
                )
        return tuple(records)

    def find_attachment(
        self, *, message_id: str, file_key: str
    ) -> LocalFeishuAttachment | None:
        for root, database in self._readable_message_databases():
            with self._connect_read_only(database) as connection:
                if not _ATTACHMENT_COLUMNS.issubset(
                    self._table_columns(connection, "message_attachments")
                ):
                    continue
                row = connection.execute(
                    """
                    SELECT message_id, file_key, file_name, mime_type, size, local_path
                    FROM message_attachments
                    WHERE message_id = ? AND file_key = ?
                    LIMIT 1
                    """,
                    (message_id, file_key),
                ).fetchone()
            if row is None:
                continue
            local_path = Path(str(row[5])).resolve()
            if (
                not local_path.is_file()
                or local_path.is_symlink()
                or not local_path.is_relative_to(root)
            ):
                continue
            return LocalFeishuAttachment(
                message_id=str(row[0]),
                file_key=str(row[1]),
                file_name=str(row[2]),
                mime_type=str(row[3]) if row[3] is not None else None,
                size=int(row[4]) if row[4] is not None else None,
                local_path=local_path,
            )
        return None

    def _readable_message_databases(self) -> tuple[tuple[Path, Path], ...]:
        values: list[tuple[Path, Path]] = []
        for root in self._roots:
            if not root.is_dir() or not os.access(root, os.R_OK):
                continue
            for path in self._iter_safe_files(root):
                if path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
                    continue
                try:
                    with self._connect_read_only(path) as connection:
                        if self._known_schema(root, path, connection) is not None:
                            values.append((root, path))
                except sqlite3.DatabaseError:
                    continue
        return tuple(values)

    def _iter_safe_files(self, root: Path):  # type: ignore[no-untyped-def]
        for directory, names, files in os.walk(root, topdown=True, followlinks=False):
            names[:] = [
                name
                for name in names
                if not self._is_excluded_component(name)
                and not (Path(directory) / name).is_symlink()
            ]
            for name in files:
                path = Path(directory) / name
                if path.is_symlink() or self._is_excluded_component(name):
                    continue
                try:
                    if path.is_file() and os.access(path, os.R_OK):
                        yield path
                except OSError:
                    continue

    def _inspect_database(self, root: Path, path: Path) -> LocalDatabaseFinding:
        stat = path.stat()
        with path.open("rb") as stream:
            header = stream.read(len(_SQLITE_HEADER))
        database_type = "sqlite" if header == _SQLITE_HEADER else "opaque_or_encrypted"
        table_count = 0
        known_schema: str | None = None
        readable_attachment_index = False
        if database_type == "sqlite":
            try:
                with self._connect_read_only(path) as connection:
                    table_count = int(
                        connection.execute(
                            "SELECT count(*) FROM sqlite_master WHERE type = 'table'"
                        ).fetchone()[0]
                    )
                    known_schema = self._known_schema(root, path, connection)
                    readable_attachment_index = known_schema is not None
            except sqlite3.DatabaseError:
                database_type = "opaque_or_encrypted"
        return LocalDatabaseFinding(
            location_type=self._location_type(root),
            relative_path_hash=self._relative_hash(root, path),
            size=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
            database_type=database_type,
            table_count=table_count,
            known_schema=known_schema,
            readable_attachment_index=readable_attachment_index,
        )

    @staticmethod
    def _connect_read_only(path: Path) -> sqlite3.Connection:
        uri = f"file:{quote(str(path))}?mode=ro&immutable=1"
        return sqlite3.connect(uri, uri=True)

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
        if table not in {"messages", "message_attachments"}:
            return set()
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}

    @classmethod
    def _known_schema(
        cls,
        root: Path,
        path: Path,
        connection: sqlite3.Connection,
    ) -> str | None:
        try:
            relative_path = path.relative_to(root).as_posix()
        except ValueError:
            return None
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        for version, supported_paths in _SUPPORTED_MESSAGE_SCHEMA_PATHS.items():
            if relative_path not in supported_paths:
                continue
            if tables != _SUPPORTED_MESSAGE_SCHEMA_TABLES:
                continue
            if cls._table_columns(connection, "messages") != _MESSAGE_COLUMNS:
                continue
            if (
                cls._table_columns(connection, "message_attachments")
                != _ATTACHMENT_COLUMNS
            ):
                continue
            return version
        return None

    @staticmethod
    def _json_object(value: object) -> dict[str, object]:
        if not isinstance(value, str):
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"text": value}
        return parsed if isinstance(parsed, dict) else {"value": parsed}

    @staticmethod
    def _is_excluded_component(value: str) -> bool:
        lowered = value.lower()
        stem = Path(lowered).stem
        return any(
            candidate in (lowered, stem)
            or candidate in lowered.split(".")
            for candidate in _EXCLUDED_COMPONENTS
        )

    @staticmethod
    def _relative_hash(root: Path, path: Path) -> str:
        relative = str(path.relative_to(root))
        return hashlib.sha256(relative.encode("utf-8")).hexdigest()

    @staticmethod
    def _location_type(root: Path) -> str:
        text = str(root)
        if "/Group Containers/" in text:
            return "group_container"
        if "/Containers/" in text:
            return "app_container"
        return "configured_root"

    @staticmethod
    def _client_version() -> str | None:
        info = Path("/Applications/Lark.app/Contents/Info.plist")
        try:
            payload = plistlib.loads(info.read_bytes())
        except (OSError, plistlib.InvalidFileException):
            return None
        value = payload.get("CFBundleShortVersionString")
        return str(value) if value is not None else None


async def _run_host_sync(
    *,
    connector: LocalFeishuConnector,
    authorization_id: UUID,
    confirmed_account_hash: str | None,
) -> dict[str, object]:
    from legal_workbench.application.feishu_handlers import IngestFeishuEventHandler
    from legal_workbench.application.feishu_local_sync import (
        LocalFeishuHostSyncService,
    )
    from legal_workbench.application.feishu_personal_sync import (
        LocalMessageIngestionAdapter,
    )
    from legal_workbench.application.feishu_scopes import FeishuScopeService
    from legal_workbench.infrastructure.database import dispose_engine
    from legal_workbench.infrastructure.unit_of_work import (
        SqlAlchemyUnitOfWorkFactory,
    )

    uow_factory = SqlAlchemyUnitOfWorkFactory()
    try:
        result = await LocalFeishuHostSyncService(
            uow_factory,
            connector=connector,
            scope_service=FeishuScopeService(uow_factory),
            ingestion_adapter=LocalMessageIngestionAdapter(
                IngestFeishuEventHandler(uow_factory)
            ),
        ).sync(
            authorization_id=authorization_id,
            confirmed_account_hash=confirmed_account_hash,
        )
        return result.to_dict()
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover or sync allowlisted local Feishu data read-only"
    )
    parser.add_argument("--root", type=Path, action="append")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--authorization-id", type=UUID)
    parser.add_argument(
        "--account-id-hash",
        help="SHA-256 of the explicitly confirmed local Feishu account ID",
    )
    parser.add_argument(
        "--output",
        type=Path,
    )
    args = parser.parse_args()
    connector = LocalFeishuConnector(
        roots=tuple(args.root) if args.root else None,
    )
    if args.sync:
        if args.authorization_id is None:
            parser.error("--authorization-id is required with --sync")
        payload = asyncio.run(
            _run_host_sync(
                connector=connector,
                authorization_id=args.authorization_id,
                confirmed_account_hash=args.account_id_hash,
            )
        )
        output = args.output or Path("artifacts/feishu-local/host-sync.json")
    else:
        payload = connector.discover().to_dict()
        output = args.output or Path("artifacts/feishu-local/discovery.json")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered + "\n", encoding="utf-8")
    os.chmod(output, 0o600)


if __name__ == "__main__":
    main()
