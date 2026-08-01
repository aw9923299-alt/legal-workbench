from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from legal_workbench.agents.message_judgement import MessageJudgementResult
from legal_workbench.domain.entities import AgentDefinition, AgentRun, ContextSnapshot

HeartbeatCallback = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AgentExecutionContext:
    snapshot: ContextSnapshot
    heartbeat: HeartbeatCallback | None = None


@dataclass(frozen=True, slots=True)
class AgentExecutionResult:
    output: MessageJudgementResult
    raw_stdout: str
    raw_stderr: str
    output_path: Path


class AgentRuntimeError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        raw_stdout: str = "",
        raw_stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.raw_stdout = raw_stdout
        self.raw_stderr = raw_stderr


class AgentRuntime(Protocol):
    async def execute(
        self,
        definition: AgentDefinition,
        run: AgentRun,
        context: AgentExecutionContext,
    ) -> AgentExecutionResult: ...


class DisabledAgentRuntime:
    """Fail explicitly when external Codex execution is feature-gated off."""

    async def execute(
        self,
        definition: AgentDefinition,
        run: AgentRun,
        context: AgentExecutionContext,
    ) -> AgentExecutionResult:
        del definition, run, context
        raise AgentRuntimeError(
            "AGENT_DEFINITION_DISABLED",
            "Real Codex execution is disabled by configuration.",
            retryable=False,
        )
