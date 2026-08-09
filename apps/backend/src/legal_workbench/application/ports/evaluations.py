from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from legal_workbench.domain.evaluations import (
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
)

__all__ = [
    "EvaluationRepository",
]

class EvaluationRepository(Protocol):
    async def get_case(
        self, *, suite_key: str, case_key: str, case_version: int
    ) -> EvaluationCase | None: ...
    async def add_case(self, case: EvaluationCase) -> None: ...
    async def add_run(self, run: EvaluationRun) -> None: ...
    async def get_run(self, run_id: UUID) -> EvaluationRun | None: ...
    async def get_run_for_update(self, run_id: UUID) -> EvaluationRun | None: ...
    async def save_run(self, run: EvaluationRun) -> None: ...
    async def add_result(self, result: EvaluationResult) -> None: ...
    async def list_results(self, run_id: UUID) -> Sequence[EvaluationResult]: ...
