from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

SUPPORTED_MIME_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}

EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".cache",
        "cache",
        "caches",
        "缓存",
        "build",
        "dist",
        "out",
        "target",
        "coverage",
        "backup",
        "backups",
        "bak",
        "备份",
        "重复备份",
    }
)


@dataclass(frozen=True, slots=True)
class LocalKnowledgeFile:
    relative_path: str
    display_name: str
    extension: str
    mime_type: str
    size: int
    modified_at_ns: int
    content_sha256: str
    supported: bool
    absolute_path: Path = field(repr=False)


@dataclass(frozen=True, slots=True)
class LocalKnowledgeFileFailure:
    relative_path: str
    error_code: str


@dataclass(frozen=True, slots=True)
class LocalKnowledgeFileScan:
    files: tuple[LocalKnowledgeFile, ...]
    failures: tuple[LocalKnowledgeFileFailure, ...]
    skipped_symlink_count: int


def scan_local_knowledge_files(source: Path) -> LocalKnowledgeFileScan:
    root = source.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError("Local knowledge source must be a directory.")
    files: list[LocalKnowledgeFile] = []
    failures: list[LocalKnowledgeFileFailure] = []
    skipped_symlinks = 0

    def visit(directory: Path) -> None:
        nonlocal skipped_symlinks
        try:
            children = sorted(directory.iterdir(), key=lambda value: value.name.casefold())
        except OSError:
            relative = directory.relative_to(root).as_posix() or "."
            failures.append(LocalKnowledgeFileFailure(relative, "DIRECTORY_READ_FAILED"))
            return
        for child in children:
            relative_path = child.relative_to(root).as_posix()
            try:
                if child.is_symlink():
                    skipped_symlinks += 1
                    continue
                if child.is_dir():
                    if _exclude_directory(child.name):
                        continue
                    visit(child)
                    continue
                if not child.is_file() or _exclude_file(child.name):
                    continue
                before = child.stat()
                digest = _sha256_file(child)
                after = child.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    failures.append(
                        LocalKnowledgeFileFailure(relative_path, "FILE_CHANGED_DURING_SCAN")
                    )
                    continue
            except OSError:
                failures.append(LocalKnowledgeFileFailure(relative_path, "FILE_READ_FAILED"))
                continue
            extension = child.suffix.casefold()
            mime_type = SUPPORTED_MIME_TYPES.get(extension, "application/octet-stream")
            files.append(
                LocalKnowledgeFile(
                    relative_path=relative_path,
                    display_name=child.name,
                    extension=extension,
                    mime_type=mime_type,
                    size=after.st_size,
                    modified_at_ns=after.st_mtime_ns,
                    content_sha256=digest,
                    supported=extension in SUPPORTED_MIME_TYPES,
                    absolute_path=child,
                )
            )

    visit(root)
    return LocalKnowledgeFileScan(
        files=tuple(sorted(files, key=lambda value: value.relative_path.casefold())),
        failures=tuple(sorted(failures, key=lambda value: value.relative_path.casefold())),
        skipped_symlink_count=skipped_symlinks,
    )


def _exclude_directory(name: str) -> bool:
    normalized = name.casefold()
    return (
        normalized.startswith(".")
        or normalized in EXCLUDED_DIRECTORY_NAMES
        or normalized.endswith((".backup", "-backup", "_backup", "-备份", "_备份"))
    )


def _exclude_file(name: str) -> bool:
    return name.startswith((".", "~$", ".~", "#")) or name.endswith(("~", ".tmp", ".temp"))


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
