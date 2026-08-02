from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class CodexHealthStatus(StrEnum):
    AVAILABLE = "available"
    UNAUTHENTICATED = "unauthenticated"
    VERSION_MISMATCH = "version_mismatch"
    MISCONFIGURED = "misconfigured"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True, slots=True)
class CodexRuntimeHealth:
    status: CodexHealthStatus
    executable: str | None
    detected_version: str | None
    expected_version: str | None
    authentication: str
    runtime_directory_writable: bool
    detail: str


class CodexRuntimeHealthChecker:
    """Verify the exact executable, version, isolated auth and run directory."""

    def __init__(
        self,
        *,
        command: Sequence[str] | str,
        expected_version: str | None,
        runs_root: str | Path,
        timeout_seconds: float = 5,
    ) -> None:
        parsed = shlex.split(command) if isinstance(command, str) else list(command)
        self._command = parsed
        self._expected_version = (expected_version or "").strip() or None
        self._runs_root = Path(runs_root)
        self._timeout = timeout_seconds

    async def check(
        self, *, environment: Mapping[str, str] | None = None
    ) -> CodexRuntimeHealth:
        executable = self._resolve_executable()
        if executable is None:
            return self._result(
                CodexHealthStatus.MISCONFIGURED,
                executable=None,
                detail="Codex CLI executable was not found.",
            )
        writable = self._check_runtime_directory()
        if not writable:
            return self._result(
                CodexHealthStatus.MISCONFIGURED,
                executable=executable,
                detail="Codex runtime directory is not writable.",
            )
        try:
            version_output = await self._run(
                [executable, *self._command[1:], "--version"],
                environment=environment,
            )
        except (TimeoutError, OSError) as exc:
            return self._result(
                CodexHealthStatus.UNREACHABLE,
                executable=executable,
                detail=f"Codex version check failed: {type(exc).__name__}.",
            )
        detected = self._parse_version(version_output)
        if not detected:
            return self._result(
                CodexHealthStatus.UNREACHABLE,
                executable=executable,
                detail="Codex version output could not be parsed.",
            )
        if self._expected_version and detected != self._expected_version:
            return CodexRuntimeHealth(
                status=CodexHealthStatus.VERSION_MISMATCH,
                executable=executable,
                detected_version=detected,
                expected_version=self._expected_version,
                authentication="not_checked",
                runtime_directory_writable=True,
                detail="Codex CLI version does not match the configured runtime version.",
            )

        safe_environment = dict(environment or os.environ)
        if not (safe_environment.get("OPENAI_API_KEY") or "").strip():
            return CodexRuntimeHealth(
                status=CodexHealthStatus.UNAUTHENTICATED,
                executable=executable,
                detected_version=detected,
                expected_version=self._expected_version,
                authentication="missing_runtime_api_key",
                runtime_directory_writable=True,
                detail=(
                    "The isolated worker environment has no Codex authentication; "
                    "host login state is intentionally not inherited."
                ),
            )
        try:
            login_output = await self._run(
                [executable, *self._command[1:], "login", "status"],
                environment=safe_environment,
            )
        except TimeoutError:
            return CodexRuntimeHealth(
                status=CodexHealthStatus.UNREACHABLE,
                executable=executable,
                detected_version=detected,
                expected_version=self._expected_version,
                authentication="unreachable",
                runtime_directory_writable=True,
                detail="Codex authentication check timed out.",
            )
        except OSError:
            return CodexRuntimeHealth(
                status=CodexHealthStatus.UNAUTHENTICATED,
                executable=executable,
                detected_version=detected,
                expected_version=self._expected_version,
                authentication="rejected",
                runtime_directory_writable=True,
                detail="Codex authentication was rejected in the isolated environment.",
            )
        return CodexRuntimeHealth(
            status=CodexHealthStatus.AVAILABLE,
            executable=executable,
            detected_version=detected,
            expected_version=self._expected_version,
            authentication=("api_key" if "api key" in login_output.lower() else "authenticated"),
            runtime_directory_writable=True,
            detail="Codex CLI, configured version, authentication and runtime directory are ready.",
        )

    def _resolve_executable(self) -> str | None:
        if not self._command:
            return None
        candidate = self._command[0]
        if Path(candidate).is_absolute():
            return candidate if os.access(candidate, os.X_OK) else None
        return shutil.which(candidate)

    def _check_runtime_directory(self) -> bool:
        try:
            self._runs_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = tempfile.mkdtemp(prefix="health-", dir=self._runs_root)
            Path(temporary).rmdir()
        except OSError:
            return False
        return True

    async def _run(
        self, command: list[str], *, environment: Mapping[str, str] | None
    ) -> str:
        health_home = self._runs_root / ".health-home"
        health_home.mkdir(parents=True, exist_ok=True, mode=0o700)
        process_environment = {
            "LANG": "C.UTF-8",
            "PATH": (environment or os.environ).get("PATH", os.defpath),
            "HOME": str(health_home),
            "CODEX_HOME": str(health_home),
        }
        api_key = (environment or os.environ).get("OPENAI_API_KEY")
        if api_key:
            process_environment["OPENAI_API_KEY"] = api_key
        process = await asyncio.create_subprocess_exec(
            *command,
            env=process_environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        output = (stdout + b"\n" + stderr).decode("utf-8", errors="replace").strip()
        if process.returncode != 0:
            raise OSError(f"Codex health command exited with {process.returncode}: {output[:200]}")
        return output

    @staticmethod
    def _parse_version(output: str) -> str | None:
        first_line = output.splitlines()[0].strip() if output.strip() else ""
        if not first_line:
            return None
        if first_line.startswith("codex-cli "):
            return first_line.removeprefix("codex-cli ").strip() or None
        return first_line.split()[-1] if first_line.split() else None

    def _result(
        self,
        status: CodexHealthStatus,
        *,
        executable: str | None,
        detail: str,
    ) -> CodexRuntimeHealth:
        return CodexRuntimeHealth(
            status=status,
            executable=executable,
            detected_version=None,
            expected_version=self._expected_version,
            authentication="not_checked",
            runtime_directory_writable=status != CodexHealthStatus.MISCONFIGURED,
            detail=detail,
        )
