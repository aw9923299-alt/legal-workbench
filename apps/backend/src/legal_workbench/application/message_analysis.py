from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from legal_workbench.agents.definitions import (
    MESSAGE_JUDGEMENT_KEY,
    build_message_judgement_definition,
)
from legal_workbench.agents.message_judgement import (
    JudgementActionability,
    JudgementLegalRelevance,
    JudgementMessageRole,
    candidate_requires_manual_review,
    should_create_candidate,
)
from legal_workbench.agents.runtime import (
    AgentExecutionContext,
    AgentRuntime,
    AgentRuntimeError,
)
from legal_workbench.application.agent_attempts import AgentAttemptService
from legal_workbench.application.context_snapshots import ContextSnapshotBuilder
from legal_workbench.application.ports import UnitOfWork, UnitOfWorkFactory
from legal_workbench.domain.entities import (
    AgentAttemptLease,
    AgentDefinition,
    AgentRun,
    AgentRunSource,
    AuditEvent,
    CandidateRevision,
    ContextSnapshot,
    IdempotencyRecord,
    MessageCandidate,
    OutboxEvent,
)
from legal_workbench.domain.enums import (
    AgentAttemptStatus,
    AgentRunSourceType,
    AgentRunStatus,
    CandidateStatus,
    FeishuMessageStatus,
    LegalRelevance,
    MessageRole,
    RecommendedAction,
)
from legal_workbench.domain.errors import (
    EntityNotFoundError,
    IdempotencyConflictError,
    InvalidStateTransitionError,
)


@dataclass(frozen=True, slots=True)
class AnalyseFeishuMessageCommand:
    message_id: UUID
    actor_id: str
    actor_source: str
    correlation_id: str
    force_new_run: bool = False
    recover_interrupted_run: bool = False
    worker_id: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyseFeishuMessageResult:
    message_id: UUID
    agent_run_id: UUID
    status: AgentRunStatus
    candidate_id: UUID | None
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class PreparedAnalysis:
    run: AgentRun | None
    definition: AgentDefinition | None
    snapshot: ContextSnapshot | None
    idempotent_result: AnalyseFeishuMessageResult | None = None


class MessageAnalysisError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class RequestFeishuMessageAnalysisCommand:
    message_id: UUID
    actor_id: str
    actor_source: str
    correlation_id: str
    idempotency_key: str
    force_new_run: bool = False


@dataclass(frozen=True, slots=True)
class RequestFeishuMessageAnalysisResult:
    message_id: UUID
    status: FeishuMessageStatus
    idempotent_replay: bool = False


class RequestFeishuMessageAnalysisHandler:
    OPERATION = "request_feishu_message_analysis"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, command: RequestFeishuMessageAnalysisCommand
    ) -> RequestFeishuMessageAnalysisResult:
        request_hash = sha256(
            json.dumps(
                {
                    "messageId": str(command.message_id),
                    "forceNewRun": command.force_new_run,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.idempotency_key)
            replay = await uow.idempotency.get(
                operation=self.OPERATION, key=command.idempotency_key
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was used for a different analysis request.",
                    )
                return RequestFeishuMessageAnalysisResult(
                    message_id=UUID(str(replay.response_payload["messageId"])),
                    status=FeishuMessageStatus(str(replay.response_payload["status"])),
                    idempotent_replay=True,
                )
            message = await uow.feishu.get_message_for_update(command.message_id)
            if message is None:
                raise EntityNotFoundError(
                    "Feishu message was not found.",
                    details={"code": "FEISHU_MESSAGE_NOT_FOUND"},
                )
            if message.status == FeishuMessageStatus.RECEIVED or (
                command.force_new_run
                and message.status
                in {
                    FeishuMessageStatus.CANDIDATE_CREATED,
                    FeishuMessageStatus.IGNORED,
                    FeishuMessageStatus.ANALYSIS_FAILED,
                    FeishuMessageStatus.DEAD_LETTER,
                }
            ):
                message.transition_to(FeishuMessageStatus.QUEUED_FOR_ANALYSIS)
                await uow.feishu.save_message(message)
            elif message.status != FeishuMessageStatus.QUEUED_FOR_ANALYSIS:
                raise InvalidStateTransitionError(
                    "Feishu message cannot be queued from its current status.",
                    details={"status": message.status.value},
                )
            event_payload: dict[str, object] = {
                "messageId": str(message.id),
                "actorId": command.actor_id,
                "actorSource": command.actor_source,
                "forceNewRun": command.force_new_run,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="feishu_message",
                    aggregate_id=message.id,
                    event_type="feishu_message_analysis_requested",
                    actor_id=command.actor_id,
                    actor_source=command.actor_source,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="FeishuMessageAnalysisRequested",
                    aggregate_type="feishu_message",
                    aggregate_id=message.id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=request_hash,
                    response_payload={
                        "messageId": str(message.id),
                        "status": message.status.value,
                    },
                )
            )
            await uow.commit()
            return RequestFeishuMessageAnalysisResult(
                message_id=message.id,
                status=message.status,
            )


class AnalyseFeishuMessageHandler:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        runtime: AgentRuntime,
        snapshot_builder: ContextSnapshotBuilder,
        *,
        runs_root: str | Path,
        manual_review_threshold: float,
        default_definition: AgentDefinition | None = None,
        lease_seconds: int = 30,
    ) -> None:
        self._uow_factory = uow_factory
        self._runtime = runtime
        self._snapshot_builder = snapshot_builder
        self._runs_root = Path(runs_root)
        self._manual_review_threshold = manual_review_threshold
        self._default_definition = default_definition or build_message_judgement_definition()
        self._lease_seconds = lease_seconds

    async def execute(self, command: AnalyseFeishuMessageCommand) -> AnalyseFeishuMessageResult:
        try:
            prepared = await self.prepare(command)
        except MessageAnalysisError:
            raise
        except EntityNotFoundError as exc:
            raise MessageAnalysisError(
                "FEISHU_MESSAGE_NOT_FOUND",
                "The Feishu message no longer exists and cannot be analysed.",
                retryable=False,
            ) from exc
        except Exception as exc:
            raise MessageAnalysisError(
                "CONTEXT_BUILD_FAILED",
                "The deterministic analysis context could not be prepared.",
                retryable=True,
            ) from exc
        if prepared.idempotent_result is not None:
            return prepared.idempotent_result
        if prepared.run is None or prepared.definition is None or prepared.snapshot is None:
            raise RuntimeError("Prepared analysis is incomplete.")
        run, lease = await self._mark_running(prepared.run.id, command)

        async def heartbeat() -> None:
            await self._heartbeat(run.id, lease)

        try:
            execution = await self._runtime.execute(
                prepared.definition,
                run,
                AgentExecutionContext(snapshot=prepared.snapshot, heartbeat=heartbeat),
            )
        except AgentRuntimeError as exc:
            await self._persist_failure(
                run.id,
                lease,
                command,
                exc,
                input_payload=run.input_payload,
                working_directory=run.working_directory,
            )
            raise
        except Exception as exc:
            runtime_error = AgentRuntimeError(
                "AGENT_RUNTIME_START_FAILED",
                "Agent runtime failed unexpectedly before producing a result.",
                retryable=True,
            )
            await self._persist_failure(
                run.id,
                lease,
                command,
                runtime_error,
                input_payload=run.input_payload,
                working_directory=run.working_directory,
            )
            raise runtime_error from exc
        return await self._persist_success(
            run.id,
            lease,
            command,
            prepared.definition,
            execution.output.model_dump(by_alias=True, mode="json"),
            execution.raw_stdout,
            execution.raw_stderr,
            run.input_payload,
            run.working_directory,
            runtime_version=execution.runtime_version,
            validation_errors=list(execution.validation_errors),
            repair_attempted=execution.repair_attempted,
            token_usage=execution.token_usage,
        )

    async def prepare(self, command: AnalyseFeishuMessageCommand) -> PreparedAnalysis:
        snapshot = await self._snapshot_builder.build_for_feishu_message(command.message_id)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation="analyse_feishu_message", key=str(command.message_id)
            )
            message = await uow.feishu.get_message_for_update(command.message_id)
            if message is None:
                raise EntityNotFoundError(
                    "Feishu message was not found.",
                    details={"code": "FEISHU_MESSAGE_NOT_FOUND"},
                )
            active_candidate = await uow.candidates.get_active_for_message(message.id)
            runs = list(await uow.agent_runs.list_by_message(message.id))
            if not command.force_new_run:
                if active_candidate is not None and active_candidate.agent_run_id is not None:
                    return PreparedAnalysis(
                        run=None,
                        definition=None,
                        snapshot=None,
                        idempotent_result=AnalyseFeishuMessageResult(
                            message_id=message.id,
                            agent_run_id=active_candidate.agent_run_id,
                            status=AgentRunStatus.COMPLETED,
                            candidate_id=active_candidate.id,
                            idempotent_replay=True,
                        ),
                    )
                if message.status == FeishuMessageStatus.IGNORED and runs:
                    return PreparedAnalysis(
                        run=None,
                        definition=None,
                        snapshot=None,
                        idempotent_result=AnalyseFeishuMessageResult(
                            message_id=message.id,
                            agent_run_id=runs[0].id,
                            status=runs[0].status,
                            candidate_id=None,
                            idempotent_replay=True,
                        ),
                    )
                if (
                    command.recover_interrupted_run
                    and runs
                    and runs[0].status == AgentRunStatus.QUEUED
                ):
                    definition = await uow.agent_definitions.get(runs[0].agent_definition_id)
                    if definition is None:
                        raise MessageAnalysisError(
                            "AGENT_DEFINITION_NOT_FOUND",
                            "The queued AgentDefinition no longer exists.",
                            retryable=False,
                        )
                    return PreparedAnalysis(
                        run=runs[0], definition=definition, snapshot=snapshot
                    )
                if (
                    command.recover_interrupted_run
                    and runs
                    and runs[0].status
                    in {AgentRunStatus.PREPARING, AgentRunStatus.RUNNING}
                ):
                    interrupted = runs[0]
                    await AgentAttemptService(
                        uow.agent_run_attempts,
                        lease_seconds=self._lease_seconds,
                    ).expire_current(
                        run_id=interrupted.id,
                        attempt_number=interrupted.attempt_number,
                    )
                    interrupted.failure_code = "AGENT_RUNTIME_START_FAILED"
                    interrupted.failure_message = "Worker delivery was interrupted and recovered."
                    interrupted.transition_to(AgentRunStatus.FAILED)
                    message.transition_to(
                        FeishuMessageStatus.ANALYSIS_FAILED,
                        failure_code=interrupted.failure_code,
                        failure_message=interrupted.failure_message,
                    )
                    await uow.agent_runs.save(interrupted)
                    await uow.feishu.save_message(message)
                    if interrupted.attempt_number >= interrupted.max_attempts:
                        interrupted.transition_to(AgentRunStatus.DEAD_LETTER)
                        message.transition_to(
                            FeishuMessageStatus.DEAD_LETTER,
                            failure_code=interrupted.failure_code,
                            failure_message=interrupted.failure_message,
                        )
                        await uow.agent_runs.save(interrupted)
                        await uow.feishu.save_message(message)
                        await uow.commit()
                        return PreparedAnalysis(
                            run=None,
                            definition=None,
                            snapshot=None,
                            idempotent_result=AnalyseFeishuMessageResult(
                                message_id=message.id,
                                agent_run_id=interrupted.id,
                                status=interrupted.status,
                                candidate_id=None,
                                idempotent_replay=True,
                            ),
                        )
                if runs and runs[0].status in {
                    AgentRunStatus.QUEUED,
                    AgentRunStatus.PREPARING,
                    AgentRunStatus.RUNNING,
                    AgentRunStatus.VALIDATING,
                }:
                    return PreparedAnalysis(
                        run=None,
                        definition=None,
                        snapshot=None,
                        idempotent_result=AnalyseFeishuMessageResult(
                            message_id=message.id,
                            agent_run_id=runs[0].id,
                            status=runs[0].status,
                            candidate_id=None,
                            idempotent_replay=True,
                        ),
                    )
                retry = self._retryable_run(runs)
                if retry is not None:
                    definition = await uow.agent_definitions.get(retry.agent_definition_id)
                    if definition is None:
                        raise MessageAnalysisError(
                            "AGENT_DEFINITION_NOT_FOUND",
                            "The AgentDefinition used by the failed run no longer exists.",
                            retryable=False,
                        )
                    retry.attempt_number += 1
                    retry.transition_to(AgentRunStatus.QUEUED)
                    retry.timeout_at = datetime.now(UTC) + timedelta(
                        seconds=definition.timeout_seconds
                    )
                    retry.finished_at = None
                    retry.failure_code = None
                    retry.failure_message = None
                    await uow.agent_runs.save(retry)
                    message.transition_to(FeishuMessageStatus.QUEUED_FOR_ANALYSIS)
                    message.context_snapshot_id = snapshot.id
                    message.last_agent_run_id = retry.id
                    message.transition_to(FeishuMessageStatus.CONTEXT_PREPARED)
                    message.transition_to(FeishuMessageStatus.AGENT_QUEUED)
                    await uow.feishu.save_message(message)
                    await uow.audit_events.add(
                        AuditEvent(
                            id=uuid4(),
                            aggregate_type="agent_run",
                            aggregate_id=retry.id,
                            event_type="agent_run_requeued",
                            actor_id=command.actor_id,
                            actor_source=command.actor_source,
                            payload={
                                "messageId": str(message.id),
                                "attemptNumber": retry.attempt_number,
                                "recoveredInterruptedRun": command.recover_interrupted_run,
                            },
                            correlation_id=command.correlation_id,
                        )
                    )
                    await uow.commit()
                    return PreparedAnalysis(run=retry, definition=definition, snapshot=snapshot)
                if runs and runs[0].status in {
                    AgentRunStatus.COMPLETED,
                    AgentRunStatus.NEEDS_MORE_INFORMATION,
                    AgentRunStatus.FAILED,
                    AgentRunStatus.TIMED_OUT,
                    AgentRunStatus.CANCELLED,
                    AgentRunStatus.DEAD_LETTER,
                }:
                    return PreparedAnalysis(
                        run=None,
                        definition=None,
                        snapshot=None,
                        idempotent_result=AnalyseFeishuMessageResult(
                            message_id=message.id,
                            agent_run_id=runs[0].id,
                            status=runs[0].status,
                            candidate_id=(active_candidate.id if active_candidate else None),
                            idempotent_replay=True,
                        ),
                    )
            definition = await uow.agent_definitions.get_active(MESSAGE_JUDGEMENT_KEY)
            if definition is None:
                existing_definition = await uow.agent_definitions.get(
                    self._default_definition.id
                )
                if existing_definition is not None:
                    raise MessageAnalysisError(
                        "AGENT_DEFINITION_DISABLED",
                        "The configured message judgement AgentDefinition is not active.",
                        retryable=False,
                    )
                definition = self._default_definition
                await uow.agent_definitions.add(definition)
            try:
                definition.ensure_executable()
            except InvalidStateTransitionError as exc:
                raise MessageAnalysisError(
                    "AGENT_DEFINITION_DISABLED",
                    "The configured message judgement AgentDefinition is not active.",
                    retryable=False,
                ) from exc
            if message.status in {
                FeishuMessageStatus.RECEIVED,
                FeishuMessageStatus.CANDIDATE_CREATED,
                FeishuMessageStatus.IGNORED,
                FeishuMessageStatus.ANALYSIS_FAILED,
                FeishuMessageStatus.DEAD_LETTER,
            }:
                message.transition_to(FeishuMessageStatus.QUEUED_FOR_ANALYSIS)
            if message.status != FeishuMessageStatus.QUEUED_FOR_ANALYSIS:
                raise InvalidStateTransitionError(
                    "Feishu message is already being analysed.",
                    details={"status": message.status.value},
                )
            run_id = uuid4()
            run = AgentRun(
                id=run_id,
                agent_definition_id=definition.id,
                feishu_message_id=message.id,
                context_snapshot_id=snapshot.id,
                status=AgentRunStatus.QUEUED,
                objective="Analyse the authorized Feishu message and propose a candidate.",
                prompt_snapshot=definition.prompt_template,
                working_directory=str(self._runs_root / str(run_id)),
                attempt_number=1,
                max_attempts=definition.max_retries + 1,
                timeout_at=datetime.now(UTC) + timedelta(seconds=definition.timeout_seconds),
                correlation_id=command.correlation_id,
                created_by=command.actor_id,
                agent_definition_version=definition.version,
                prompt_version=definition.version,
                worker_id=command.worker_id,
            )
            await uow.agent_runs.add(run)
            await uow.agent_run_sources.add_many(self._sources(run, snapshot))
            message.context_snapshot_id = snapshot.id
            message.last_agent_run_id = run.id
            message.transition_to(FeishuMessageStatus.CONTEXT_PREPARED)
            message.transition_to(FeishuMessageStatus.AGENT_QUEUED)
            await uow.feishu.save_message(message)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="agent_run",
                    aggregate_id=run.id,
                    event_type="agent_run_prepared",
                    actor_id=command.actor_id,
                    actor_source=command.actor_source,
                    payload={
                        "messageId": str(message.id),
                        "contextSnapshotId": str(snapshot.id),
                        "agentKey": definition.key,
                        "agentVersion": definition.version,
                    },
                    correlation_id=command.correlation_id,
                )
            )
            await uow.commit()
            return PreparedAnalysis(run=run, definition=definition, snapshot=snapshot)

    async def _mark_running(
        self, run_id: UUID, command: AnalyseFeishuMessageCommand
    ) -> tuple[AgentRun, AgentAttemptLease]:
        async with self._uow_factory() as uow:
            run = await uow.agent_runs.get_for_update(run_id)
            if run is None or run.feishu_message_id is None:
                raise MessageAnalysisError(
                    "AGENT_RUNTIME_START_FAILED",
                    "Prepared AgentRun could not be loaded.",
                    retryable=True,
                )
            message = await uow.feishu.get_message_for_update(run.feishu_message_id)
            if message is None:
                raise MessageAnalysisError(
                    "FEISHU_MESSAGE_NOT_FOUND",
                    "Feishu message disappeared before runtime execution.",
                    retryable=False,
                )
            run.transition_to(AgentRunStatus.PREPARING)
            run.transition_to(AgentRunStatus.RUNNING)
            run.worker_id = command.worker_id or run.worker_id or "analysis-worker"
            run.lease_expires_at = datetime.now(UTC) + timedelta(
                seconds=self._lease_seconds
            )
            lease = await AgentAttemptService(
                uow.agent_run_attempts,
                lease_seconds=self._lease_seconds,
            ).claim(
                run_id=run.id,
                attempt_number=run.attempt_number,
                worker_id=run.worker_id,
            )
            message.transition_to(FeishuMessageStatus.ANALYSING)
            await uow.agent_runs.save(run)
            await uow.feishu.save_message(message)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="agent_run",
                    aggregate_id=run.id,
                    event_type="agent_run_started",
                    actor_id=command.actor_id,
                    actor_source=command.actor_source,
                    payload={"attemptNumber": run.attempt_number},
                    correlation_id=command.correlation_id,
                )
            )
            await uow.commit()
            return run, lease

    async def _heartbeat(self, run_id: UUID, lease: AgentAttemptLease) -> None:
        async with self._uow_factory() as uow:
            run = await uow.agent_runs.get_for_update(run_id)
            if run is None:
                return
            run.lease_expires_at = await AgentAttemptService(
                uow.agent_run_attempts,
                lease_seconds=self._lease_seconds,
            ).heartbeat(lease)
            run.heartbeat()
            await uow.agent_runs.save(run)
            await uow.commit()

    async def _persist_success(
        self,
        run_id: UUID,
        lease: AgentAttemptLease,
        command: AnalyseFeishuMessageCommand,
        definition: AgentDefinition,
        output_payload: dict[str, object],
        raw_stdout: str,
        raw_stderr: str,
        input_payload: dict[str, object],
        working_directory: str,
        runtime_version: str | None,
        validation_errors: list[str],
        repair_attempted: bool,
        token_usage: dict[str, int] | None,
    ) -> AnalyseFeishuMessageResult:
        from legal_workbench.agents.message_judgement import MessageJudgementResult

        output = MessageJudgementResult.model_validate(output_payload)
        async with self._uow_factory() as uow:
            run = await uow.agent_runs.get_for_update(run_id)
            if run is None or run.feishu_message_id is None:
                raise RuntimeError("AgentRun disappeared before result persistence.")
            message = await uow.feishu.get_message_for_update(run.feishu_message_id)
            if message is None:
                raise RuntimeError("FeishuMessage disappeared before result persistence.")
            await AgentAttemptService(
                uow.agent_run_attempts,
                lease_seconds=self._lease_seconds,
            ).complete(lease)
            run.transition_to(AgentRunStatus.VALIDATING)
            run.output_payload = output_payload
            run.input_payload = input_payload
            run.raw_stdout = raw_stdout
            run.raw_stderr = raw_stderr
            run.working_directory = working_directory
            run.failure_code = None
            run.failure_message = None
            run.runtime_version = runtime_version
            run.validation_errors = validation_errors
            run.repair_attempted = repair_attempted
            run.token_usage = token_usage
            run.lease_expires_at = None
            run.transition_to(AgentRunStatus.COMPLETED)
            candidate_id: UUID | None = None
            existing = await uow.candidates.get_active_for_message(message.id)
            if should_create_candidate(output):
                category_proposals = self._candidate_categories(output)
                requires_manual_review = (
                    definition.requires_human_review
                    or candidate_requires_manual_review(
                        output, threshold=self._manual_review_threshold
                    )
                )
                if existing is None:
                    candidate = MessageCandidate.create(
                        context_snapshot_id=run.context_snapshot_id,
                        status=CandidateStatus.PENDING_CONFIRMATION,
                        legal_relevance=self._candidate_relevance(output.legal_relevance),
                        message_role=self._candidate_role(output.message_role),
                        recommended_action=self._candidate_action(output.actionability),
                        confidence=output.confidence,
                        title_proposal=output.suggested_title,
                        category_proposals=category_proposals,
                        deadline_proposals=[
                            value.model_dump(by_alias=True, mode="json")
                            for value in output.deadline_candidates
                        ],
                        related_matter_proposals=[],
                        evidence_refs=[fact.source_message_id for fact in output.confirmed_facts],
                        agent_run_id=run.id,
                    )
                    candidate.feishu_message_id = message.id
                    candidate.requires_manual_review = requires_manual_review
                    candidate.analysis_payload = output_payload
                    await uow.candidates.add(candidate)
                    candidate_id = candidate.id
                    await uow.outbox_events.add(
                        OutboxEvent(
                            id=uuid4(),
                            event_type="MessageCandidateCreated",
                            aggregate_type="message_candidate",
                            aggregate_id=candidate.id,
                            payload={
                                "messageId": str(message.id),
                                "agentRunId": str(run.id),
                                "requiresManualReview": candidate.requires_manual_review,
                            },
                            correlation_id=command.correlation_id,
                        )
                    )
                elif existing.status in {
                    CandidateStatus.PENDING_ANALYSIS,
                    CandidateStatus.PENDING_CONFIRMATION,
                }:
                    existing.replace_pending_analysis(
                        context_snapshot_id=run.context_snapshot_id,
                        legal_relevance=self._candidate_relevance(output.legal_relevance),
                        message_role=self._candidate_role(output.message_role),
                        recommended_action=self._candidate_action(output.actionability),
                        confidence=output.confidence,
                        title_proposal=output.suggested_title,
                        category_proposals=category_proposals,
                        deadline_proposals=[
                            value.model_dump(by_alias=True, mode="json")
                            for value in output.deadline_candidates
                        ],
                        evidence_refs=[
                            fact.source_message_id for fact in output.confirmed_facts
                        ],
                        agent_run_id=run.id,
                        requires_manual_review=requires_manual_review,
                        analysis_payload=output_payload,
                    )
                    await uow.candidates.save(existing)
                    candidate_id = existing.id
                else:
                    # Human-confirmed values are immutable. A forced diagnostic
                    # rerun is retained on AgentRun but cannot overwrite them.
                    candidate_id = existing.id
                message.transition_to(FeishuMessageStatus.CANDIDATE_CREATED)
            else:
                if existing is not None and existing.status in {
                    CandidateStatus.PENDING_ANALYSIS,
                    CandidateStatus.PENDING_CONFIRMATION,
                }:
                    existing.reject_superseded_analysis()
                    await uow.candidates.save(existing)
                    await uow.audit_events.add(
                        AuditEvent(
                            id=uuid4(),
                            aggregate_type="message_candidate",
                            aggregate_id=existing.id,
                            event_type="message_candidate_superseded",
                            actor_id=command.actor_id,
                            actor_source=command.actor_source,
                            payload={"supersededByAgentRunId": str(run.id)},
                            correlation_id=command.correlation_id,
                        )
                    )
                if existing is not None and existing.status in {
                    CandidateStatus.CONFIRMED,
                    CandidateStatus.LINKED,
                }:
                    candidate_id = existing.id
                    message.transition_to(FeishuMessageStatus.CANDIDATE_CREATED)
                else:
                    message.transition_to(FeishuMessageStatus.IGNORED)
            revision_candidate_id = existing.id if existing is not None else candidate_id
            if revision_candidate_id is not None:
                await self._append_candidate_revision(
                    uow,
                    candidate_id=revision_candidate_id,
                    agent_run_id=run.id,
                    analysis_payload=output_payload,
                )
            await uow.agent_runs.save(run)
            await uow.feishu.save_message(message)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="agent_run",
                    aggregate_id=run.id,
                    event_type="message_analysis_completed",
                    actor_id=command.actor_id,
                    actor_source=command.actor_source,
                    payload={
                        "messageId": str(message.id),
                        "candidateId": str(candidate_id) if candidate_id else None,
                        "legalRelevance": output.legal_relevance.value,
                        "confidence": output.confidence,
                    },
                    correlation_id=command.correlation_id,
                )
            )
            await uow.commit()
            return AnalyseFeishuMessageResult(
                message_id=message.id,
                agent_run_id=run.id,
                status=run.status,
                candidate_id=candidate_id,
                idempotent_replay=False,
            )

    @staticmethod
    async def _append_candidate_revision(
        uow: UnitOfWork,
        *,
        candidate_id: UUID,
        agent_run_id: UUID,
        analysis_payload: dict[str, object],
    ) -> None:
        existing_revisions = await uow.candidates.list_revisions(candidate_id)
        revision_number = (
            max((value.revision for value in existing_revisions), default=0) + 1
        )
        await uow.candidates.append_revision(
            CandidateRevision(
                id=uuid4(),
                candidate_id=candidate_id,
                revision=revision_number,
                agent_run_id=agent_run_id,
                analysis_payload=analysis_payload,
            )
        )

    async def _persist_failure(
        self,
        run_id: UUID,
        lease: AgentAttemptLease,
        command: AnalyseFeishuMessageCommand,
        error: AgentRuntimeError,
        *,
        input_payload: dict[str, object],
        working_directory: str,
    ) -> None:
        async with self._uow_factory() as uow:
            run = await uow.agent_runs.get_for_update(run_id)
            if run is None or run.feishu_message_id is None:
                return
            message = await uow.feishu.get_message_for_update(run.feishu_message_id)
            if message is None:
                return
            attempt_status = {
                "AGENT_RUNTIME_TIMEOUT": AgentAttemptStatus.TIMED_OUT,
                "AGENT_RUNTIME_CANCELLED": AgentAttemptStatus.CANCELLED,
            }.get(error.code, AgentAttemptStatus.FAILED)
            await AgentAttemptService(
                uow.agent_run_attempts,
                lease_seconds=self._lease_seconds,
            ).fail(
                lease,
                status=attempt_status,
                failure_code=error.code,
                failure_message=str(error)[:4000],
            )
            run.raw_stdout = error.raw_stdout
            run.raw_stderr = error.raw_stderr
            run.input_payload = input_payload
            run.working_directory = working_directory
            run.failure_code = error.code
            run.failure_message = str(error)[:4000]
            run.validation_errors = list(error.validation_errors)
            run.repair_attempted = error.repair_attempted
            run.lease_expires_at = None
            target = {
                "AGENT_RUNTIME_TIMEOUT": AgentRunStatus.TIMED_OUT,
                "AGENT_RUNTIME_CANCELLED": AgentRunStatus.CANCELLED,
            }.get(error.code, AgentRunStatus.FAILED)
            run.transition_to(target)
            message.transition_to(
                FeishuMessageStatus.ANALYSIS_FAILED,
                failure_code=error.code,
                failure_message=str(error)[:4000],
            )
            if target != AgentRunStatus.CANCELLED and (
                not error.retryable or run.attempt_number >= run.max_attempts
            ):
                run.transition_to(AgentRunStatus.DEAD_LETTER)
                message.transition_to(
                    FeishuMessageStatus.DEAD_LETTER,
                    failure_code=error.code,
                    failure_message=str(error)[:4000],
                )
            await uow.agent_runs.save(run)
            await uow.feishu.save_message(message)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="agent_run",
                    aggregate_id=run.id,
                    event_type="message_analysis_failed",
                    actor_id=command.actor_id,
                    actor_source=command.actor_source,
                    payload={
                        "messageId": str(message.id),
                        "failureCode": error.code,
                        "retryable": error.retryable,
                        "attemptNumber": run.attempt_number,
                    },
                    correlation_id=command.correlation_id,
                )
            )
            await uow.commit()

    @staticmethod
    def _retryable_run(runs: list[AgentRun]) -> AgentRun | None:
        if not runs:
            return None
        latest = runs[0]
        if (
            latest.status in {AgentRunStatus.FAILED, AgentRunStatus.TIMED_OUT}
            and latest.attempt_number < latest.max_attempts
        ):
            return latest
        return None

    @staticmethod
    def _candidate_categories(output: object) -> list[dict[str, object]]:
        from legal_workbench.agents.message_judgement import MessageJudgementResult

        validated = MessageJudgementResult.model_validate(output)
        proposals: list[dict[str, object]] = []
        for value in validated.category_candidates:
            proposal = value.model_dump(by_alias=True, mode="json")
            if proposal["category"] == "general":
                proposal["category"] = "general_consultation"
            proposals.append(proposal)
        return proposals

    @staticmethod
    def _sources(run: AgentRun, snapshot: ContextSnapshot) -> list[AgentRunSource]:
        sources = [
            AgentRunSource(
                id=uuid4(),
                agent_run_id=run.id,
                source_type=AgentRunSourceType.CONTEXT_SNAPSHOT,
                source_id=str(snapshot.id),
                source_version=str(snapshot.snapshot_version),
                source_hash=snapshot.content_hash,
                display_name="ContextSnapshot",
                citation_metadata={"messageIds": snapshot.message_ids},
            )
        ]
        messages = snapshot.content.get("messages", [])
        by_id = (
            {
                str(value.get("messageId")): value
                for value in messages
                if isinstance(value, dict) and value.get("messageId")
            }
            if isinstance(messages, list)
            else {}
        )
        for message_id in snapshot.message_ids:
            payload = json.dumps(
                by_id.get(message_id, {"messageId": message_id}),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            sources.append(
                AgentRunSource(
                    id=uuid4(),
                    agent_run_id=run.id,
                    source_type=AgentRunSourceType.FEISHU_MESSAGE,
                    source_id=message_id,
                    source_version=None,
                    source_hash=sha256(payload.encode("utf-8")).hexdigest(),
                    display_name=f"Feishu message {message_id}",
                    citation_metadata={},
                )
            )
        for attachment_id in snapshot.attachment_ids:
            sources.append(
                AgentRunSource(
                    id=uuid4(),
                    agent_run_id=run.id,
                    source_type=AgentRunSourceType.ATTACHMENT,
                    source_id=attachment_id,
                    source_version=None,
                    source_hash=sha256(attachment_id.encode("utf-8")).hexdigest(),
                    display_name=f"Attachment metadata {attachment_id}",
                    citation_metadata={"metadataOnly": True},
                )
            )
        return sources

    @staticmethod
    def _candidate_relevance(value: JudgementLegalRelevance) -> LegalRelevance:
        return {
            JudgementLegalRelevance.RELEVANT: LegalRelevance.RELEVANT,
            JudgementLegalRelevance.POSSIBLY_RELEVANT: LegalRelevance.POSSIBLY_RELEVANT,
            JudgementLegalRelevance.IRRELEVANT: LegalRelevance.NOT_RELEVANT,
        }[value]

    @staticmethod
    def _candidate_role(value: JudgementMessageRole) -> MessageRole:
        return {
            JudgementMessageRole.NEW_REQUEST: MessageRole.NEW_REQUEST,
            JudgementMessageRole.EXISTING_MATTER_UPDATE: MessageRole.PROGRESS_UPDATE,
            JudgementMessageRole.SUPPLEMENTAL_MATERIAL: MessageRole.MATERIAL_UPDATE,
            JudgementMessageRole.DEADLINE_CHANGE: MessageRole.DEADLINE_CHANGE,
            JudgementMessageRole.DECISION_RECORD: MessageRole.DECISION,
            JudgementMessageRole.COMPLETION_UPDATE: MessageRole.CLOSURE_SIGNAL,
            JudgementMessageRole.INFORMATION_ONLY: MessageRole.INFORMATION,
        }[value]

    @staticmethod
    def _candidate_action(value: JudgementActionability) -> RecommendedAction:
        return {
            JudgementActionability.CREATE_CANDIDATE: RecommendedAction.CREATE_MATTER,
            JudgementActionability.LINK_CANDIDATE: RecommendedAction.LINK_MATTER,
            JudgementActionability.UPDATE_ONLY: RecommendedAction.UPDATE_MATTER,
            JudgementActionability.IGNORE: RecommendedAction.IGNORE,
        }[value]
