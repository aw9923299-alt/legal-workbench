from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Never
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.evaluations import (
    EvaluationScores,
    EvaluationService,
    RunEvaluationCommand,
    aggregate_evaluation_metrics,
    load_evaluation_fixture,
)
from legal_workbench.domain.entities import (
    AuditEvent,
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
    IdempotencyRecord,
)
from legal_workbench.domain.enums import EvaluationRunStatus, EvaluationRuntimeType
from legal_workbench.domain.errors import (
    EvaluationFixtureConflictError,
    EvaluationRuntimeDisabledError,
    IdempotencyConflictError,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "evaluations"
    / "message_judgement_v1.json"
)


class EvaluationRepository:
    def __init__(self) -> None:
        self.cases: dict[tuple[str, str, int], EvaluationCase] = {}
        self.runs: dict[UUID, EvaluationRun] = {}
        self.results: list[EvaluationResult] = []

    async def get_case(
        self, *, suite_key: str, case_key: str, case_version: int
    ) -> EvaluationCase | None:
        return self.cases.get((suite_key, case_key, case_version))

    async def add_case(self, case: EvaluationCase) -> None:
        self.cases[(case.suite_key, case.case_key, case.case_version)] = case

    async def add_run(self, run: EvaluationRun) -> None:
        self.runs[run.id] = run

    async def get_run(self, run_id: UUID) -> EvaluationRun | None:
        return self.runs.get(run_id)

    async def get_run_for_update(self, run_id: UUID) -> EvaluationRun | None:
        return self.runs.get(run_id)

    async def save_run(self, run: EvaluationRun) -> None:
        self.runs[run.id] = run

    async def add_result(self, result: EvaluationResult) -> None:
        self.results.append(result)

    async def list_results(self, run_id: UUID) -> Sequence[EvaluationResult]:
        return [value for value in self.results if value.evaluation_run_id == run_id]


class AuditRepository:
    def __init__(self) -> None:
        self.values: list[AuditEvent] = []

    async def add(self, value: AuditEvent) -> None:
        self.values.append(value)


class IdempotencyRepository:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], IdempotencyRecord] = {}

    async def get(self, *, operation: str, key: str) -> IdempotencyRecord | None:
        return self.values.get((operation, key))

    async def add(self, value: IdempotencyRecord) -> None:
        self.values[(value.operation, value.idempotency_key)] = value


class FakeUnitOfWork:
    def __init__(self, state: FakeState) -> None:
        self.evaluations = state.evaluations
        self.audit_events = state.audit_events
        self.idempotency = state.idempotency

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None

    async def commit(self) -> None:
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        return None


class FakeState:
    def __init__(self) -> None:
        self.evaluations = EvaluationRepository()
        self.audit_events = AuditRepository()
        self.idempotency = IdempotencyRepository()

    def factory(self) -> FakeUnitOfWork:
        return FakeUnitOfWork(self)


def fail_factory() -> Never:
    raise AssertionError("A gated real evaluation must not open a UnitOfWork")


def result(
    *,
    expected_relevant: bool = True,
    candidate_created: bool = True,
    schema_first_pass: bool = True,
    duration_ms: int = 100,
    retry_count: int = 0,
    failure_code: str | None = None,
    scores: EvaluationScores | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        id=uuid4(),
        evaluation_run_id=uuid4(),
        evaluation_case_id=uuid4(),
        result_payload={},
        scores=(scores or EvaluationScores.perfect()).to_dict(),
        expected_relevant=expected_relevant,
        candidate_created=candidate_created,
        schema_first_pass=schema_first_pass,
        duration_ms=duration_ms,
        retry_count=retry_count,
        failure_code=failure_code,
        runtime_version="fake-evaluation-v1",
    )


def test_evaluation_metrics_count_irrelevant_candidate_as_false_positive() -> None:
    metrics = aggregate_evaluation_metrics(
        [result(expected_relevant=False, candidate_created=True)]
    )

    assert metrics.irrelevant_candidate_false_positive_rate == 1.0


def test_evaluation_metrics_cover_quality_runtime_failures_and_retries() -> None:
    degraded = EvaluationScores(
        legal_relevance=0.0,
        category=0.0,
        deadline=0.0,
        message_role=1.0,
        facts=0.5,
        missing_information=0.0,
        fact_citation_correct=1,
        fact_citation_total=2,
        inference_false_positive_count=1,
        inference_prediction_count=2,
    )
    metrics = aggregate_evaluation_metrics(
        [
            result(duration_ms=100),
            result(
                expected_relevant=False,
                candidate_created=False,
                schema_first_pass=False,
                duration_ms=300,
                retry_count=2,
                failure_code="AGENT_OUTPUT_SCHEMA_INVALID",
                scores=degraded,
            ),
        ]
    )

    assert metrics.legal_relevance_accuracy == 0.5
    assert metrics.category_accuracy == 0.5
    assert metrics.deadline_accuracy == 0.5
    assert metrics.message_role_accuracy == 1.0
    assert metrics.facts_accuracy == 0.75
    assert metrics.fact_citation_accuracy == pytest.approx(2 / 3)
    assert metrics.inference_false_positive_rate == 0.5
    assert metrics.missing_information_accuracy == 0.5
    assert metrics.schema_first_pass_rate == 0.5
    assert metrics.average_latency_ms == 200
    assert metrics.failure_rate == 0.5
    assert metrics.retry_rate == 0.5


def test_versioned_fixture_is_non_sensitive_and_covers_required_cases() -> None:
    suite = load_evaluation_fixture(FIXTURE)

    assert suite.suite_key == "message_judgement_v1"
    assert suite.version == 1
    assert len(suite.cases) >= 11
    assert {
        "contract_review",
        "employment_question",
        "intellectual_property",
        "casual_chat",
        "information_only",
        "matter_update",
        "explicit_deadline",
        "ambiguous_deadline",
        "prompt_injection",
        "oversized_message",
        "attachment_message",
    }.issubset({case.case_key for case in suite.cases})
    assert all(case.case_version >= 1 for case in suite.cases)
    assert all(case.content_hash for case in suite.cases)

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert raw["dataClassification"] == "synthetic_non_sensitive"
    assert "真实" not in "".join(case.input_text for case in suite.cases)


@pytest.mark.asyncio
async def test_fake_suite_persists_cases_results_metrics_and_audit() -> None:
    state = FakeState()
    service = EvaluationService(state.factory)
    command = RunEvaluationCommand(
        fixture_path=FIXTURE,
        runtime_type=EvaluationRuntimeType.FAKE,
        allow_real_runtime=False,
        actor_id="legal-evaluator",
        actor_source="test",
        correlation_id="corr-evaluation-fake",
        idempotency_key="idem-evaluation-fake",
    )
    report = await service.run(command)
    replay = await service.run(command)

    assert report.run.status == EvaluationRunStatus.COMPLETED
    assert report.run.agent_definition_version == "2.2.0"
    assert report.run.metrics["case_count"] == 11
    assert report.run.metrics["legal_relevance_accuracy"] == 1.0
    assert report.run.metrics["irrelevant_candidate_false_positive_rate"] == 0.0
    assert len(report.results) == 11
    assert len(state.evaluations.cases) == 11
    assert len(state.evaluations.results) == 11
    assert replay.run.id == report.run.id
    assert len(replay.results) == 11
    assert [value.event_type for value in state.audit_events.values] == [
        "evaluation_run_started",
        "evaluation_run_completed",
    ]
    assert all(value.runtime_execution_id is None for value in report.results)
    with pytest.raises(IdempotencyConflictError):
        await service.run(
            RunEvaluationCommand(
                fixture_path=FIXTURE,
                runtime_type=EvaluationRuntimeType.FAKE,
                allow_real_runtime=True,
                actor_id="legal-evaluator",
                actor_source="test",
                correlation_id="corr-evaluation-fake-changed",
                idempotency_key="idem-evaluation-fake",
            )
        )


@pytest.mark.asyncio
async def test_immutable_case_version_cannot_be_replaced() -> None:
    state = FakeState()
    suite = load_evaluation_fixture(FIXTURE)
    fixture_case = suite.cases[0]
    state.evaluations.cases[
        (suite.suite_key, fixture_case.case_key, fixture_case.case_version)
    ] = EvaluationCase(
        id=uuid4(),
        suite_key=suite.suite_key,
        case_key=fixture_case.case_key,
        case_version=fixture_case.case_version,
        agent_key=suite.agent_key,
        input_payload=fixture_case.input_payload,
        expected_output=fixture_case.expected_output,
        content_hash="0" * 64,
    )

    with pytest.raises(EvaluationFixtureConflictError):
        await EvaluationService(state.factory).run(
            RunEvaluationCommand(
                fixture_path=FIXTURE,
                runtime_type=EvaluationRuntimeType.FAKE,
                allow_real_runtime=False,
                actor_id="legal-evaluator",
                actor_source="test",
                correlation_id="corr-evaluation-fixture-conflict",
                idempotency_key="idem-evaluation-fixture-conflict",
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("allow_real_runtime", "server_enabled", "reason"),
    [
        (False, True, "explicit_approval_required"),
        (True, False, "server_feature_disabled"),
        (True, True, "runner_unreachable"),
    ],
)
async def test_real_runtime_requires_both_explicit_and_server_gates(
    allow_real_runtime: bool,
    server_enabled: bool,
    reason: str,
) -> None:
    service = EvaluationService(
        fail_factory,
        real_executor=None,
        real_runtime_enabled=server_enabled,
    )

    with pytest.raises(EvaluationRuntimeDisabledError) as captured:
        await service.run(
            RunEvaluationCommand(
                fixture_path=FIXTURE,
                runtime_type=EvaluationRuntimeType.REAL,
                allow_real_runtime=allow_real_runtime,
                actor_id="legal-evaluator",
                actor_source="test",
                correlation_id="corr-evaluation-real-gate",
                idempotency_key="idem-evaluation-real-gate",
            )
        )

    assert captured.value.code == "REAL_EVALUATION_RUNTIME_DISABLED"
    assert captured.value.details["reason"] == reason


@pytest.mark.asyncio
async def test_evaluation_http_defaults_to_fake_and_returns_durable_report() -> None:
    from httpx import ASGITransport, AsyncClient

    from legal_workbench.api.auth import RequestActor
    from legal_workbench.api.dependencies import get_request_actor
    from legal_workbench.api.routes.evaluations import get_evaluation_service
    from legal_workbench.config import Settings, get_settings
    from legal_workbench.main import app

    state = FakeState()
    service = EvaluationService(state.factory)
    app.dependency_overrides[get_request_actor] = lambda: RequestActor(
        actor_id="legal-evaluator", identity_source="test"
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        evaluation_fixture_path=str(FIXTURE)
    )
    app.dependency_overrides[get_evaluation_service] = lambda: service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/v1/evaluations/runs",
                json={},
                headers={
                    "X-Correlation-ID": "corr-evaluation-http",
                    "Idempotency-Key": "idem-evaluation-http",
                },
            )
            run_id = response.json().get("id")
            fetched = await client.get(f"/api/v1/evaluations/runs/{run_id}")
    finally:
        app.dependency_overrides.pop(get_request_actor, None)
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_evaluation_service, None)

    assert response.status_code == 200, response.text
    assert response.json()["runtimeType"] == "fake"
    assert response.json()["correlationId"] == "corr-evaluation-http"
    assert response.json()["metrics"]["caseCount"] == 11
    assert response.json()["metrics"]["schemaFirstPassRate"] == 1.0
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == run_id


@pytest.mark.asyncio
async def test_evaluation_http_real_gate_has_stable_code_and_correlation_id() -> None:
    from httpx import ASGITransport, AsyncClient

    from legal_workbench.api.auth import RequestActor
    from legal_workbench.api.dependencies import get_request_actor
    from legal_workbench.api.routes.evaluations import get_evaluation_service
    from legal_workbench.main import app

    app.dependency_overrides[get_request_actor] = lambda: RequestActor(
        actor_id="legal-evaluator", identity_source="test"
    )
    app.dependency_overrides[get_evaluation_service] = lambda: EvaluationService(
        fail_factory,
        real_runtime_enabled=False,
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/v1/evaluations/runs",
                json={"runtimeType": "real", "allowRealRuntime": False},
                headers={
                    "X-Correlation-ID": "corr-evaluation-gate",
                    "Idempotency-Key": "idem-evaluation-gate",
                },
            )
    finally:
        app.dependency_overrides.pop(get_request_actor, None)
        app.dependency_overrides.pop(get_evaluation_service, None)

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "REAL_EVALUATION_RUNTIME_DISABLED"
    assert response.json()["error"]["correlationId"] == "corr-evaluation-gate"
