from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from legal_workbench.integrations.local_knowledge_files import scan_local_knowledge_files


def test_scanner_is_read_only_sorted_and_excludes_runtime_noise(tmp_path: Path) -> None:
    source = tmp_path / "Codex-Obs法务项目"
    source.mkdir()
    included = source / "法规" / "民法典.md"
    included.parent.mkdir()
    included.write_text("第一条 法律正文", encoding="utf-8")
    unsupported = source / "表格.xls"
    unsupported.write_bytes(b"legacy-sheet")
    for directory in (".git", "node_modules", ".venv", "缓存", "build", "备份"):
        ignored = source / directory
        ignored.mkdir()
        (ignored / "ignored.txt").write_text("secret", encoding="utf-8")
    (source / ".hidden.tmp").write_text("secret", encoding="utf-8")
    (source / "~$temporary.docx").write_text("secret", encoding="utf-8")
    before = included.stat()

    scan = scan_local_knowledge_files(source)

    assert [item.relative_path for item in scan.files] == ["法规/民法典.md", "表格.xls"]
    assert scan.files[0].supported is True
    assert scan.files[0].mime_type == "text/markdown"
    assert scan.files[0].content_sha256 == sha256(included.read_bytes()).hexdigest()
    assert scan.files[1].supported is False
    assert scan.files[1].mime_type == "application/octet-stream"
    after = included.stat()
    assert (after.st_mode, after.st_size, after.st_mtime_ns) == (
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )


def test_scanner_never_follows_symlinks_outside_source(tmp_path: Path) -> None:
    source = tmp_path / "Codex-Obs法务项目"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("must not be read", encoding="utf-8")
    (source / "linked.txt").symlink_to(outside)

    scan = scan_local_knowledge_files(source)

    assert scan.files == ()
    assert scan.skipped_symlink_count == 1


def test_scanner_records_single_file_failure_without_stopping_batch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Codex-Obs法务项目"
    source.mkdir()
    first = source / "a.txt"
    second = source / "b.txt"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")
    original_open = Path.open

    def selective_open(path: Path, *args, **kwargs):
        if path == first:
            raise PermissionError("denied sensitive path")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", selective_open)

    scan = scan_local_knowledge_files(source)

    assert [item.relative_path for item in scan.files] == ["b.txt"]
    assert len(scan.failures) == 1
    assert scan.failures[0].relative_path == "a.txt"
    assert scan.failures[0].error_code == "FILE_READ_FAILED"
    assert "denied" not in repr(scan.failures[0])


def test_scanner_rejects_file_provider_noindex_backing_store(tmp_path: Path) -> None:
    source = tmp_path / "OneDrive.noindex" / "Codex-Obs法务项目"
    source.mkdir(parents=True)
    (source / "placeholder.txt").write_text("not a verified source", encoding="utf-8")

    with pytest.raises(ValueError, match="File Provider backing store"):
        scan_local_knowledge_files(source)
