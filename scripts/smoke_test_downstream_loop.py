from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

POSTGRES_TESTS = (
    "apps/backend/tests/test_postgres_agent_attempt_fencing.py",
    "apps/backend/tests/test_postgres_document_extraction.py",
    "apps/backend/tests/test_postgres_matter_update_proposals.py",
    "apps/backend/tests/test_postgres_work_item_lifecycle.py",
    "apps/backend/tests/test_postgres_dashboard_queue.py",
    "apps/backend/tests/test_postgres_feishu_scopes.py",
    "apps/backend/tests/test_postgres_system_status.py",
    "apps/backend/tests/test_postgres_redis_flush_recovery.py",
    "apps/backend/tests/test_postgres_vertical_slice.py",
    "apps/backend/tests/test_worker_redis_recovery.py",
    "apps/backend/tests/test_analysis_recovery.py",
)


def _validated_redis_test_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "redis"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/15"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Redis recovery smoke requires an uncredentialed loopback Redis DB 15"
        )
    return value


def _run(
    args: list[str],
    *,
    repository_root: Path,
    environment: dict[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=repository_root,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Downstream smoke step failed: {Path(args[0]).name}")
    return completed


def run(args: argparse.Namespace) -> dict[str, object]:
    repository_root = args.repository_root.resolve(strict=True)
    if not args.allow_database_write:
        raise ValueError("Refusing to write smoke rows without --allow-database-write")
    if not args.allow_redis_flush:
        raise ValueError("Redis recovery smoke requires --allow-redis-flush")
    if args.runtime == "real" and not args.allow_real_runtime:
        raise ValueError("Real Codex requires --allow-real-runtime")
    redis_url = _validated_redis_test_url(args.redis_url)
    environment = dict(os.environ)
    environment.update(
        {
            "LEGAL_WORKBENCH_TEST_DATABASE_URL": args.database_url,
            "LEGAL_WORKBENCH_DATABASE_URL": args.database_url,
            "RUN_POSTGRES_INTEGRATION_TESTS": "1",
            "RUN_REDIS_INTEGRATION_TESTS": "1",
            "LEGAL_WORKBENCH_TEST_REDIS_URL": redis_url,
        }
    )
    python = sys.executable
    steps: list[dict[str, object]] = []
    _run(
        [
            python,
            "-m",
            "alembic",
            "-c",
            "apps/backend/alembic.ini",
            "upgrade",
            "head",
        ],
        repository_root=repository_root,
        environment=environment,
        timeout_seconds=180,
    )
    steps.append({"name": "migrations", "status": "passed"})
    tests = _run(
        [python, "-m", "pytest", *POSTGRES_TESTS, "--disable-warnings"],
        repository_root=repository_root,
        environment=environment,
        timeout_seconds=600,
    )
    steps.append(
        {
            "name": "postgres_downstream_components",
            "status": "passed",
            "summary": tests.stdout.strip().splitlines()[-1] if tests.stdout.strip() else "passed",
        }
    )
    codex_command = [
        python,
        "scripts/smoke_test_codex_triage.py",
        "--runtime",
        args.runtime,
        "--allow-database-write",
    ]
    if args.runtime == "real":
        codex_command.append("--allow-real-runtime")
    codex = _run(
        codex_command,
        repository_root=repository_root,
        environment=environment,
        timeout_seconds=1_800,
    )
    codex_result = json.loads(codex.stdout)
    steps.append(
        {
            "name": "message_judgement",
            "status": "passed",
            "runtime": args.runtime,
            "realInferenceExecuted": bool(codex_result.get("realInferenceExecuted")),
            "caseCount": len(codex_result.get("results", [])),
        }
    )
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "passed",
        "verificationScope": "component_integration",
        "componentIntegrationVerification": True,
        "hostOperationalAcceptance": False,
        "singleObjectEndToEnd": False,
        "steps": steps,
        "operationalSteps": {
            "wakeCheck": {
                "state": "not_executed",
                "reason": "requires_live_host_compose",
            },
            "postgresBackup": {
                "state": "not_executed",
                "reason": "requires_live_host_compose",
            },
            "diagnostics": {
                "state": "not_executed",
                "reason": "requires_live_host_filesystem",
            },
            "redisFlushRecovery": {
                "state": "passed",
                "evidence": "isolated_redis_db_flush_integration_test",
            },
            "expiredAttemptFencing": {
                "state": "passed",
                "evidence": "postgres_integration_test",
            },
        },
        "realFeishuTestMessage": {
            "state": "not_executed",
            "errorCode": "REAL_FEISHU_PHASE_DEFERRED",
        },
        "officialLongConnection": {
            "state": "not_executed",
            "errorCode": "REAL_FEISHU_PHASE_DEFERRED",
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the non-sensitive downstream operational smoke suite"
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("LEGAL_WORKBENCH_TEST_DATABASE_URL"),
    )
    parser.add_argument("--runtime", choices=("fake", "real"), default="fake")
    parser.add_argument("--allow-real-runtime", action="store_true")
    parser.add_argument("--allow-database-write", action="store_true")
    parser.add_argument("--allow-redis-flush", action="store_true")
    parser.add_argument(
        "--redis-url",
        default=os.getenv(
            "LEGAL_WORKBENCH_TEST_REDIS_URL",
            "redis://127.0.0.1:6379/15",
        ),
        help="Dedicated Redis URL; the selected non-zero database will be flushed.",
    )
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error(
            "--database-url or LEGAL_WORKBENCH_TEST_DATABASE_URL is required"
        )
    try:
        report = run(args)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "errorType": type(exc).__name__,
                    "realFeishuTestMessage": {"state": "not_executed"},
                    "officialLongConnection": {"state": "not_executed"},
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
