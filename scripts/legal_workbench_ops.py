from __future__ import annotations

import argparse
import fcntl
import hashlib
import http.cookiejar
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol
from uuid import UUID

REAL_FEISHU_PHASE_DEFERRED = "REAL_FEISHU_PHASE_DEFERRED"
SENSITIVE_KEY = re.compile(
    r"(?:secret|token|password|api[_-]?key|authorization|credential)", re.IGNORECASE
)
URL_CREDENTIALS = re.compile(
    r"([a-z][a-z0-9+.-]*://[^\s:/]+:)[^@\s]+(@)", re.IGNORECASE
)
KEY_VALUE_SECRET = re.compile(
    r"((?:secret|token|password|api[_-]?key|authorization|credential)\s*[=:]\s*)"
    r"(?:\"[^\r\n\"]*\"|'[^\r\n']*'|[^\s,;]+)",
    re.IGNORECASE,
)
AUTHORIZATION_SECRET = re.compile(
    r"(authorization\s*[=:]\s*)(?:bearer\s+)?"
    r"(?:\"[^\r\n\"]*\"|'[^\r\n']*'|[^\s,;]+)",
    re.IGNORECASE,
)
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    def run(
        self,
        args: list[str],
        *,
        timeout_seconds: int,
        stdout_path: Path | None = None,
        check: bool = True,
    ) -> CommandResult: ...


class HttpClient(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class OpsConfig:
    repository_root: Path
    state_root: Path
    backup_root: Path
    codex_runs_root: Path
    attachment_root: Path
    postgres_user: str
    postgres_database: str
    api_base_url: str
    backup_retention_days: int = 14
    codex_run_retention_days: int = 14
    attachment_quota_bytes: int = 5 * 1024 * 1024 * 1024
    minimum_disk_free_bytes: int = 5 * 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.repository_root.is_absolute():
            raise ValueError("repository_root must be absolute")
        for path in (
            self.state_root,
            self.backup_root,
            self.codex_runs_root,
            self.attachment_root,
        ):
            if not path.is_absolute():
                raise ValueError("Operations paths must be absolute")
        for value in (self.postgres_user, self.postgres_database):
            if not SAFE_IDENTIFIER.fullmatch(value):
                raise ValueError("PostgreSQL identifiers must contain only safe characters")
        api_url = urllib.parse.urlsplit(self.api_base_url)
        if (
            api_url.scheme not in {"http", "https"}
            or api_url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or api_url.username is not None
            or api_url.password is not None
        ):
            raise ValueError("Operations API URL must use an uncredentialed loopback host")
        if self.backup_retention_days < 1 or self.codex_run_retention_days < 1:
            raise ValueError("Retention periods must be positive")
        if self.attachment_quota_bytes < 1 or self.minimum_disk_free_bytes < 0:
            raise ValueError("Disk thresholds must be non-negative")


@dataclass(frozen=True, slots=True)
class BackupResult:
    path: Path
    size_bytes: int
    sha256: str
    completed_at: datetime


class SubprocessRunner:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.resolve(strict=True)

    def run(
        self,
        args: list[str],
        *,
        timeout_seconds: int,
        stdout_path: Path | None = None,
        check: bool = True,
    ) -> CommandResult:
        if not args or any("\x00" in value for value in args):
            raise ValueError("A valid argument array is required")
        output_handle = None
        try:
            if stdout_path is not None:
                stdout_path.parent.mkdir(parents=True, exist_ok=True)
                flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                flags |= getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(stdout_path, flags, 0o600)
                os.fchmod(descriptor, 0o600)
                output_handle = os.fdopen(descriptor, "wb")
            completed = subprocess.run(
                args,
                cwd=self._repository_root,
                stdin=subprocess.DEVNULL,
                stdout=output_handle or subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
            )
            stdout = ""
            if output_handle is None and isinstance(completed.stdout, bytes):
                stdout = completed.stdout.decode(errors="replace")
            stderr = completed.stderr.decode(errors="replace")
            result = CommandResult(tuple(args), completed.returncode, stdout, stderr)
            if check and completed.returncode != 0:
                raise RuntimeError(
                    f"Command failed with exit code {completed.returncode}: {args[0]}"
                )
            return result
        finally:
            if output_handle is not None:
                output_handle.flush()
                os.fsync(output_handle.fileno())
                output_handle.close()


class LocalApiClient:
    def __init__(self, base_url: str, *, timeout_seconds: int = 15) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        request = urllib.request.Request(
            f"{self._base_url}/{path.lstrip('/')}",
            method=method,
            data=b"" if method in {"POST", "PATCH", "PUT"} else None,
            headers={"Accept": "application/json", **(headers or {})},
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                payload = response.read(2_000_000)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Local API request failed: {path}") from exc
        if not payload:
            return {}
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise TypeError(f"Local API returned a non-object payload: {path}")
        return value


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _append_operation_log(config: OpsConfig, event: Mapping[str, object]) -> None:
    config.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(config.state_root, 0o700)
    log_path = config.state_root / "operations.jsonl"
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(log_path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    os.close(descriptor)
    logger = logging.getLogger("legal_workbench.operations")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    logger.addHandler(handler)
    logger.info(json.dumps(event, ensure_ascii=False, sort_keys=True))
    handler.close()
    logger.handlers.clear()
    os.chmod(log_path, 0o600)


def _redact(value: str, environment: Mapping[str, str]) -> str:
    result = value
    for key, secret in environment.items():
        if SENSITIVE_KEY.search(key):
            result = result.replace(key, "[REDACTED_KEY]")
            if secret:
                result = result.replace(secret, "[REDACTED]")
    result = AUTHORIZATION_SECRET.sub(r"\1[REDACTED]", result)
    result = URL_CREDENTIALS.sub(r"\1[REDACTED]\2", result)
    return KEY_VALUE_SECRET.sub(r"\1[REDACTED]", result)


def _directory_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for base, _directories, files in os.walk(root, followlinks=False):
        for name in files:
            path = Path(base) / name
            try:
                if not path.is_symlink():
                    total += path.stat().st_size
            except OSError:
                continue
    return total


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _disk_status(config: OpsConfig) -> dict[str, object]:
    config.attachment_root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(config.attachment_root)
    attachment_bytes = _directory_bytes(config.attachment_root)
    return {
        "freeBytes": usage.free,
        "totalBytes": usage.total,
        "attachmentBytes": attachment_bytes,
        "attachmentQuotaBytes": config.attachment_quota_bytes,
        "belowMinimum": usage.free < config.minimum_disk_free_bytes,
        "quotaExceeded": attachment_bytes > config.attachment_quota_bytes,
    }


def start_services(
    config: OpsConfig,
    *,
    runner: Runner | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> dict[str, object]:
    active_runner = runner or SubprocessRunner(config.repository_root)
    active_runner.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        timeout_seconds=20,
    )
    active_runner.run(
        [
            "docker",
            "compose",
            "stop",
            "--timeout",
            "30",
            "feishu-connector",
        ],
        timeout_seconds=60,
    )
    active_runner.run(
        [
            "docker",
            "compose",
            "up",
            "-d",
            "postgres",
            "redis",
            "api",
            "worker",
            "scheduler",
            "web",
        ],
        timeout_seconds=180,
    )
    paused_marker = config.state_root / "intake-paused.json"
    if paused_marker.exists():
        paused_marker.unlink()
    result: dict[str, object] = {
        "status": "started",
        "completedAt": now().isoformat(),
        "realFeishuStarted": False,
    }
    _atomic_json(config.state_root / "start-status.json", result)
    _append_operation_log(config, {"event": "start", **result})
    return result


def safe_stop(
    config: OpsConfig,
    *,
    runner: Runner | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> dict[str, object]:
    active_runner = runner or SubprocessRunner(config.repository_root)
    started_at = now()
    _atomic_json(
        config.state_root / "intake-paused.json",
        {"paused": True, "pausedAt": started_at.isoformat()},
    )
    active_runner.run(
        [
            "docker",
            "compose",
            "stop",
            "--timeout",
            "30",
            "feishu-connector",
        ],
        timeout_seconds=60,
    )
    transaction_query = (
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
        "AND pid <> pg_backend_pid() AND state <> 'idle'"
    )
    for attempt in range(10):
        check = active_runner.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                config.postgres_user,
                "-d",
                config.postgres_database,
                "-Atc",
                transaction_query,
            ],
            timeout_seconds=10,
            check=False,
        )
        transaction_count = check.stdout.strip()
        if check.returncode != 0 or not transaction_count.isdigit():
            raise RuntimeError("PostgreSQL active transaction check failed")
        if int(transaction_count) == 0:
            break
        if attempt == 9:
            raise RuntimeError("PostgreSQL active transactions did not drain")
        time.sleep(1)
    active_runner.run(
        [
            "docker",
            "compose",
            "stop",
            "--timeout",
            "60",
            "worker",
            "scheduler",
        ],
        timeout_seconds=90,
    )
    active_runner.run(
        ["docker", "compose", "stop", "--timeout", "30"],
        timeout_seconds=120,
    )
    result: dict[str, object] = {
        "status": "stopped",
        "completedAt": now().isoformat(),
        "intakePausedAt": started_at.isoformat(),
    }
    _atomic_json(config.state_root / "stop-status.json", result)
    _append_operation_log(config, {"event": "stop", **result})
    return result


def backup_postgres(
    config: OpsConfig,
    *,
    runner: Runner | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> BackupResult:
    config.backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(config.backup_root, 0o700)
    lock_path = config.backup_root / ".backup.lock"
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("PostgreSQL backup is already running") from exc
        return _backup_postgres_locked(config, runner=runner, now=now)
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _backup_postgres_locked(
    config: OpsConfig,
    *,
    runner: Runner | None,
    now: Callable[[], datetime],
) -> BackupResult:
    active_runner = runner or SubprocessRunner(config.repository_root)
    completed_at = now()
    status_path = config.state_root / "backup-status.json"
    previous_status: dict[str, object] = {}
    if status_path.is_file() and not status_path.is_symlink():
        try:
            value = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                previous_status = value
        except (OSError, json.JSONDecodeError):
            previous_status = {}
    timestamp = completed_at.strftime("%Y%m%dT%H%M%SZ")
    target = config.backup_root / f"legal-workbench-{timestamp}.dump"
    partial = config.backup_root / f".{target.name}.partial"
    if partial.exists():
        partial.unlink()
    try:
        active_runner.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "-U",
                config.postgres_user,
                "--format=custom",
                "--no-owner",
                "--no-acl",
                config.postgres_database,
            ],
            timeout_seconds=900,
            stdout_path=partial,
        )
        size = partial.stat().st_size
        if size < 1:
            raise RuntimeError("PostgreSQL backup produced an empty dump")
        with partial.open("rb") as stream:
            if stream.read(5) != b"PGDMP":
                raise RuntimeError("PostgreSQL backup does not have a custom-dump header")
        digest = _sha256_file(partial)
        os.chmod(partial, 0o600)
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        last_successful_at = (
            previous_status.get("completedAt")
            if previous_status.get("status") == "succeeded"
            else previous_status.get("lastSuccessfulAt")
        )
        last_successful_name = (
            previous_status.get("fileName")
            if previous_status.get("status") == "succeeded"
            else previous_status.get("lastSuccessfulFileName")
        )
        last_successful_size = (
            previous_status.get("sizeBytes")
            if previous_status.get("status") == "succeeded"
            else previous_status.get("lastSuccessfulSizeBytes")
        )
        failed_status: dict[str, object] = {
            "status": "failed",
            "failedAt": completed_at.isoformat(),
        }
        if isinstance(last_successful_at, str):
            failed_status["lastSuccessfulAt"] = last_successful_at
        if isinstance(last_successful_name, str):
            failed_status["lastSuccessfulFileName"] = last_successful_name
        if isinstance(last_successful_size, int):
            failed_status["lastSuccessfulSizeBytes"] = last_successful_size
        _atomic_json(
            status_path,
            failed_status,
        )
        raise
    cutoff = completed_at - timedelta(days=config.backup_retention_days)
    for candidate in config.backup_root.glob("legal-workbench-*.dump"):
        if candidate == target or candidate.is_symlink():
            continue
        modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=UTC)
        if modified < cutoff:
            candidate.unlink()
    result = BackupResult(target, size, digest, completed_at)
    _atomic_json(
        status_path,
        {
            "status": "succeeded",
            "completedAt": completed_at.isoformat(),
            "fileName": target.name,
            "sizeBytes": size,
            "sha256": digest,
        },
    )
    _append_operation_log(
        config,
        {"event": "backup", "status": "succeeded", "sizeBytes": size},
    )
    return result


def build_diagnostics(
    config: OpsConfig,
    *,
    output_dir: Path,
    runner: Runner | None = None,
    environment: Mapping[str, str] | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> Path:
    active_runner = runner or SubprocessRunner(config.repository_root)
    if environment is not None:
        source_environment = dict(environment)
    else:
        source_environment = dict(os.environ)
        for key, value in _dotenv_values(config.repository_root / ".env").items():
            existing = source_environment.get(key)
            if not existing:
                source_environment[key] = value
            elif value and value != existing:
                # Preserve both potential secret values while keeping the real
                # environment authoritative for non-redaction configuration.
                source_environment[f"DOTENV_{key}"] = value
    if output_dir.is_symlink():
        raise RuntimeError("Diagnostics output directory cannot be a symlink")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_dir, 0o700)
    timestamp = now().strftime("%Y%m%dT%H%M%SZ")
    archive_path = output_dir / f"legal-workbench-diagnostics-{timestamp}.tar.gz"
    commands: dict[str, list[str]] = {
        "docker-info.txt": ["docker", "info", "--format", "{{.ServerVersion}}"],
        "compose-ps.txt": ["docker", "compose", "ps", "--format", "json"],
        "git-status.txt": ["git", "status", "-sb"],
        "git-head.txt": ["git", "log", "-1", "--oneline", "--decorate"],
    }
    with tempfile.TemporaryDirectory(prefix="legal-workbench-diagnostics-") as temp:
        root = Path(temp)
        for file_name, command in commands.items():
            try:
                result = active_runner.run(
                    command,
                    timeout_seconds=30,
                    check=False,
                )
                content = result.stdout or result.stderr
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                content = f"unavailable: {type(exc).__name__}"
            (root / file_name).write_text(
                _redact(content, source_environment), encoding="utf-8"
            )
        state: dict[str, object] = {}
        for state_file in (
            "backup-status.json",
            "wake-status.json",
            "cleanup-status.json",
        ):
            path = config.state_root / state_file
            if path.is_file() and not path.is_symlink():
                try:
                    state[state_file] = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    state[state_file] = {"status": "unreadable"}
        diagnostic = {
            "generatedAt": now().isoformat(),
            "repositoryName": config.repository_root.name,
            "disk": _disk_status(config),
            "operationState": state,
            "environmentIncluded": False,
            "realMessageContentIncluded": False,
        }
        (root / "diagnostic.json").write_text(
            _redact(
                json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, indent=2),
                source_environment,
            ),
            encoding="utf-8",
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".legal-workbench-diagnostics-",
            suffix=".partial",
            dir=output_dir,
        )
        temporary_path = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as output_stream:
                with tarfile.open(fileobj=output_stream, mode="w:gz") as archive:
                    for path in sorted(root.iterdir()):
                        archive.add(path, arcname=path.name, recursive=False)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            temporary_path.replace(archive_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    _append_operation_log(
        config,
        {"event": "diagnostics", "status": "succeeded", "archive": archive_path.name},
    )
    return archive_path


def wake_check(
    config: OpsConfig,
    *,
    runner: Runner | None = None,
    http_client: HttpClient | None = None,
    now: Callable[[], datetime] = _utc_now,
    health_attempts: int = 6,
    health_retry_seconds: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    if health_attempts < 1 or health_retry_seconds < 0:
        raise ValueError("Wake health retry settings are invalid")
    paused_marker = config.state_root / "intake-paused.json"
    if paused_marker.is_file() and not paused_marker.is_symlink():
        paused_report: dict[str, object] = {
            "status": "paused",
            "completedAt": now().isoformat(),
            "realFeishuStarted": False,
            "reason": "MANUAL_SAFE_STOP",
            "feishuReconcile": {
                "state": "not_executed",
                "errorCode": REAL_FEISHU_PHASE_DEFERRED,
            },
        }
        _atomic_json(config.state_root / "wake-status.json", paused_report)
        _append_operation_log(config, {"event": "wake_check", "status": "paused"})
        return paused_report
    active_runner = runner or SubprocessRunner(config.repository_root)
    active_http = http_client or LocalApiClient(config.api_base_url)
    started_at = now()
    active_runner.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        timeout_seconds=20,
    )
    active_runner.run(
        [
            "docker",
            "compose",
            "stop",
            "--timeout",
            "30",
            "feishu-connector",
        ],
        timeout_seconds=60,
    )
    active_runner.run(
        [
            "docker",
            "compose",
            "up",
            "-d",
            "postgres",
            "redis",
            "api",
            "worker",
            "scheduler",
            "web",
        ],
        timeout_seconds=180,
    )
    compose = active_runner.run(
        ["docker", "compose", "ps", "--format", "json"],
        timeout_seconds=30,
    )
    required = (
        "postgresql",
        "redis",
        "celery_worker",
        "celery_scheduler",
        "disk",
    )
    unavailable = list(required)
    ready: dict[str, object] = {}
    system_checks: dict[str, str] = {}
    for attempt in range(health_attempts):
        try:
            ready = active_http.request("GET", "/health/ready")
            active_http.request("POST", "/auth/local-supervisor-session")
            health = active_http.request("GET", "/system/health")
        except RuntimeError:
            unavailable = ["system_health"]
        else:
            components = health.get("components")
            if not isinstance(components, dict):
                raise TypeError("System health did not return component status")
            backup_component = components.get("backup")
            codex = health.get("codex")
            if not isinstance(backup_component, dict) or not isinstance(codex, dict):
                raise TypeError("System health omitted backup or Codex status")
            backup_status = backup_component.get("status")
            codex_status = codex.get("status")
            disk_component = components.get("disk")
            disk_status = (
                disk_component.get("status")
                if isinstance(disk_component, dict)
                else None
            )
            if (
                not isinstance(backup_status, str)
                or not isinstance(codex_status, str)
                or not isinstance(disk_status, str)
            ):
                raise TypeError("System health returned an invalid resource status")
            system_checks = {
                "backupStatus": backup_status,
                "codexStatus": codex_status,
                "diskStatus": disk_status,
            }
            unavailable = [
                name
                for name in required
                if not isinstance(components.get(name), dict)
                or components[name].get("status") != "normal"
            ]
        if not unavailable:
            break
        if attempt + 1 < health_attempts:
            sleep(health_retry_seconds)
    else:
        raise RuntimeError(f"Wake health check failed: {', '.join(unavailable)}")
    key = f"wake-recovery:{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    recovery = active_http.request(
        "POST",
        "/system/recover-pending-jobs",
        headers={"Idempotency-Key": key, "X-Correlation-ID": key},
    )
    backup_state: dict[str, object] = {"status": "unknown"}
    backup_path = config.state_root / "backup-status.json"
    if backup_path.is_file() and not backup_path.is_symlink():
        try:
            value = json.loads(backup_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                backup_state = value
        except (OSError, json.JSONDecodeError):
            backup_state = {"status": "unreadable"}
    warning_statuses = [
        name
        for name, value in (
            ("backup", system_checks["backupStatus"]),
            ("codex", system_checks["codexStatus"]),
        )
        if value not in {"normal", "available", "ready"}
    ]
    report: dict[str, object] = {
        "status": "degraded" if warning_statuses else "ready",
        "startedAt": started_at.isoformat(),
        "completedAt": now().isoformat(),
        "docker": {"status": "ready"},
        "compose": {"status": "ready", "outputPresent": bool(compose.stdout)},
        "apiReady": ready,
        "systemChecks": system_checks,
        "warnings": warning_statuses,
        "postgresRecovery": recovery,
        "feishuReconcile": {
            "state": "not_executed",
            "errorCode": REAL_FEISHU_PHASE_DEFERRED,
        },
        "disk": _disk_status(config),
        "backup": backup_state,
    }
    _atomic_json(config.state_root / "wake-status.json", report)
    _append_operation_log(
        config,
        {"event": "wake_check", "status": report["status"]},
    )
    return report


def cleanup_runtime_data(
    config: OpsConfig,
    *,
    runner: Runner | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> dict[str, object]:
    active_runner = runner or SubprocessRunner(config.repository_root)
    if config.codex_runs_root.is_symlink():
        raise RuntimeError("Codex run cleanup root cannot be a symlink")
    root = config.codex_runs_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    query = (
        "SELECT working_directory FROM agent_runs WHERE status IN "
        "('queued','preparing','running','validating')"
    )
    active_result = active_runner.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            config.postgres_user,
            "-d",
            config.postgres_database,
            "-Atc",
            query,
        ],
        timeout_seconds=30,
    )
    active_run_ids: set[str] = set()
    for line in active_result.stdout.splitlines():
        for part in Path(line.strip()).parts:
            try:
                active_run_ids.add(str(UUID(part)))
            except ValueError:
                continue
    cutoff = now() - timedelta(days=config.codex_run_retention_days)
    removed = 0
    for candidate in root.iterdir():
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        try:
            run_id = str(UUID(candidate.name))
        except ValueError:
            continue
        if run_id in active_run_ids:
            continue
        modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=UTC)
        if modified >= cutoff:
            continue
        resolved = candidate.resolve(strict=True)
        if resolved.parent != root:
            continue
        shutil.rmtree(resolved)
        removed += 1
    result: dict[str, object] = {
        "status": "completed",
        "completedAt": now().isoformat(),
        "codexRunDirectoriesRemoved": removed,
        "disk": _disk_status(config),
    }
    _atomic_json(config.state_root / "cleanup-status.json", result)
    _append_operation_log(config, {"event": "cleanup", **result})
    return result


def _dotenv_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def default_config(repository_root: Path | None = None) -> OpsConfig:
    root = (repository_root or Path(__file__).resolve().parents[1]).resolve(strict=True)
    dotenv = _dotenv_values(root / ".env")
    env = {**dotenv, **os.environ}

    def host_path(key: str, default: Path) -> Path:
        configured = env.get(key)
        if configured is None:
            return default.resolve()
        path = Path(configured)
        if not path.is_absolute():
            raise ValueError(f"{key} must be an absolute host path")
        return path.resolve()

    return OpsConfig(
        repository_root=root,
        state_root=host_path(
            "LEGAL_WORKBENCH_OPS_STATE_ROOT", root / "data/operations"
        ),
        backup_root=host_path(
            "LEGAL_WORKBENCH_OPS_BACKUP_ROOT", root / "data/backups"
        ),
        codex_runs_root=host_path(
            "LEGAL_WORKBENCH_OPS_CODEX_RUNS_ROOT", root / "data/codex-runs"
        ),
        attachment_root=host_path(
            "LEGAL_WORKBENCH_OPS_ATTACHMENT_ROOT",
            root / "data/feishu-attachments",
        ),
        postgres_user=env.get("POSTGRES_USER", "legal_workbench"),
        postgres_database=env.get("POSTGRES_DB", "legal_workbench"),
        api_base_url=(
            env.get(
                "LEGAL_WORKBENCH_OPERATIONS_API_BASE_URL",
                f"http://127.0.0.1:{env.get('API_PORT', '8000')}/api/v1",
            )
        ),
        backup_retention_days=int(
            env.get("LEGAL_WORKBENCH_BACKUP_RETENTION_DAYS", "14")
        ),
        codex_run_retention_days=int(
            env.get("LEGAL_WORKBENCH_CODEX_RUN_RETENTION_DAYS", "14")
        ),
        attachment_quota_bytes=int(
            env.get(
                "LEGAL_WORKBENCH_FEISHU_ATTACHMENT_TOTAL_QUOTA_BYTES",
                str(5 * 1024 * 1024 * 1024),
            )
        ),
        minimum_disk_free_bytes=int(
            env.get(
                "LEGAL_WORKBENCH_MINIMUM_DISK_FREE_BYTES",
                str(5 * 1024 * 1024 * 1024),
            )
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Legal Workbench local Mac operations")
    parser.add_argument(
        "command",
        choices=("start", "stop", "wake-check", "backup", "diagnostics", "cleanup"),
    )
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    config: OpsConfig | None = None
    try:
        config = default_config(args.repository_root)
        if args.command == "start":
            result: object = start_services(config)
        elif args.command == "stop":
            result = safe_stop(config)
        elif args.command == "wake-check":
            result = wake_check(config)
        elif args.command == "backup":
            result = asdict(backup_postgres(config))
        elif args.command == "diagnostics":
            result = {
                "archive": str(
                    build_diagnostics(
                        config,
                        output_dir=(
                            args.output_dir or config.state_root / "diagnostics"
                        ).resolve(),
                    )
                )
            }
        else:
            result = cleanup_runtime_data(config)
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        tarfile.TarError,
        urllib.error.URLError,
    ) as exc:
        failure: dict[str, object] = {
            "status": "failed",
            "command": args.command,
            "errorType": type(exc).__name__,
        }
        if config is not None:
            try:
                _append_operation_log(config, {"event": "command_failed", **failure})
            except (OSError, RuntimeError, TypeError, ValueError):
                # The CLI response remains useful even when the operation log's
                # disk is unavailable. Never echo the original exception text.
                failure["operationLogStatus"] = "unavailable"
        print(json.dumps(failure, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
