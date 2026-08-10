from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from legal_workbench.agents.definitions import build_message_judgement_definition
from legal_workbench.agents.message_judgement import MessageJudgementResult
from legal_workbench.agents.runtime import (
    AgentExecutionResult,
    AgentRuntimeError,
)
from legal_workbench.application.context_snapshots import ContextSnapshotBuilder
from legal_workbench.application.message_analysis import (
    AnalyseFeishuMessageCommand,
    AnalyseFeishuMessageHandler,
    RequestFeishuMessageAnalysisCommand,
    RequestFeishuMessageAnalysisHandler,
)
from legal_workbench.domain.entities import (
    AgentAttemptLease,
    AgentDefinition,
    AgentRun,
    AgentRunAttempt,
    AgentRunSource,
    AuditEvent,
    CandidateRevision,
    ContextSnapshot,
    FeishuMessage,
    IdempotencyRecord,
    MessageCandidate,
    OutboxEvent,
)
from legal_workbench.domain.enums import (
    AgentAttemptStatus,
    AgentDefinitionStatus,
    AgentRunSourceType,
    AgentRunStatus,
    CandidateStatus,
    FeishuMessageStatus,
)
from legal_workbench.domain.errors import StaleAgentAttemptError


def output_payload(
    *,
    relevance: str = "relevant",
    confidence: float = 0.9,
    category: str = "contract",
) -> dict[str, object]:
    return {
        "legalRelevance": relevance,
        "messageRole": "new_request",
        "actionability": "ignore" if relevance == "irrelevant" else "create_candidate",
        "suggestedTitle": "审核供应商合同",
        "categoryCandidates": [
            {"category": category, "confidence": 0.9, "reason": "明确要求审核合同"}
        ],
        "deadlineCandidates": [],
        "confirmedFacts": [{"statement": "请求审核合同", "sourceMessageId": "om_current"}],
        "inferredFacts": [],
        "missingInformation": [],
        "reasons": ["消息包含法务行动要求"],
        "confidence": confidence,
    }


class FakeRuntime:
    def __init__(
        self,
        state: FakeState,
        *,
        payload: dict[str, object] | None = None,
        error: AgentRuntimeError | None = None,
    ) -> None:
        self.state = state
        self.payload = payload or output_payload()
        self.error = error
        self.calls = 0
        self.saw_open_transaction = False

    async def execute(self, definition, run, context):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.saw_open_transaction = self.state.active_uows > 0
        if self.error:
            raise self.error
        run.input_payload = {"fakeRuntime": True}
        run.working_directory = str(self.state.output_path.parent)
        return AgentExecutionResult(
            output=MessageJudgementResult.model_validate(self.payload),
            raw_stdout="fake stdout",
            raw_stderr="",
            output_path=self.state.output_path,
        )


class SnapshotRepository:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    async def add(self, snapshot: ContextSnapshot) -> None:
        self.state.snapshots[snapshot.id] = snapshot

    async def get(self, snapshot_id: UUID) -> ContextSnapshot | None:
        return self.state.snapshots.get(snapshot_id)

    async def find_by_source_hash(
        self, *, source_type: str, source_id: str, content_hash: str
    ) -> ContextSnapshot | None:
        return next(
            (
                value
                for value in self.state.snapshots.values()
                if value.source_type == source_type
                and value.source_id == source_id
                and value.content_hash == content_hash
            ),
            None,
        )


class FeishuRepository:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    async def get_message_by_id(self, message_id: UUID) -> FeishuMessage | None:
        return self.state.messages.get(message_id)

    async def get_message_for_update(self, message_id: UUID) -> FeishuMessage | None:
        return self.state.messages.get(message_id)

    async def list_context_messages(
        self, message: FeishuMessage, *, limit: int
    ) -> Sequence[FeishuMessage]:
        return [message]

    async def list_attachments(self, message_id: UUID) -> Sequence[object]:
        del message_id
        return []

    async def save_message(self, message: FeishuMessage) -> None:
        self.state.messages[message.id] = message


class DefinitionRepository:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    async def add(self, definition: AgentDefinition) -> None:
        self.state.definitions[definition.id] = definition

    async def get(self, definition_id: UUID) -> AgentDefinition | None:
        return self.state.definitions.get(definition_id)

    async def get_active(self, key: str) -> AgentDefinition | None:
        return next(
            (
                value
                for value in self.state.definitions.values()
                if value.key == key and value.status == AgentDefinitionStatus.ACTIVE
            ),
            None,
        )


class RunRepository:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    async def add(self, run: AgentRun) -> None:
        self.state.runs[run.id] = run

    async def get(self, run_id: UUID) -> AgentRun | None:
        return self.state.runs.get(run_id)

    async def get_for_update(self, run_id: UUID) -> AgentRun | None:
        return self.state.runs.get(run_id)

    async def save(self, run: AgentRun) -> None:
        self.state.runs[run.id] = run

    async def list_by_message(self, message_id: UUID) -> Sequence[AgentRun]:
        return sorted(
            (run for run in self.state.runs.values() if run.feishu_message_id == message_id),
            key=lambda run: run.created_at,
            reverse=True,
        )


class AttemptRepository:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    async def add(self, attempt: AgentRunAttempt) -> None:
        self.state.attempts.append(attempt)

    async def complete(self, lease: AgentAttemptLease, *, finished_at: datetime) -> None:
        self._find(lease).complete(lease, now=finished_at)

    async def heartbeat(
        self,
        lease: AgentAttemptLease,
        *,
        heartbeat_at: datetime,
        lease_expires_at: datetime,
    ) -> None:
        self._find(lease).heartbeat(
            lease,
            heartbeat_at=heartbeat_at,
            lease_expires_at=lease_expires_at,
        )

    async def fail(
        self,
        lease: AgentAttemptLease,
        *,
        status: AgentAttemptStatus,
        failure_code: str,
        failure_message: str,
        finished_at: datetime,
    ) -> None:
        self._find(lease).fail(
            lease,
            status=status,
            failure_code=failure_code,
            failure_message=failure_message,
            now=finished_at,
        )

    async def expire_current(
        self,
        *,
        run_id: UUID,
        attempt_number: int,
        finished_at: datetime,
    ) -> bool:
        attempt = next(
            (
                value
                for value in self.state.attempts
                if value.run_id == run_id
                and value.attempt_number == attempt_number
                and value.status == AgentAttemptStatus.RUNNING
            ),
            None,
        )
        if attempt is None:
            return False
        if attempt.lease_expires_at > finished_at:
            return False
        attempt.expire(now=finished_at)
        return True

    def _find(self, lease: AgentAttemptLease) -> AgentRunAttempt:
        attempt = next(
            (
                value
                for value in self.state.attempts
                if value.run_id == lease.run_id and value.attempt_number == lease.attempt_number
            ),
            None,
        )
        if attempt is None:
            raise StaleAgentAttemptError("The Agent Attempt does not exist.")
        return attempt


class SourceRepository:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    async def add_many(self, sources: Sequence[AgentRunSource]) -> None:
        self.state.sources.extend(sources)


class CandidateRepository:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    async def add(self, candidate: MessageCandidate) -> None:
        self.state.candidates[candidate.id] = candidate

    async def save(self, candidate: MessageCandidate) -> None:
        self.state.candidates[candidate.id] = candidate

    async def get_active_for_message(self, message_id: UUID) -> MessageCandidate | None:
        return next(
            (
                value
                for value in self.state.candidates.values()
                if value.feishu_message_id == message_id
                and value.status == CandidateStatus.PENDING_CONFIRMATION
            ),
            None,
        )

    async def append_revision(self, revision: CandidateRevision) -> None:
        for existing in self.state.candidate_revisions:
            if existing.candidate_id == revision.candidate_id and existing.superseded_at is None:
                existing.superseded_at = revision.created_at
                existing.superseded_by = revision.id
        self.state.candidate_revisions.append(revision)

    async def list_revisions(self, candidate_id: UUID) -> Sequence[CandidateRevision]:
        return [
            value for value in self.state.candidate_revisions if value.candidate_id == candidate_id
        ]


class AppendRepository:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    async def add(self, value: object) -> None:
        self.values.append(value)


class IdempotencyRepository:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    async def get(self, *, operation: str, key: str) -> IdempotencyRecord | None:
        return self.state.idempotency_records.get((operation, key))

    async def add(self, record: IdempotencyRecord) -> None:
        self.state.idempotency_records[(record.operation, record.idempotency_key)] = record


class DocumentRepository:
    async def list_latest_segments(self, attachment_ids: Sequence[UUID]) -> Sequence[object]:
        del attachment_ids
        return []

    async def list_latest_feishu_segments_for_messages(
        self, message_ids: Sequence[UUID]
    ) -> Sequence[object]:
        del message_ids
        return []


class FakeUnitOfWork:
    def __init__(self, state: FakeState) -> None:
        self.state = state
        self.context_snapshots = SnapshotRepository(state)
        self.feishu = FeishuRepository(state)
        self.documents = DocumentRepository()
        self.agent_definitions = DefinitionRepository(state)
        self.agent_runs = RunRepository(state)
        self.agent_run_attempts = AttemptRepository(state)
        self.agent_run_sources = SourceRepository(state)
        self.candidates = CandidateRepository(state)
        self.audit_events = AppendRepository(state.audit_events)
        self.outbox_events = AppendRepository(state.outbox_events)
        self.idempotency = IdempotencyRepository(state)

    async def __aenter__(self) -> FakeUnitOfWork:
        self.state.active_uows += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.state.active_uows -= 1

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        self.state.locks.append((operation, key))

    async def commit(self) -> None:
        self.state.commits += 1


class FakeState:
    def __init__(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        self.messages: dict[UUID, FeishuMessage] = {}
        self.snapshots: dict[UUID, ContextSnapshot] = {}
        self.definitions: dict[UUID, AgentDefinition] = {}
        self.runs: dict[UUID, AgentRun] = {}
        self.attempts: list[AgentRunAttempt] = []
        self.sources: list[AgentRunSource] = []
        self.candidates: dict[UUID, MessageCandidate] = {}
        self.candidate_revisions: list[CandidateRevision] = []
        self.audit_events: list[object] = []
        self.outbox_events: list[object] = []
        self.idempotency_records: dict[tuple[str, str], IdempotencyRecord] = {}
        self.locks: list[tuple[str, str]] = []
        self.commits = 0
        self.active_uows = 0
        self.output_path = tmp_path / "output.json"

    def factory(self) -> FakeUnitOfWork:
        return FakeUnitOfWork(self)


def make_message() -> FeishuMessage:
    return FeishuMessage(
        id=uuid4(),
        event_id=uuid4(),
        tenant_key="tenant",
        message_id="om_current",
        chat_id="oc_chat",
        thread_id=None,
        root_id=None,
        parent_id=None,
        sender_id="ou_sender",
        sender_type="user",
        message_type="text",
        content={"text": "请审核合同"},
        mentions=[],
        create_time=datetime(2026, 8, 1, tzinfo=UTC),
        update_time=None,
        raw_message={},
        status=FeishuMessageStatus.QUEUED_FOR_ANALYSIS,
    )


def make_handler(state: FakeState, runtime: FakeRuntime) -> AnalyseFeishuMessageHandler:
    state.definitions.update(
        {definition.id: definition for definition in [build_message_judgement_definition()]}
    )
    builder = ContextSnapshotBuilder(
        state.factory,
        max_messages=10,
        max_text_characters=5000,
        now=lambda: datetime(2026, 8, 1, tzinfo=UTC),
    )
    return AnalyseFeishuMessageHandler(
        state.factory,
        runtime,
        builder,
        runs_root="/tmp/legal-workbench-test-runs",
        manual_review_threshold=0.75,
    )


@pytest.mark.asyncio
async def test_explicit_recall_override_intent_is_persisted_and_audited(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message

    await RequestFeishuMessageAnalysisHandler(state.factory).execute(
        RequestFeishuMessageAnalysisCommand(
            message_id=message.id,
            actor_id="legal-reviewer",
            actor_source="user",
            correlation_id="corr-explicit-override-request",
            idempotency_key="idem-explicit-override-request",
            override_recalled=True,
        )
    )

    event = next(value for value in state.outbox_events if isinstance(value, OutboxEvent))
    assert event.payload["overrideRecalled"] is True
    assert any(
        isinstance(value, AuditEvent)
        and value.event_type == "recalled_message_manual_analysis_override_requested"
        and value.payload["explicitOverride"] is True
        for value in state.audit_events
    )


@pytest.mark.asyncio
async def test_valid_output_commits_before_runtime_and_creates_candidate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = FakeRuntime(state)

    result = await make_handler(state, runtime).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="system",
            actor_source="worker",
            correlation_id="corr-analysis",
        )
    )

    candidate = state.candidates[result.candidate_id]
    run = state.runs[result.agent_run_id]
    assert runtime.saw_open_transaction is False
    assert candidate.feishu_message_id == message.id
    assert candidate.status == CandidateStatus.PENDING_CONFIRMATION
    assert candidate.requires_manual_review is True
    assert run.status == AgentRunStatus.COMPLETED
    assert run.input_payload == {"fakeRuntime": True}
    assert run.working_directory == str(state.output_path.parent)
    assert state.messages[message.id].status == FeishuMessageStatus.CANDIDATE_CREATED
    assert len(state.candidate_revisions) == 1
    assert any(isinstance(event, AuditEvent) for event in state.audit_events)
    assert any(isinstance(event, OutboxEvent) for event in state.outbox_events)


@pytest.mark.asyncio
async def test_current_builtin_definition_wins_over_stale_active_schema(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    current = build_message_judgement_definition()
    stale = build_message_judgement_definition()
    stale.id = uuid4()
    stale.version = "1.0.0"
    stale.input_schema = {"type": "object"}
    state.definitions = {stale.id: stale, current.id: current}

    result = await make_handler(state, FakeRuntime(state)).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="system",
            actor_source="worker",
            correlation_id="corr-current-definition",
        )
    )

    assert state.runs[result.agent_run_id].agent_definition_id == current.id


@pytest.mark.asyncio
async def test_explicit_manual_analysis_can_override_store_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    message.analysis_disposition = "store_only"
    state.messages[message.id] = message

    result = await make_handler(state, FakeRuntime(state)).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="legal-reviewer",
            actor_source="user",
            correlation_id="corr-manual-store-only",
            force_new_run=True,
        )
    )

    assert result.status == AgentRunStatus.COMPLETED
    assert result.candidate_id is not None


@pytest.mark.asyncio
async def test_recalled_message_worker_delivery_is_audited_noop_before_runtime(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    message.recalled_at = datetime(2026, 8, 9, 1, 10, tzinfo=UTC)
    state.messages[message.id] = message
    runtime = FakeRuntime(state)

    result = await make_handler(state, runtime).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="analysis-worker",
            actor_source="worker",
            correlation_id="corr-recalled-before-runtime",
        )
    )

    assert result.agent_run_id is None
    assert result.status is None
    assert result.candidate_id is None
    assert result.no_op_reason == "message_recalled"
    assert runtime.calls == 0
    assert state.runs == {}
    assert state.candidates == {}
    assert any(
        isinstance(event, AuditEvent)
        and event.event_type == "recalled_message_automatic_analysis_suppressed"
        for event in state.audit_events
    )


@pytest.mark.asyncio
async def test_explicit_user_override_analyses_recalled_message_and_is_audited(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    message.recalled_at = datetime(2026, 8, 9, 1, 12, tzinfo=UTC)
    state.messages[message.id] = message
    runtime = FakeRuntime(state)

    result = await make_handler(state, runtime).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="legal-reviewer",
            actor_source="user",
            correlation_id="corr-recalled-manual-override",
            force_new_run=True,
            override_recalled=True,
        )
    )

    assert result.status == AgentRunStatus.COMPLETED
    assert result.candidate_id is not None
    assert runtime.calls == 1
    assert any(
        isinstance(event, AuditEvent)
        and event.event_type == "recalled_message_manual_analysis_override"
        and event.actor_id == "legal-reviewer"
        and event.actor_source == "user"
        for event in state.audit_events
    )


@pytest.mark.asyncio
async def test_user_source_without_explicit_override_cannot_analyse_recalled_message(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    message.recalled_at = datetime(2026, 8, 9, 1, 13, tzinfo=UTC)
    state.messages[message.id] = message
    runtime = FakeRuntime(state)

    result = await make_handler(state, runtime).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="legal-reviewer",
            actor_source="user",
            correlation_id="corr-recalled-user-without-override",
        )
    )

    assert result.no_op_reason == "message_recalled"
    assert result.candidate_id is None
    assert runtime.calls == 0


class RecallDuringRuntime(FakeRuntime):
    async def execute(self, definition, run, context):  # type: ignore[no-untyped-def]
        execution = await super().execute(definition, run, context)
        self.state.messages[run.feishu_message_id].recalled_at = datetime(
            2026, 8, 9, 1, 15, tzinfo=UTC
        )
        return execution


@pytest.mark.asyncio
async def test_automatic_run_that_started_before_recall_keeps_run_but_not_candidate(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = RecallDuringRuntime(state)

    result = await make_handler(state, runtime).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="analysis-worker",
            actor_source="worker",
            correlation_id="corr-recall-during-runtime",
        )
    )

    assert result.status == AgentRunStatus.COMPLETED
    assert result.agent_run_id is not None
    assert state.runs[result.agent_run_id].output_payload
    assert result.candidate_id is None
    assert result.no_op_reason == "message_recalled"
    assert state.candidates == {}
    assert state.candidate_revisions == []
    assert state.messages[message.id].status == FeishuMessageStatus.IGNORED
    assert any(
        isinstance(event, AuditEvent)
        and event.event_type == "recalled_message_candidate_persistence_suppressed"
        for event in state.audit_events
    )


@pytest.mark.asyncio
async def test_user_request_without_explicit_override_recalled_during_runtime_is_suppressed(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = RecallDuringRuntime(state)

    result = await make_handler(state, runtime).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="legal-reviewer",
            actor_source="user",
            correlation_id="corr-user-recall-during-runtime",
        )
    )

    assert result.status == AgentRunStatus.COMPLETED
    assert result.no_op_reason == "message_recalled"
    assert result.candidate_id is None
    assert state.candidates == {}
    assert state.candidate_revisions == []


@pytest.mark.asyncio
async def test_explicit_override_recalled_during_runtime_persists_candidate_with_audit(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = RecallDuringRuntime(state)

    result = await make_handler(state, runtime).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="legal-reviewer",
            actor_source="user",
            correlation_id="corr-explicit-override-recall-during-runtime",
            override_recalled=True,
        )
    )

    assert result.status == AgentRunStatus.COMPLETED
    assert result.candidate_id is not None
    assert any(
        isinstance(event, AuditEvent)
        and event.event_type == "recalled_message_manual_analysis_override"
        and event.payload["phase"] == "candidate_persistence"
        for event in state.audit_events
    )


@pytest.mark.asyncio
async def test_included_attachment_segment_becomes_a_hashed_run_source(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    result = await make_handler(state, FakeRuntime(state)).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="system",
            actor_source="worker",
            correlation_id="corr-attachment-source",
        )
    )
    run = state.runs[result.agent_run_id]
    snapshot = state.snapshots[run.context_snapshot_id]
    snapshot.included_segments = [
        {
            "attachmentId": "11111111-1111-4111-8111-111111111111",
            "fileName": "合同.pdf",
            "pageNumber": 2,
            "paragraphNumber": 3,
            "contentHash": "c" * 64,
        }
    ]

    sources = AnalyseFeishuMessageHandler._sources(run, snapshot)
    segment_source = next(
        value
        for value in sources
        if value.source_type == AgentRunSourceType.ATTACHMENT
        and value.citation_metadata.get("segment") is True
    )

    assert segment_source.source_hash == "c" * 64
    assert segment_source.source_id.endswith("page:2:paragraph:3")
    assert segment_source.citation_metadata == {
        "segment": True,
        "attachmentId": "11111111-1111-4111-8111-111111111111",
        "fileName": "合同.pdf",
        "pageNumber": 2,
        "paragraphNumber": 3,
    }


@pytest.mark.asyncio
async def test_included_native_document_segment_becomes_a_hashed_run_source(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    result = await make_handler(state, FakeRuntime(state)).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="system",
            actor_source="worker",
            correlation_id="corr-native-document-source",
        )
    )
    run = state.runs[result.agent_run_id]
    snapshot = state.snapshots[run.context_snapshot_id]
    snapshot.included_segments = [
        {
            "documentId": "22222222-2222-4222-8222-222222222222",
            "documentToken": "doccnTest",
            "title": "测试合同",
            "paragraphNumber": 4,
            "contentHash": "d" * 64,
        }
    ]

    sources = AnalyseFeishuMessageHandler._sources(run, snapshot)
    source = next(
        value
        for value in sources
        if value.source_type == AgentRunSourceType.KNOWLEDGE_DOCUMENT
    )

    assert source.source_hash == "d" * 64
    assert source.source_id.endswith("paragraph:4")
    assert source.citation_metadata == {
        "segment": True,
        "documentId": "22222222-2222-4222-8222-222222222222",
        "documentToken": "doccnTest",
        "title": "测试合同",
        "paragraphNumber": 4,
    }


@pytest.mark.asyncio
async def test_irrelevant_output_is_audited_without_candidate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = FakeRuntime(state, payload=output_payload(relevance="irrelevant"))

    result = await make_handler(state, runtime).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="system",
            actor_source="worker",
            correlation_id="corr-ignore",
        )
    )

    assert result.candidate_id is None
    assert state.candidates == {}
    assert state.messages[message.id].status == FeishuMessageStatus.IGNORED


@pytest.mark.asyncio
async def test_general_category_is_mapped_to_matter_contract_value(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = FakeRuntime(state, payload=output_payload(category="general"))

    result = await make_handler(state, runtime).execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="system",
            actor_source="worker",
            correlation_id="corr-general",
        )
    )

    candidate = state.candidates[result.candidate_id]
    assert candidate.category_proposals[0]["category"] == "general_consultation"


@pytest.mark.asyncio
async def test_reanalysis_that_becomes_irrelevant_rejects_pending_candidate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = FakeRuntime(state)
    handler = make_handler(state, runtime)

    first = await handler.execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="system",
            actor_source="worker",
            correlation_id="corr-first",
        )
    )
    runtime.payload = output_payload(relevance="irrelevant")
    second = await handler.execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="system",
            actor_source="worker",
            correlation_id="corr-second",
            force_new_run=True,
        )
    )

    assert second.candidate_id is None
    assert state.candidates[first.candidate_id].status == CandidateStatus.REJECTED
    assert state.messages[message.id].status == FeishuMessageStatus.IGNORED
    assert len(state.runs) == 2
    assert len(state.candidate_revisions) == 2
    assert state.candidate_revisions[0].superseded_by == state.candidate_revisions[1].id


@pytest.mark.asyncio
async def test_runtime_timeout_records_failure_without_candidate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = FakeRuntime(
        state,
        error=AgentRuntimeError("AGENT_RUNTIME_TIMEOUT", "timed out", retryable=True),
    )

    with pytest.raises(AgentRuntimeError):
        await make_handler(state, runtime).execute(
            AnalyseFeishuMessageCommand(
                message_id=message.id,
                actor_id="system",
                actor_source="worker",
                correlation_id="corr-timeout",
            )
        )

    assert state.candidates == {}
    assert state.messages[message.id].status == FeishuMessageStatus.ANALYSIS_FAILED
    assert next(iter(state.runs.values())).status == AgentRunStatus.TIMED_OUT


@pytest.mark.asyncio
async def test_runtime_cancellation_is_terminal_but_allows_manual_retry(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = FakeRuntime(
        state,
        error=AgentRuntimeError("AGENT_RUNTIME_CANCELLED", "cancelled", retryable=False),
    )

    with pytest.raises(AgentRuntimeError):
        await make_handler(state, runtime).execute(
            AnalyseFeishuMessageCommand(
                message_id=message.id,
                actor_id="system",
                actor_source="worker",
                correlation_id="corr-cancelled",
            )
        )

    assert state.messages[message.id].status == FeishuMessageStatus.ANALYSIS_FAILED
    assert next(iter(state.runs.values())).status == AgentRunStatus.CANCELLED


@pytest.mark.asyncio
async def test_duplicate_delivery_does_not_revive_terminal_run(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = FakeRuntime(
        state,
        error=AgentRuntimeError("AGENT_RUNTIME_CANCELLED", "cancelled", retryable=False),
    )
    handler = make_handler(state, runtime)
    command = AnalyseFeishuMessageCommand(
        message_id=message.id,
        actor_id="system",
        actor_source="worker",
        correlation_id="corr-terminal-replay",
    )

    with pytest.raises(AgentRuntimeError):
        await handler.execute(command)
    replay = await handler.execute(command)

    assert replay.idempotent_replay is True
    assert replay.status == AgentRunStatus.CANCELLED
    assert len(state.runs) == 1
    assert runtime.calls == 1


@pytest.mark.asyncio
async def test_idempotent_replay_does_not_create_second_candidate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = FakeRuntime(state)
    handler = make_handler(state, runtime)
    command = AnalyseFeishuMessageCommand(
        message_id=message.id,
        actor_id="system",
        actor_source="worker",
        correlation_id="corr-replay",
    )

    first = await handler.execute(command)
    second = await handler.execute(command)

    assert second.candidate_id == first.candidate_id
    assert len(state.candidates) == 1
    assert len(state.runs) == 1
    assert runtime.calls == 1


@pytest.mark.asyncio
async def test_duplicate_delivery_reuses_in_progress_run(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = FakeRuntime(state)
    handler = make_handler(state, runtime)
    command = AnalyseFeishuMessageCommand(
        message_id=message.id,
        actor_id="system",
        actor_source="worker",
        correlation_id="corr-duplicate",
    )

    first = await handler.prepare(command)
    second = await handler.prepare(command)

    assert first.run is not None
    assert second.idempotent_result is not None
    assert second.idempotent_result.agent_run_id == first.run.id
    assert second.idempotent_result.status == AgentRunStatus.QUEUED
    assert len(state.runs) == 1
    assert runtime.calls == 0


@pytest.mark.asyncio
async def test_redelivered_worker_recovers_running_attempt(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message
    runtime = FakeRuntime(state)
    handler = make_handler(state, runtime)
    command = AnalyseFeishuMessageCommand(
        message_id=message.id,
        actor_id="system",
        actor_source="worker",
        correlation_id="corr-recovered",
    )
    prepared = await handler.prepare(command)
    assert prepared.run is not None
    prepared.run.transition_to(AgentRunStatus.PREPARING)
    prepared.run.transition_to(AgentRunStatus.RUNNING)
    message.transition_to(FeishuMessageStatus.ANALYSING)

    result = await handler.execute(
        AnalyseFeishuMessageCommand(
            message_id=message.id,
            actor_id="system",
            actor_source="worker",
            correlation_id="corr-recovered",
            recover_interrupted_run=True,
        )
    )

    assert result.status == AgentRunStatus.COMPLETED
    assert prepared.run.attempt_number == 2
    assert len(state.runs) == 1
    assert runtime.calls == 1


class LateWorkerRuntime(FakeRuntime):
    async def execute(self, definition, run, context):  # type: ignore[no-untyped-def]
        execution = await super().execute(definition, run, context)
        if state_attempts := self.state.attempts:
            first = state_attempts[-1]
        else:
            first = AgentRunAttempt.start(
                run_id=run.id,
                attempt_number=run.attempt_number,
                lease_token=uuid4(),
                worker_id="worker-late",
                lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
            )
            self.state.attempts.append(first)
        first.expire(now=first.lease_expires_at + timedelta(microseconds=1))
        run.attempt_number += 1
        self.state.attempts.append(
            AgentRunAttempt.start(
                run_id=run.id,
                attempt_number=run.attempt_number,
                lease_token=uuid4(),
                worker_id="worker-current",
                lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
            )
        )
        return execution


@pytest.mark.asyncio
async def test_late_worker_cannot_create_candidate_for_newer_attempt(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = FakeState(tmp_path)
    message = make_message()
    state.messages[message.id] = message

    with pytest.raises(StaleAgentAttemptError):
        await make_handler(state, LateWorkerRuntime(state)).execute(
            AnalyseFeishuMessageCommand(
                message_id=message.id,
                actor_id="system",
                actor_source="worker",
                correlation_id="corr-late-worker",
                worker_id="worker-late",
            )
        )

    assert state.candidates == {}
    assert state.attempts[-1].status == AgentAttemptStatus.RUNNING
