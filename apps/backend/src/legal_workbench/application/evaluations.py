from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from legal_workbench.agents.definitions import build_message_judgement_definition
from legal_workbench.agents.message_judgement import (
    MessageJudgementResult,
    should_create_candidate,
)
from legal_workbench.agents.runtime import (
    AgentExecutionContext,
    AgentRuntime,
    AgentRuntimeError,
)
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import (
    AgentRun,
    AuditEvent,
    ContextSnapshot,
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
    IdempotencyRecord,
)
from legal_workbench.domain.enums import (
    AgentRunStatus,
    EvaluationRunStatus,
    EvaluationRuntimeType,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityNotFoundError,
    EvaluationFixtureConflictError,
    EvaluationRuntimeDisabledError,
    IdempotencyConflictError,
)


@dataclass(frozen=True, slots=True)
class EvaluationFixtureCase:
    case_key: str
    case_version: int
    input_payload: dict[str, object]
    expected_output: dict[str, object]
    content_hash: str

    @property
    def input_text(self) -> str:
        text = str(self.input_payload.get("text") or "")
        repeat = self.input_payload.get("textRepeat")
        if isinstance(repeat, dict):
            value = str(repeat.get("value") or "")
            count = repeat.get("count")
            if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                text += value * min(count, 10_000)
        return text


@dataclass(frozen=True, slots=True)
class EvaluationFixtureSuite:
    suite_key: str
    version: int
    agent_key: str
    data_classification: str
    cases: tuple[EvaluationFixtureCase, ...]


@dataclass(frozen=True, slots=True)
class EvaluationScores:
    legal_relevance: float
    category: float
    deadline: float
    message_role: float
    facts: float
    missing_information: float
    fact_citation_correct: int
    fact_citation_total: int
    inference_false_positive_count: int
    inference_prediction_count: int

    @classmethod
    def perfect(cls) -> EvaluationScores:
        return cls(
            legal_relevance=1.0,
            category=1.0,
            deadline=1.0,
            message_role=1.0,
            facts=1.0,
            missing_information=1.0,
            fact_citation_correct=1,
            fact_citation_total=1,
            inference_false_positive_count=0,
            inference_prediction_count=0,
        )

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> EvaluationScores:
        return cls(
            legal_relevance=_score_number(value.get("legal_relevance")),
            category=_score_number(value.get("category")),
            deadline=_score_number(value.get("deadline")),
            message_role=_score_number(value.get("message_role")),
            facts=_score_number(value.get("facts")),
            missing_information=_score_number(value.get("missing_information")),
            fact_citation_correct=_count_number(value.get("fact_citation_correct")),
            fact_citation_total=_count_number(value.get("fact_citation_total")),
            inference_false_positive_count=_count_number(
                value.get("inference_false_positive_count", 0)
            ),
            inference_prediction_count=_count_number(
                value.get("inference_prediction_count", 0)
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    case_count: int
    legal_relevance_accuracy: float
    category_accuracy: float
    deadline_accuracy: float
    message_role_accuracy: float
    facts_accuracy: float
    fact_citation_accuracy: float
    inference_false_positive_rate: float
    missing_information_accuracy: float
    irrelevant_candidate_false_positive_rate: float
    schema_first_pass_rate: float
    average_latency_ms: float
    failure_rate: float
    retry_rate: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _score_number(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _count_number(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    return 0


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def aggregate_evaluation_metrics(
    results: list[EvaluationResult] | tuple[EvaluationResult, ...],
) -> EvaluationMetrics:
    count = len(results)
    scores = [EvaluationScores.from_dict(result.scores) for result in results]
    irrelevant = [result for result in results if not result.expected_relevant]
    return EvaluationMetrics(
        case_count=count,
        legal_relevance_accuracy=_ratio(
            sum(value.legal_relevance for value in scores), count
        ),
        category_accuracy=_ratio(sum(value.category for value in scores), count),
        deadline_accuracy=_ratio(sum(value.deadline for value in scores), count),
        message_role_accuracy=_ratio(sum(value.message_role for value in scores), count),
        facts_accuracy=_ratio(sum(value.facts for value in scores), count),
        fact_citation_accuracy=_ratio(
            sum(value.fact_citation_correct for value in scores),
            sum(value.fact_citation_total for value in scores),
        ),
        inference_false_positive_rate=_ratio(
            sum(value.inference_false_positive_count for value in scores),
            sum(value.inference_prediction_count for value in scores),
        ),
        missing_information_accuracy=_ratio(
            sum(value.missing_information for value in scores), count
        ),
        irrelevant_candidate_false_positive_rate=_ratio(
            sum(result.candidate_created for result in irrelevant), len(irrelevant)
        ),
        schema_first_pass_rate=_ratio(sum(result.schema_first_pass for result in results), count),
        average_latency_ms=_ratio(sum(result.duration_ms for result in results), count),
        failure_rate=_ratio(sum(result.failure_code is not None for result in results), count),
        retry_rate=_ratio(sum(result.retry_count > 0 for result in results), count),
    )


def load_evaluation_fixture(path: str | Path) -> EvaluationFixtureSuite:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DomainValidationError("Evaluation fixture could not be loaded.") from exc
    if not isinstance(payload, dict):
        raise DomainValidationError("Evaluation fixture root must be an object.")
    suite_key = str(payload.get("suiteKey") or "").strip()
    agent_key = str(payload.get("agentKey") or "").strip()
    version = payload.get("version")
    classification = str(payload.get("dataClassification") or "")
    raw_cases = payload.get("cases")
    if (
        not suite_key
        or not agent_key
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
        or classification != "synthetic_non_sensitive"
        or not isinstance(raw_cases, list)
        or not raw_cases
    ):
        raise DomainValidationError("Evaluation fixture metadata is invalid.")
    cases: list[EvaluationFixtureCase] = []
    identities: set[tuple[str, int]] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise DomainValidationError("Evaluation fixture case must be an object.")
        case_key = str(raw.get("caseKey") or "").strip()
        case_version = raw.get("caseVersion")
        input_payload = raw.get("input")
        expected_output = raw.get("expected")
        if (
            not case_key
            or not isinstance(case_version, int)
            or isinstance(case_version, bool)
            or case_version < 1
            or not isinstance(input_payload, dict)
            or not isinstance(expected_output, dict)
        ):
            raise DomainValidationError("Evaluation fixture case is invalid.")
        identity = (case_key, case_version)
        if identity in identities:
            raise DomainValidationError("Evaluation fixture case identity is duplicated.")
        identities.add(identity)
        canonical = json.dumps(
            {
                "caseKey": case_key,
                "caseVersion": case_version,
                "input": input_payload,
                "expected": expected_output,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        cases.append(
            EvaluationFixtureCase(
                case_key=case_key,
                case_version=case_version,
                input_payload=input_payload,
                expected_output=expected_output,
                content_hash=sha256(canonical.encode("utf-8")).hexdigest(),
            )
        )
    return EvaluationFixtureSuite(
        suite_key=suite_key,
        version=version,
        agent_key=agent_key,
        data_classification=classification,
        cases=tuple(cases),
    )


@dataclass(frozen=True, slots=True)
class EvaluationExecution:
    output: MessageJudgementResult | None
    schema_first_pass: bool
    duration_ms: int
    retry_count: int
    failure_code: str | None = None
    runtime_version: str | None = None
    runtime_execution_id: UUID | None = None


class EvaluationExecutor(Protocol):
    async def execute(
        self,
        case: EvaluationFixtureCase,
        *,
        evaluation_run_id: UUID,
    ) -> EvaluationExecution: ...


def _case_input_text(case: EvaluationFixtureCase) -> str:
    return case.input_text


def _attachment_segments(case: EvaluationFixtureCase) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    attachments = case.input_payload.get("attachments")
    if not isinstance(attachments, list):
        return values
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        attachment_id = str(attachment.get("attachmentId") or "")
        file_name = str(attachment.get("fileName") or "")
        segments = attachment.get("segments")
        if not attachment_id or not file_name or not isinstance(segments, list):
            continue
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            content = str(segment.get("content") or "")
            paragraph = segment.get("paragraphNumber")
            page = segment.get("pageNumber")
            if not content or not isinstance(paragraph, int) or isinstance(paragraph, bool):
                continue
            values.append(
                {
                    "attachmentId": attachment_id,
                    "fileName": file_name,
                    "pageNumber": page if isinstance(page, int) else None,
                    "paragraphNumber": paragraph,
                    "content": content,
                    "contentHash": sha256(content.encode("utf-8")).hexdigest(),
                }
            )
    return values


def _build_fixture_output(case: EvaluationFixtureCase) -> MessageJudgementResult:
    expected = case.expected_output
    message_role = str(expected.get("messageRole") or "information_only")
    candidate_created = bool(expected.get("candidateCreated"))
    if not candidate_created:
        actionability = "ignore"
    elif message_role in {"existing_matter_update", "supplemental_material"}:
        actionability = "link_candidate"
    else:
        actionability = "create_candidate"
    category = expected.get("category")
    categories = [] if category is None else [
        {"category": str(category), "confidence": 1.0, "reason": "versioned fixture"}
    ]
    deadlines = expected.get("deadlines")
    deadline_candidates = [
        {**value, "confidence": 1.0}
        for value in deadlines
        if isinstance(value, dict)
    ] if isinstance(deadlines, list) else []
    segments = _attachment_segments(case)
    facts: list[dict[str, object]] = []
    expected_facts = expected.get("facts")
    if isinstance(expected_facts, list):
        for value in expected_facts:
            if not isinstance(value, dict):
                continue
            fact: dict[str, object] = {"statement": str(value.get("statement") or "")}
            source_message_id = value.get("sourceMessageId")
            if source_message_id:
                fact["sourceMessageId"] = str(source_message_id)
            else:
                matching = next(
                    (
                        segment
                        for segment in segments
                        if segment["attachmentId"] == value.get("attachmentId")
                        and segment["paragraphNumber"] == value.get("paragraphNumber")
                    ),
                    None,
                )
                if matching is None:
                    raise DomainValidationError(
                        "Evaluation fixture attachment fact has no matching segment."
                    )
                fact["attachmentCitation"] = {
                    key: matching[key]
                    for key in (
                        "attachmentId",
                        "fileName",
                        "pageNumber",
                        "paragraphNumber",
                        "contentHash",
                    )
                }
            facts.append(fact)
    expected_inferences = expected.get("inferences")
    inferences: list[dict[str, object]] = []
    if isinstance(expected_inferences, list):
        for value in expected_inferences:
            if isinstance(value, dict):
                inferences.append(value)
            elif isinstance(value, str):
                inferences.append(
                    {"statement": value, "basis": "versioned fixture", "confidence": 1.0}
                )
    missing = expected.get("missingInformation")
    return MessageJudgementResult.model_validate(
        {
            "legalRelevance": expected.get("legalRelevance"),
            "messageRole": message_role,
            "actionability": actionability,
            "suggestedTitle": f"评估 - {case.case_key}",
            "categoryCandidates": categories,
            "deadlineCandidates": deadline_candidates,
            "confirmedFacts": facts,
            "inferredFacts": inferences,
            "missingInformation": list(missing) if isinstance(missing, list) else [],
            "reasons": ["deterministic fake evaluation runtime"],
            "confidence": 1.0,
        }
    )


class FakeEvaluationExecutor:
    async def execute(
        self,
        case: EvaluationFixtureCase,
        *,
        evaluation_run_id: UUID,
    ) -> EvaluationExecution:
        del evaluation_run_id
        started = time.monotonic()
        try:
            output = _build_fixture_output(case)
        except Exception:
            return EvaluationExecution(
                output=None,
                schema_first_pass=False,
                duration_ms=round((time.monotonic() - started) * 1000),
                retry_count=0,
                failure_code="EVALUATION_FIXTURE_OUTPUT_INVALID",
                runtime_version="fake-evaluation-v1",
            )
        return EvaluationExecution(
            output=output,
            schema_first_pass=True,
            duration_ms=round((time.monotonic() - started) * 1000),
            retry_count=0,
            runtime_version="fake-evaluation-v1",
        )


def _build_evaluation_context(case: EvaluationFixtureCase) -> ContextSnapshot:
    message_id = str(case.input_payload.get("messageId") or case.case_key)
    text = _case_input_text(case)
    segments = _attachment_segments(case)
    content: dict[str, object] = {
        "messages": [
            {
                "messageId": message_id,
                "messageType": str(case.input_payload.get("messageType") or "text"),
                "plainText": text,
            }
        ],
        "attachments": case.input_payload.get("attachments") or [],
    }
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return ContextSnapshot(
        id=uuid4(),
        source_type="evaluation_fixture",
        source_id=f"{case.case_key}:v{case.case_version}",
        source_ids=[case.case_key],
        message_ids=[message_id],
        file_ids=[],
        attachment_ids=[str(value["attachmentId"]) for value in segments],
        included_segments=segments,
        excluded_segments=[],
        relevant_matter_ids=[],
        participant_ids=["synthetic-evaluation-sender"],
        permission_snapshot={"synthetic": True, "authorized": True},
        thread_metadata={"evaluationCase": case.case_key},
        content=content,
        generated_at=datetime.now(UTC),
        content_hash=sha256(canonical.encode("utf-8")).hexdigest(),
        builder_version="evaluation-v1",
        selection_policy_version="evaluation-v1",
        original_size=len(text),
        included_size=len(text),
    )


class RealCodexEvaluationExecutor:
    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime

    async def execute(
        self,
        case: EvaluationFixtureCase,
        *,
        evaluation_run_id: UUID,
    ) -> EvaluationExecution:
        definition = build_message_judgement_definition()
        snapshot = _build_evaluation_context(case)
        run = AgentRun(
            id=uuid4(),
            agent_definition_id=definition.id,
            context_snapshot_id=snapshot.id,
            status=AgentRunStatus.RUNNING,
            objective="Evaluate one synthetic message judgement fixture.",
            prompt_snapshot=definition.prompt_template,
            working_directory=f"evaluation/{evaluation_run_id}/{case.case_key}",
            attempt_number=1,
            max_attempts=definition.max_retries + 1,
            correlation_id=f"evaluation:{evaluation_run_id}:{case.case_key}",
            created_by="evaluation-runner",
            agent_definition_version=definition.version,
            prompt_version=definition.version,
        )
        started = time.monotonic()
        try:
            execution = await self._runtime.execute(
                definition,
                run,
                AgentExecutionContext(snapshot=snapshot),
            )
        except AgentRuntimeError as exc:
            return EvaluationExecution(
                output=None,
                schema_first_pass=False,
                duration_ms=round((time.monotonic() - started) * 1000),
                retry_count=int(exc.repair_attempted),
                failure_code=exc.code,
                runtime_execution_id=run.id,
            )
        except Exception:
            return EvaluationExecution(
                output=None,
                schema_first_pass=False,
                duration_ms=round((time.monotonic() - started) * 1000),
                retry_count=0,
                failure_code="EVALUATION_RUNTIME_FAILED",
                runtime_execution_id=run.id,
            )
        return EvaluationExecution(
            output=execution.output,
            schema_first_pass=not execution.repair_attempted,
            duration_ms=round((time.monotonic() - started) * 1000),
            retry_count=int(execution.repair_attempted),
            runtime_version=execution.runtime_version,
            runtime_execution_id=run.id,
        )


def _normalized_text(value: object) -> str:
    return str(value or "").strip().rstrip("。")


def _set_f1(expected: set[str], predicted: set[str]) -> float:
    if not expected and not predicted:
        return 1.0
    if not expected or not predicted:
        return 0.0
    intersection = len(expected & predicted)
    precision = intersection / len(predicted)
    recall = intersection / len(expected)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _canonical_deadlines(values: object) -> set[tuple[str, str | None, str]]:
    if not isinstance(values, list):
        return set()
    return {
        (
            _normalized_text(value.get("rawText")),
            str(value.get("resolvedAt")) if value.get("resolvedAt") else None,
            str(value.get("deadlineType") or ""),
        )
        for value in values
        if isinstance(value, dict)
    }


def _expected_fact_citation(
    case: EvaluationFixtureCase, value: dict[str, object]
) -> tuple[object, ...] | None:
    if value.get("sourceMessageId"):
        return ("message", str(value["sourceMessageId"]))
    matching = next(
        (
            segment
            for segment in _attachment_segments(case)
            if segment["attachmentId"] == value.get("attachmentId")
            and segment["paragraphNumber"] == value.get("paragraphNumber")
        ),
        None,
    )
    if matching is None:
        return None
    return (
        "attachment",
        matching["attachmentId"],
        matching["fileName"],
        matching["pageNumber"],
        matching["paragraphNumber"],
        matching["contentHash"],
    )


def _predicted_fact_citation(value: dict[str, object]) -> tuple[object, ...] | None:
    if value.get("sourceMessageId"):
        return ("message", str(value["sourceMessageId"]))
    citation = value.get("attachmentCitation")
    if not isinstance(citation, dict):
        return None
    return (
        "attachment",
        citation.get("attachmentId"),
        citation.get("fileName"),
        citation.get("pageNumber"),
        citation.get("paragraphNumber"),
        citation.get("contentHash"),
    )


def score_evaluation_output(
    case: EvaluationFixtureCase,
    output: MessageJudgementResult,
) -> EvaluationScores:
    predicted = output.model_dump(by_alias=True, mode="json")
    expected = case.expected_output
    categories = predicted.get("categoryCandidates")
    predicted_category = (
        categories[0].get("category")
        if isinstance(categories, list) and categories and isinstance(categories[0], dict)
        else None
    )
    expected_facts_raw = expected.get("facts")
    predicted_facts_raw = predicted.get("confirmedFacts")
    expected_facts = [
        value for value in expected_facts_raw if isinstance(value, dict)
    ] if isinstance(expected_facts_raw, list) else []
    predicted_facts = [
        value for value in predicted_facts_raw if isinstance(value, dict)
    ] if isinstance(predicted_facts_raw, list) else []
    expected_statements = {_normalized_text(value.get("statement")) for value in expected_facts}
    predicted_statements = {_normalized_text(value.get("statement")) for value in predicted_facts}
    expected_by_statement = {
        _normalized_text(value.get("statement")): value for value in expected_facts
    }
    citation_correct = 0
    for value in predicted_facts:
        statement = _normalized_text(value.get("statement"))
        expected_fact = expected_by_statement.get(statement)
        if expected_fact is not None and _predicted_fact_citation(value) == _expected_fact_citation(
            case, expected_fact
        ):
            citation_correct += 1
    expected_inferences = expected.get("inferences")
    predicted_inferences = predicted.get("inferredFacts")
    expected_inference_statements = {
        _normalized_text(value.get("statement") if isinstance(value, dict) else value)
        for value in expected_inferences
    } if isinstance(expected_inferences, list) else set()
    predicted_inference_statements = {
        _normalized_text(value.get("statement"))
        for value in predicted_inferences
        if isinstance(value, dict)
    } if isinstance(predicted_inferences, list) else set()
    expected_missing = expected.get("missingInformation")
    predicted_missing = predicted.get("missingInformation")
    return EvaluationScores(
        legal_relevance=float(
            predicted.get("legalRelevance") == expected.get("legalRelevance")
        ),
        category=float(predicted_category == expected.get("category")),
        deadline=float(
            _canonical_deadlines(predicted.get("deadlineCandidates"))
            == _canonical_deadlines(expected.get("deadlines"))
        ),
        message_role=float(predicted.get("messageRole") == expected.get("messageRole")),
        facts=_set_f1(expected_statements, predicted_statements),
        missing_information=_set_f1(
            {_normalized_text(value) for value in expected_missing}
            if isinstance(expected_missing, list)
            else set(),
            {_normalized_text(value) for value in predicted_missing}
            if isinstance(predicted_missing, list)
            else set(),
        ),
        fact_citation_correct=citation_correct,
        fact_citation_total=max(len(expected_facts), len(predicted_facts)),
        inference_false_positive_count=len(
            predicted_inference_statements - expected_inference_statements
        ),
        inference_prediction_count=len(predicted_inference_statements),
    )


@dataclass(frozen=True, slots=True)
class RunEvaluationCommand:
    fixture_path: str | Path
    runtime_type: EvaluationRuntimeType
    allow_real_runtime: bool
    actor_id: str
    actor_source: str
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class EvaluationRunReport:
    run: EvaluationRun
    results: tuple[EvaluationResult, ...]


@dataclass(frozen=True, slots=True)
class _PersistedRunStart:
    cases: tuple[EvaluationCase, ...]
    replay_run_id: UUID | None = None


class EvaluationService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        fake_executor: EvaluationExecutor | None = None,
        real_executor: EvaluationExecutor | None = None,
        real_runtime_enabled: bool = False,
    ) -> None:
        self._uow_factory = uow_factory
        self._fake_executor = fake_executor or FakeEvaluationExecutor()
        self._real_executor = real_executor
        self._real_runtime_enabled = real_runtime_enabled

    async def run(self, command: RunEvaluationCommand) -> EvaluationRunReport:
        if command.runtime_type == EvaluationRuntimeType.REAL:
            if not command.allow_real_runtime:
                raise EvaluationRuntimeDisabledError(
                    "Real Codex evaluation requires allowRealRuntime=true.",
                    details={"reason": "explicit_approval_required"},
                )
            if not self._real_runtime_enabled or self._real_executor is None:
                reason = (
                    "server_feature_disabled"
                    if not self._real_runtime_enabled
                    else "runner_unreachable"
                )
                raise EvaluationRuntimeDisabledError(
                    "Real Codex evaluation requires an enabled dedicated Runner.",
                    details={"reason": reason},
                )
            executor = self._real_executor
        else:
            executor = self._fake_executor
        suite = load_evaluation_fixture(command.fixture_path)
        definition = build_message_judgement_definition()
        run = EvaluationRun(
            id=uuid4(),
            suite_key=suite.suite_key,
            suite_version=suite.version,
            runtime_type=command.runtime_type,
            agent_key=suite.agent_key,
            agent_definition_version=definition.version,
            status=EvaluationRunStatus.RUNNING,
            requested_by=command.actor_id,
            correlation_id=command.correlation_id,
            started_at=datetime.now(UTC),
            allow_real_runtime=command.allow_real_runtime,
        )
        persisted_start = await self._persist_run_start(
            suite=suite,
            run=run,
            actor_source=command.actor_source,
            idempotency_key=command.idempotency_key,
        )
        if persisted_start.replay_run_id is not None:
            return await self.get_report(persisted_start.replay_run_id)
        cases = persisted_start.cases
        results: list[EvaluationResult] = []
        for fixture_case, stored_case in zip(suite.cases, cases, strict=True):
            execution = await executor.execute(fixture_case, evaluation_run_id=run.id)
            expected_facts = fixture_case.expected_output.get("facts")
            scores = (
                score_evaluation_output(fixture_case, execution.output)
                if execution.output is not None
                else EvaluationScores(
                    legal_relevance=0,
                    category=0,
                    deadline=0,
                    message_role=0,
                    facts=0,
                    missing_information=0,
                    fact_citation_correct=0,
                    fact_citation_total=(
                        len(expected_facts) if isinstance(expected_facts, list) else 0
                    ),
                    inference_false_positive_count=0,
                    inference_prediction_count=0,
                )
            )
            result = EvaluationResult(
                id=uuid4(),
                evaluation_run_id=run.id,
                evaluation_case_id=stored_case.id,
                result_payload=(
                    execution.output.model_dump(by_alias=True, mode="json")
                    if execution.output is not None
                    else {}
                ),
                scores=scores.to_dict(),
                expected_relevant=(
                    fixture_case.expected_output.get("legalRelevance") != "irrelevant"
                ),
                candidate_created=(
                    should_create_candidate(execution.output)
                    if execution.output is not None
                    else False
                ),
                schema_first_pass=execution.schema_first_pass,
                duration_ms=execution.duration_ms,
                retry_count=execution.retry_count,
                failure_code=execution.failure_code,
                runtime_version=execution.runtime_version,
                runtime_execution_id=execution.runtime_execution_id,
            )
            async with self._uow_factory() as uow:
                await uow.evaluations.add_result(result)
                await uow.commit()
            results.append(result)
        metrics = aggregate_evaluation_metrics(results)
        async with self._uow_factory() as uow:
            stored_run = await uow.evaluations.get_run_for_update(run.id)
            if stored_run is None:
                raise EntityNotFoundError("Evaluation run disappeared before completion.")
            stored_run.complete(metrics=metrics.to_dict())
            await uow.evaluations.save_run(stored_run)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="evaluation_run",
                    aggregate_id=run.id,
                    event_type="evaluation_run_completed",
                    actor_id=command.actor_id,
                    actor_source=command.actor_source,
                    payload={
                        "runtimeType": command.runtime_type.value,
                        "caseCount": len(results),
                        "failureRate": metrics.failure_rate,
                    },
                    correlation_id=command.correlation_id,
                )
            )
            await uow.commit()
            run = stored_run
        return EvaluationRunReport(run=run, results=tuple(results))

    async def get_report(self, run_id: UUID) -> EvaluationRunReport:
        async with self._uow_factory() as uow:
            run = await uow.evaluations.get_run(run_id)
            if run is None:
                raise EntityNotFoundError("Evaluation run was not found.")
            results = await uow.evaluations.list_results(run_id)
        return EvaluationRunReport(run=run, results=tuple(results))

    async def _persist_run_start(
        self,
        *,
        suite: EvaluationFixtureSuite,
        run: EvaluationRun,
        actor_source: str,
        idempotency_key: str,
    ) -> _PersistedRunStart:
        request_hash = sha256(
            json.dumps(
                {
                    "suiteKey": suite.suite_key,
                    "suiteVersion": suite.version,
                    "runtimeType": run.runtime_type.value,
                    "allowRealRuntime": run.allow_real_runtime,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        cases: list[EvaluationCase] = []
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation="evaluation_fixture_suite",
                key=f"{suite.suite_key}:v{suite.version}",
            )
            await uow.lock_idempotency(
                operation="run_message_judgement_evaluation",
                key=idempotency_key,
            )
            replay = await uow.idempotency.get(
                operation="run_message_judgement_evaluation",
                key=idempotency_key,
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was used for a different evaluation request."
                    )
                return _PersistedRunStart(
                    cases=(),
                    replay_run_id=UUID(str(replay.response_payload["evaluationRunId"])),
                )
            for fixture_case in suite.cases:
                stored = await uow.evaluations.get_case(
                    suite_key=suite.suite_key,
                    case_key=fixture_case.case_key,
                    case_version=fixture_case.case_version,
                )
                if stored is not None:
                    if stored.content_hash != fixture_case.content_hash:
                        raise EvaluationFixtureConflictError(
                            "An immutable evaluation case version has different content.",
                            details={
                                "suiteKey": suite.suite_key,
                                "caseKey": fixture_case.case_key,
                                "caseVersion": fixture_case.case_version,
                            },
                        )
                    cases.append(stored)
                    continue
                stored = EvaluationCase(
                    id=uuid4(),
                    suite_key=suite.suite_key,
                    case_key=fixture_case.case_key,
                    case_version=fixture_case.case_version,
                    agent_key=suite.agent_key,
                    input_payload=fixture_case.input_payload,
                    expected_output=fixture_case.expected_output,
                    content_hash=fixture_case.content_hash,
                    data_classification=suite.data_classification,
                )
                await uow.evaluations.add_case(stored)
                cases.append(stored)
            await uow.evaluations.add_run(run)
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation="run_message_judgement_evaluation",
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_payload={"evaluationRunId": str(run.id)},
                )
            )
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="evaluation_run",
                    aggregate_id=run.id,
                    event_type="evaluation_run_started",
                    actor_id=run.requested_by,
                    actor_source=actor_source,
                    payload={
                        "suiteKey": run.suite_key,
                        "suiteVersion": run.suite_version,
                        "runtimeType": run.runtime_type.value,
                        "agentDefinitionVersion": run.agent_definition_version,
                    },
                    correlation_id=run.correlation_id,
                )
            )
            await uow.commit()
        return _PersistedRunStart(cases=tuple(cases))
