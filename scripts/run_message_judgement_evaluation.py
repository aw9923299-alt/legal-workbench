#!/usr/bin/env python3
"""Run the versioned synthetic message-judgement evaluation suite."""

from __future__ import annotations

import argparse
import asyncio
import json
from uuid import uuid4

from legal_workbench.agents.codex_cli import CodexCliRuntime
from legal_workbench.application.evaluations import (
    EvaluationService,
    RealCodexEvaluationExecutor,
    RunEvaluationCommand,
)
from legal_workbench.config import get_settings
from legal_workbench.domain.enums import EvaluationRuntimeType
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def run(args: argparse.Namespace) -> int:
    if not args.allow_database_write:
        raise SystemExit("Refusing to persist evaluation rows without --allow-database-write")
    settings = get_settings()
    runtime_type = EvaluationRuntimeType(args.runtime)
    engine = create_async_engine(args.database_url, pool_pre_ping=True)
    factory = SqlAlchemyUnitOfWorkFactory(async_sessionmaker(engine, expire_on_commit=False))
    try:
        service = EvaluationService(
            factory,
            real_executor=(
                RealCodexEvaluationExecutor(CodexCliRuntime(runs_root=args.runs_root))
                if runtime_type == EvaluationRuntimeType.REAL
                else None
            ),
            real_runtime_enabled=settings.enable_real_codex,
        )
        report = await service.run(
            RunEvaluationCommand(
                fixture_path=args.fixture,
                runtime_type=runtime_type,
                allow_real_runtime=args.allow_real_runtime,
                actor_id="evaluation-cli",
                actor_source="local_cli",
                correlation_id=f"evaluation-cli:{uuid4()}",
                idempotency_key=f"evaluation-cli:{uuid4()}",
            )
        )
    finally:
        await engine.dispose()
    print(
        json.dumps(
            {
                "evaluationRunId": str(report.run.id),
                "runtimeType": report.run.runtime_type.value,
                "realInferenceExecuted": report.run.runtime_type == EvaluationRuntimeType.REAL,
                "agentDefinitionVersion": report.run.agent_definition_version,
                "status": report.run.status.value,
                "metrics": report.run.metrics,
                "failureCodes": [
                    value.failure_code for value in report.results if value.failure_code
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not any(value.failure_code for value in report.results) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--fixture",
        default="apps/backend/tests/fixtures/evaluations/message_judgement_v1.json",
    )
    parser.add_argument("--runtime", choices=("fake", "real"), default="fake")
    parser.add_argument("--runs-root", default="data/codex-runs-evaluation")
    parser.add_argument("--allow-real-runtime", action="store_true")
    parser.add_argument("--allow-database-write", action="store_true")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
