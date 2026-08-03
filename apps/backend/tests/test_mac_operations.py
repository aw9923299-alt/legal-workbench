from __future__ import annotations

import asyncio
import fcntl
import json
import os
import subprocess
import sys
import tarfile
from argparse import Namespace
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import scripts.legal_workbench_ops as operations
import scripts.smoke_test_codex_triage as triage_smoke
import scripts.smoke_test_downstream_loop as downstream_smoke
import yaml
from scripts.legal_workbench_ops import (
    CommandResult,
    OpsConfig,
    SubprocessRunner,
    backup_postgres,
    build_diagnostics,
    cleanup_runtime_data,
    safe_stop,
    wake_check,
)
from scripts.smoke_test_downstream_loop import run as run_downstream_smoke

from legal_workbench.infrastructure.system_status import SystemStatusService

NOW = datetime(2026, 8, 3, 8, 30, tzinfo=UTC)


class RecordingRunner:
    def __init__(self, outputs: dict[tuple[str, ...], str] | None = None) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.outputs = outputs or {}

    def run(
        self,
        args: list[str],
        *,
        timeout_seconds: int,
        stdout_path: Path | None = None,
        check: bool = True,
    ) -> CommandResult:
        del timeout_seconds, check
        command = tuple(args)
        self.commands.append(command)
        output = self.outputs.get(command, "ok")
        if stdout_path is not None:
            stdout_path.write_bytes(output.encode())
            output = ""
        return CommandResult(args=command, returncode=0, stdout=output, stderr="")


class RecordingHttpClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, str]]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        self.requests.append((method, path, headers or {}))
        if path == "/system/health":
            return {
                "components": {
                    name: {"status": "normal"}
                    for name in (
                        "postgresql",
                        "redis",
                        "celery_worker",
                        "celery_scheduler",
                        "disk",
                        "backup",
                    )
                },
                "codex": {"status": "unauthenticated"},
            }
        if path == "/system/recover-pending-jobs":
            return {
                "missingRunsRequeued": 2,
                "staleRunsRequeued": 1,
                "deadLettered": 0,
            }
        return {"status": "ok"}


class DelayedHealthHttpClient(RecordingHttpClient):
    def __init__(self) -> None:
        super().__init__()
        self.health_calls = 0

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        if path != "/system/health":
            return super().request(method, path, headers=headers)
        self.requests.append((method, path, headers or {}))
        self.health_calls += 1
        status = "degraded" if self.health_calls == 1 else "normal"
        return {
            "components": {
                name: {"status": status if name == "celery_worker" else "normal"}
                for name in (
                    "postgresql",
                    "redis",
                    "celery_worker",
                    "celery_scheduler",
                    "disk",
                    "backup",
                )
            },
            "codex": {"status": "unauthenticated"},
        }


class TemporarilyUnavailableApiClient(RecordingHttpClient):
    def __init__(self) -> None:
        super().__init__()
        self.ready_calls = 0

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        if path == "/health/ready":
            self.ready_calls += 1
            if self.ready_calls == 1:
                raise RuntimeError("API is starting")
        return super().request(method, path, headers=headers)


class UnsafeDiskHttpClient(RecordingHttpClient):
    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        result = super().request(method, path, headers=headers)
        if path == "/system/health":
            components = result["components"]
            assert isinstance(components, dict)
            components["disk"] = {"status": "degraded"}
        return result


class UnavailableDatabaseRunner(RecordingRunner):
    def run(
        self,
        args: list[str],
        *,
        timeout_seconds: int,
        stdout_path: Path | None = None,
        check: bool = True,
    ) -> CommandResult:
        if "psql" in args:
            self.commands.append(tuple(args))
            if check:
                raise RuntimeError("database unavailable")
            return CommandResult(tuple(args), 1, "", "database unavailable")
        return super().run(
            args,
            timeout_seconds=timeout_seconds,
            stdout_path=stdout_path,
            check=check,
        )


def config(tmp_path: Path) -> OpsConfig:
    repository = tmp_path / "repository"
    repository.mkdir()
    return OpsConfig(
        repository_root=repository,
        state_root=tmp_path / "operations",
        backup_root=tmp_path / "backups",
        codex_runs_root=tmp_path / "codex-runs",
        attachment_root=tmp_path / "attachments",
        postgres_user="legal_workbench",
        postgres_database="legal_workbench",
        api_base_url="http://127.0.0.1:8000/api/v1",
        backup_retention_days=7,
        codex_run_retention_days=7,
        attachment_quota_bytes=1_000_000,
        minimum_disk_free_bytes=1,
    )


def test_operations_api_must_be_loopback(tmp_path: Path) -> None:
    cfg = config(tmp_path)

    with pytest.raises(ValueError, match="loopback"):
        OpsConfig(
            repository_root=cfg.repository_root,
            state_root=cfg.state_root,
            backup_root=cfg.backup_root,
            codex_runs_root=cfg.codex_runs_root,
            attachment_root=cfg.attachment_root,
            postgres_user=cfg.postgres_user,
            postgres_database=cfg.postgres_database,
            api_base_url="https://example.invalid/api/v1",
        )

    with pytest.raises(ValueError, match="absolute"):
        replace(cfg, backup_root=Path("relative-backups"))


def archive_text(path: Path) -> str:
    values: list[str] = []
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            stream = archive.extractfile(member)
            if stream is not None:
                values.append(stream.read().decode(errors="replace"))
    return "\n".join(values)


def test_diagnostics_redacts_credentials_and_never_archives_environment(
    tmp_path: Path,
) -> None:
    cfg = config(tmp_path)
    runner = RecordingRunner(
        {
            ("docker", "compose", "ps", "--format", "json"): (
                'app_secret=app-secret OPENAI_API_KEY=runtime-secret '
                'postgresql://user:password@localhost/db '
                'Authorization: Bearer dynamic-token '
                'client_secret="space separated secret"'
            ),
        }
    )

    archive = build_diagnostics(
        cfg,
        output_dir=tmp_path / "diagnostics",
        runner=runner,
        environment={
            "LEGAL_WORKBENCH_FEISHU_APP_SECRET": "app-secret",
            "OPENAI_API_KEY": "runtime-secret",
        },
        now=lambda: NOW,
    )
    text = archive_text(archive)

    assert "app-secret" not in text
    assert "runtime-secret" not in text
    assert "OPENAI_API_KEY" not in text
    assert "postgresql://user:password" not in text
    assert "dynamic-token" not in text
    assert "space separated secret" not in text
    assert "[REDACTED]" in text


def test_diagnostics_loads_local_dotenv_only_for_secret_redaction(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    (cfg.repository_root / ".env").write_text(
        "LEGAL_WORKBENCH_FEISHU_APP_SECRET=dotenv-secret-value\n"
    )
    runner = RecordingRunner(
        {("git", "status", "-sb"): "unexpected dotenv-secret-value output"}
    )

    archive = build_diagnostics(
        cfg,
        output_dir=tmp_path / "diagnostics",
        runner=runner,
        now=lambda: NOW,
    )
    text = archive_text(archive)

    assert "dotenv-secret-value" not in text
    assert "LEGAL_WORKBENCH_FEISHU_APP_SECRET" not in text
    assert "environmentIncluded\": false" in text


def test_diagnostics_never_follows_preexisting_archive_symlink(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    output = tmp_path / "diagnostics"
    output.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("keep-me")
    archive_path = output / "legal-workbench-diagnostics-20260803T083000Z.tar.gz"
    archive_path.symlink_to(victim)

    result = build_diagnostics(
        cfg,
        output_dir=output,
        runner=RecordingRunner(),
        environment={},
        now=lambda: NOW,
    )

    assert victim.read_text() == "keep-me"
    assert result == archive_path
    assert not result.is_symlink()
    assert result.stat().st_mode & 0o777 == 0o600


def test_backup_is_nonempty_atomic_and_prunes_only_expired_dumps(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    cfg.backup_root.mkdir(parents=True)
    old = cfg.backup_root / "legal-workbench-20260701T000000Z.dump"
    current = cfg.backup_root / "legal-workbench-20260801T000000Z.dump"
    old.write_bytes(b"old")
    current.write_bytes(b"current")
    os.utime(old, ((NOW - timedelta(days=40)).timestamp(),) * 2)
    os.utime(current, ((NOW - timedelta(days=2)).timestamp(),) * 2)

    dump_runner = RecordingRunner()
    dump_runner.outputs = {
        (
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            "legal_workbench",
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "legal_workbench",
        ): "PGDMPok"
    }
    result = backup_postgres(cfg, runner=dump_runner, now=lambda: NOW)

    assert result.path.exists()
    assert result.path.read_bytes() == b"PGDMPok"
    assert not old.exists()
    assert current.exists()
    assert not list(cfg.backup_root.glob("*.partial"))
    metadata = json.loads((cfg.state_root / "backup-status.json").read_text())
    assert metadata["status"] == "succeeded"
    assert metadata["sizeBytes"] == 7
    assert metadata["sha256"] == result.sha256
    assert result.path.stat().st_mode & 0o777 == 0o600
    assert (cfg.state_root / "operations.jsonl").stat().st_mode & 0o777 == 0o600


def test_subprocess_file_output_is_private_from_creation(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    output = tmp_path / "private-output.bin"

    result = SubprocessRunner(cfg.repository_root).run(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'PGDMP')"],
        timeout_seconds=10,
        stdout_path=output,
    )

    assert result.returncode == 0
    assert output.read_bytes() == b"PGDMP"
    assert output.stat().st_mode & 0o777 == 0o600


def test_backup_rejects_non_custom_dump_and_removes_partial(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    runner = RecordingRunner()

    with pytest.raises(RuntimeError, match="custom-dump header"):
        backup_postgres(cfg, runner=runner, now=lambda: NOW)

    assert not list(cfg.backup_root.glob("*.partial"))
    metadata = json.loads((cfg.state_root / "backup-status.json").read_text())
    assert metadata == {"failedAt": NOW.isoformat(), "status": "failed"}


def test_failed_backup_preserves_last_successful_backup_metadata(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    cfg.state_root.mkdir(parents=True)
    previous_at = NOW - timedelta(days=1)
    previous_name = "legal-workbench-20260802T083000Z.dump"
    (cfg.state_root / "backup-status.json").write_text(
        json.dumps(
            {
                "status": "succeeded",
                "completedAt": previous_at.isoformat(),
                "fileName": previous_name,
                "sizeBytes": 100,
            }
        )
    )

    with pytest.raises(RuntimeError, match="custom-dump header"):
        backup_postgres(cfg, runner=RecordingRunner(), now=lambda: NOW)

    metadata = json.loads((cfg.state_root / "backup-status.json").read_text())
    assert metadata["status"] == "failed"
    assert metadata["lastSuccessfulAt"] == previous_at.isoformat()
    assert metadata["lastSuccessfulFileName"] == previous_name
    assert metadata["lastSuccessfulSizeBytes"] == 100


def test_backup_rejects_overlapping_process_without_touching_status(
    tmp_path: Path,
) -> None:
    cfg = config(tmp_path)
    cfg.backup_root.mkdir(parents=True)
    lock_path = cfg.backup_root / ".backup.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    runner = RecordingRunner()

    try:
        with pytest.raises(RuntimeError, match="already running"):
            backup_postgres(cfg, runner=runner, now=lambda: NOW)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    assert runner.commands == []
    assert not (cfg.state_root / "backup-status.json").exists()


def test_safe_stop_disables_intake_before_worker_and_compose(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    transaction_command = (
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "legal_workbench",
        "-d",
        "legal_workbench",
        "-Atc",
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
        "AND pid <> pg_backend_pid() AND state <> 'idle'",
    )
    runner = RecordingRunner({transaction_command: "0"})

    result = safe_stop(cfg, runner=runner, now=lambda: NOW)

    assert (cfg.state_root / "intake-paused.json").exists()
    assert runner.commands[0] == (
        "docker",
        "compose",
        "stop",
        "--timeout",
        "30",
        "feishu-connector",
    )
    assert runner.commands[1][:5] == (
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
    )
    assert runner.commands[2] == (
        "docker",
        "compose",
        "stop",
        "--timeout",
        "60",
        "worker",
        "scheduler",
    )
    assert runner.commands[3] == (
        "docker",
        "compose",
        "stop",
        "--timeout",
        "30",
    )
    assert result["status"] == "stopped"


def test_safe_stop_leaves_services_running_when_transaction_check_fails(
    tmp_path: Path,
) -> None:
    cfg = config(tmp_path)
    runner = RecordingRunner()

    with pytest.raises(RuntimeError, match="transaction check"):
        safe_stop(cfg, runner=runner, now=lambda: NOW)

    assert (cfg.state_root / "intake-paused.json").exists()
    assert not any(command[-2:] == ("worker", "scheduler") for command in runner.commands)


def test_wake_check_recovers_postgres_work_and_marks_feishu_deferred(
    tmp_path: Path,
) -> None:
    cfg = config(tmp_path)
    runner = RecordingRunner()
    http = RecordingHttpClient()

    report = wake_check(
        cfg,
        runner=runner,
        http_client=http,
        now=lambda: NOW,
    )

    assert runner.commands[:4] == [
        ("docker", "info", "--format", "{{.ServerVersion}}"),
        (
            "docker",
            "compose",
            "stop",
            "--timeout",
            "30",
            "feishu-connector",
        ),
        (
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
        ),
        ("docker", "compose", "ps", "--format", "json"),
    ]
    assert [value[:2] for value in http.requests] == [
        ("GET", "/health/ready"),
        ("POST", "/auth/local-supervisor-session"),
        ("GET", "/system/health"),
        ("POST", "/system/recover-pending-jobs"),
    ]
    assert report["status"] == "degraded"
    assert report["postgresRecovery"]["missingRunsRequeued"] == 2
    assert report["feishuReconcile"] == {
        "state": "not_executed",
        "errorCode": "REAL_FEISHU_PHASE_DEFERRED",
    }
    assert report["disk"]["freeBytes"] > 0
    assert report["systemChecks"] == {
        "backupStatus": "normal",
        "codexStatus": "unauthenticated",
        "diskStatus": "normal",
    }
    assert (cfg.state_root / "wake-status.json").exists()


def test_wake_check_retries_while_single_worker_is_starting(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    http = DelayedHealthHttpClient()
    delays: list[float] = []

    report = wake_check(
        cfg,
        runner=RecordingRunner(),
        http_client=http,
        now=lambda: NOW,
        health_attempts=3,
        health_retry_seconds=0.01,
        sleep=delays.append,
    )

    assert report["status"] == "degraded"
    assert http.health_calls == 2
    assert delays == [0.01]


def test_wake_check_retries_api_readiness(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    http = TemporarilyUnavailableApiClient()
    delays: list[float] = []

    report = wake_check(
        cfg,
        runner=RecordingRunner(),
        http_client=http,
        now=lambda: NOW,
        health_attempts=3,
        health_retry_seconds=0.01,
        sleep=delays.append,
    )

    assert report["status"] == "degraded"
    assert http.ready_calls == 2
    assert delays == [0.01]


def test_wake_check_blocks_recovery_when_disk_is_degraded(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    http = UnsafeDiskHttpClient()

    with pytest.raises(RuntimeError, match="disk"):
        wake_check(
            cfg,
            runner=RecordingRunner(),
            http_client=http,
            now=lambda: NOW,
            health_attempts=1,
            health_retry_seconds=0,
        )

    assert not any(path == "/system/recover-pending-jobs" for _, path, _ in http.requests)


def test_wake_check_respects_manual_safe_stop(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    cfg.state_root.mkdir(parents=True)
    (cfg.state_root / "intake-paused.json").write_text(
        json.dumps({"paused": True, "pausedAt": NOW.isoformat()})
    )
    runner = RecordingRunner()

    report = wake_check(cfg, runner=runner, now=lambda: NOW)

    assert report["status"] == "paused"
    assert report["realFeishuStarted"] is False
    assert runner.commands == []


def test_cleanup_preserves_active_or_recent_codex_runs(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    cfg.codex_runs_root.mkdir(parents=True)
    active = cfg.codex_runs_root / "00000000-0000-0000-0000-000000000001"
    expired = cfg.codex_runs_root / "00000000-0000-0000-0000-000000000002"
    recent = cfg.codex_runs_root / "00000000-0000-0000-0000-000000000003"
    unrelated = cfg.codex_runs_root / "do-not-touch"
    for value in (active, expired, recent, unrelated):
        value.mkdir()
        (value / "metadata.json").write_text("{}")
    old_time = (NOW - timedelta(days=40)).timestamp()
    for value in (active, expired, unrelated):
        os.utime(value, (old_time, old_time))
    runner = RecordingRunner(
        {
            (
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "legal_workbench",
                "-d",
                "legal_workbench",
                "-Atc",
                "SELECT working_directory FROM agent_runs WHERE status IN "
                "('queued','preparing','running','validating')",
            ): str(active / "attempt-1"),
        }
    )

    result = cleanup_runtime_data(cfg, runner=runner, now=lambda: NOW)

    assert active.exists()
    assert recent.exists()
    assert unrelated.exists()
    assert not expired.exists()
    assert result["codexRunDirectoriesRemoved"] == 1


def test_cleanup_refuses_to_delete_when_postgres_active_run_query_fails(
    tmp_path: Path,
) -> None:
    cfg = config(tmp_path)
    cfg.codex_runs_root.mkdir(parents=True)
    expired = cfg.codex_runs_root / "00000000-0000-0000-0000-000000000002"
    expired.mkdir()
    old_time = (NOW - timedelta(days=40)).timestamp()
    os.utime(expired, (old_time, old_time))

    with pytest.raises(RuntimeError, match="database unavailable"):
        cleanup_runtime_data(
            cfg,
            runner=UnavailableDatabaseRunner(),
            now=lambda: NOW,
        )

    assert expired.exists()


def test_cleanup_rejects_symlinked_codex_run_root(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    actual_root = tmp_path / "actual-codex-runs"
    actual_root.mkdir()
    symlink_root = tmp_path / "codex-runs-link"
    symlink_root.symlink_to(actual_root, target_is_directory=True)
    linked_config = replace(cfg, codex_runs_root=symlink_root)

    with pytest.raises(RuntimeError, match="symlink"):
        cleanup_runtime_data(
            linked_config,
            runner=RecordingRunner(),
            now=lambda: NOW,
        )


def test_compose_rotates_logs_for_every_service() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    compose = yaml.safe_load((repository_root / "compose.yml").read_text())

    for name, service in compose["services"].items():
        assert service["logging"] == {
            "driver": "json-file",
            "options": {"max-size": "10m", "max-file": "3"},
        }, name


def test_compose_host_operation_overrides_drive_bind_sources() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    compose = yaml.safe_load((repository_root / "compose.yml").read_text())

    api_volumes = compose["services"]["api"]["volumes"]
    worker_volumes = compose["services"]["worker"]["volumes"]
    connector_volumes = compose["services"]["feishu-connector"]["volumes"]
    assert (
        "${LEGAL_WORKBENCH_OPS_STATE_ROOT:-./data/operations}:/data/operations:ro"
        in api_volumes
    )
    assert (
        "${LEGAL_WORKBENCH_OPS_BACKUP_ROOT:-./data/backups}:/data/backups:ro"
        in api_volumes
    )
    codex_volume = (
        "${LEGAL_WORKBENCH_OPS_CODEX_RUNS_ROOT:-./data/codex-runs}:/data/codex-runs"
    )
    attachment_volume = (
        "${LEGAL_WORKBENCH_OPS_ATTACHMENT_ROOT:-./data/feishu-attachments}:"
        "/data/feishu-attachments"
    )
    assert codex_volume in api_volumes
    assert codex_volume in worker_volumes
    assert attachment_volume in api_volumes
    assert attachment_volume in worker_volumes
    assert attachment_volume in connector_volumes


def test_system_status_reads_disk_backup_and_wake_metadata(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    cfg.attachment_root.mkdir(parents=True)
    (cfg.attachment_root / "synthetic.txt").write_bytes(b"abc")
    cfg.state_root.mkdir(parents=True)
    cfg.backup_root.mkdir(parents=True)
    dump = cfg.backup_root / "legal-workbench-20260803T083000Z.dump"
    dump.write_bytes(b"PGDMPok")
    (cfg.state_root / "backup-status.json").write_text(
        json.dumps(
            {
                "status": "succeeded",
                "completedAt": NOW.isoformat(),
                "fileName": dump.name,
                "sizeBytes": dump.stat().st_size,
            }
        )
    )
    (cfg.state_root / "wake-status.json").write_text(
        json.dumps({"status": "ready", "completedAt": NOW.isoformat()})
    )
    service = SystemStatusService(
        operations_state_root=cfg.state_root,
        backup_root=cfg.backup_root,
        attachment_root=cfg.attachment_root,
        attachment_quota_bytes=cfg.attachment_quota_bytes,
        minimum_disk_free_bytes=1,
        backup_max_age_hours=36,
    )

    status = service._local_operations_status(NOW)

    assert status.disk_component.status == "normal"
    assert status.backup_component.status == "normal"
    assert status.attachment_bytes_used == 3
    assert status.last_backup_at == NOW
    assert status.last_backup_status == "succeeded"
    assert status.last_wake_check_at == NOW


def test_system_status_degrades_when_backup_metadata_has_no_dump(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    cfg.state_root.mkdir(parents=True)
    (cfg.state_root / "backup-status.json").write_text(
        json.dumps(
            {
                "status": "succeeded",
                "completedAt": NOW.isoformat(),
                "fileName": "legal-workbench-missing.dump",
                "sizeBytes": 100,
            }
        )
    )
    service = SystemStatusService(
        operations_state_root=cfg.state_root,
        backup_root=cfg.backup_root,
        attachment_root=cfg.attachment_root,
        minimum_disk_free_bytes=1,
    )

    status = service._local_operations_status(NOW)

    assert status.backup_component.status == "degraded"
    assert status.last_backup_status == "missing"


def test_system_status_rejects_backup_with_invalid_custom_dump_header(
    tmp_path: Path,
) -> None:
    cfg = config(tmp_path)
    cfg.state_root.mkdir(parents=True)
    cfg.backup_root.mkdir(parents=True)
    dump = cfg.backup_root / "legal-workbench-20260803T083000Z.dump"
    dump.write_bytes(b"broken!")
    (cfg.state_root / "backup-status.json").write_text(
        json.dumps(
            {
                "status": "succeeded",
                "completedAt": NOW.isoformat(),
                "fileName": dump.name,
                "sizeBytes": dump.stat().st_size,
            }
        )
    )
    service = SystemStatusService(
        operations_state_root=cfg.state_root,
        backup_root=cfg.backup_root,
        attachment_root=cfg.attachment_root,
        minimum_disk_free_bytes=1,
    )

    status = service._local_operations_status(NOW)

    assert status.backup_component.status == "degraded"
    assert status.last_backup_status == "missing"


def test_downstream_smoke_requires_write_and_real_runtime_gates(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    common = {
        "repository_root": repository,
        "database_url": "postgresql+psycopg://synthetic.invalid/test",
        "runtime": "fake",
        "allow_real_runtime": False,
        "allow_database_write": False,
        "allow_redis_flush": False,
        "redis_url": "redis://127.0.0.1:6379/15",
    }

    with pytest.raises(ValueError, match="allow-database-write"):
        run_downstream_smoke(Namespace(**common))
    with pytest.raises(ValueError, match="allow-real-runtime"):
        run_downstream_smoke(
            Namespace(
                **{
                    **common,
                    "runtime": "real",
                    "allow_database_write": True,
                    "allow_redis_flush": True,
                }
            )
        )
    with pytest.raises(ValueError, match="allow-redis-flush"):
        run_downstream_smoke(
            Namespace(
                **{
                    **common,
                    "allow_database_write": True,
                }
            )
        )


@pytest.mark.parametrize(
    "redis_url",
    (
        "redis://127.0.0.1:6379/0",
        "redis://127.0.0.1:6379/1",
        "redis://127.0.0.1:6379/14",
        "redis://example.invalid:6379/15",
        "redis://user:secret@127.0.0.1:6379/15",
    ),
)
def test_downstream_smoke_rejects_unsafe_redis_flush_targets(
    tmp_path: Path,
    redis_url: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    with pytest.raises(ValueError, match="loopback Redis DB 15"):
        run_downstream_smoke(
            Namespace(
                repository_root=repository,
                database_url="postgresql+psycopg://synthetic.invalid/test",
                runtime="fake",
                allow_real_runtime=False,
                allow_database_write=True,
                allow_redis_flush=True,
                redis_url=redis_url,
            )
        )

def test_direct_codex_smoke_requires_explicit_real_runtime_gate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="allow-real-runtime"):
        asyncio.run(
            triage_smoke.run(
                Namespace(
                    runtime="real",
                    allow_real_runtime=False,
                    allow_database_write=True,
                    database_url="postgresql+psycopg://synthetic.invalid/test",
                    runs_root=tmp_path / "runs",
                )
            )
        )


def test_downstream_smoke_reports_unexecuted_host_operations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    def fake_run(
        args: list[str],
        *,
        repository_root: Path,
        environment: dict[str, str],
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        del repository_root, environment, timeout_seconds
        stdout = (
            json.dumps(
                {
                    "realInferenceExecuted": False,
                    "results": [{"success": True}],
                }
            )
            if "scripts/smoke_test_codex_triage.py" in args
            else "1 passed"
        )
        return subprocess.CompletedProcess(args, 0, stdout, "")

    monkeypatch.setattr(downstream_smoke, "_run", fake_run)
    report = downstream_smoke.run(
        Namespace(
            repository_root=repository,
            database_url="postgresql+psycopg://synthetic.invalid/test",
            runtime="fake",
            allow_real_runtime=False,
            allow_database_write=True,
            allow_redis_flush=True,
            redis_url="redis://127.0.0.1:6379/15",
        )
    )

    assert report["verificationScope"] == "component_integration"
    assert report["hostOperationalAcceptance"] is False
    operations_report = report["operationalSteps"]
    assert operations_report["wakeCheck"]["state"] == "not_executed"
    assert operations_report["postgresBackup"]["state"] == "not_executed"
    assert operations_report["diagnostics"]["state"] == "not_executed"
    assert operations_report["redisFlushRecovery"]["state"] == "passed"
    assert operations_report["expiredAttemptFencing"]["state"] == "passed"


def test_cli_failure_exposes_only_error_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg = config(tmp_path)
    monkeypatch.setattr(operations, "default_config", lambda _: cfg)

    def fail_backup(_: OpsConfig) -> None:
        raise RuntimeError("app_secret=must-never-be-printed")

    monkeypatch.setattr(operations, "backup_postgres", fail_backup)

    exit_code = operations.main(
        ["backup", "--repository-root", str(cfg.repository_root)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "RuntimeError" in captured.out
    assert "must-never-be-printed" not in captured.out
    assert "must-never-be-printed" not in captured.err
    assert "must-never-be-printed" not in (
        cfg.state_root / "operations.jsonl"
    ).read_text()
