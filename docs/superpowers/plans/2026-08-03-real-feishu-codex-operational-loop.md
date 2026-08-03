# Real Feishu-to-Matter Operational Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the durable downstream loop from persisted Feishu messages and attachments through fenced Codex analysis, human-approved Matter updates, full WorkItem operations, and a PostgreSQL-backed daily workbench, while deferring real Feishu message and official long-connection acceptance.

**Architecture:** Extend the existing Python modular monolith with narrowly scoped domain entities, application services, SQLAlchemy repositories, and Alembic migrations. Every external operation remains outside database transactions; PostgreSQL owns recovery state, Agent Attempt fencing, extracted document text, proposals, evaluations, and dashboard projections. React consumes only FastAPI contracts and contains no runtime Mock data.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Psycopg 3, Alembic, Celery, Redis, PostgreSQL 18, React 18, TypeScript, Vite, TanStack Query, Ant Design, pypdf, python-docx, Docker Compose, launchd.

## Global Constraints

- PostgreSQL is the only business fact store; Redis loss must be recoverable from PostgreSQL.
- Codex is the only reasoning or generation AI; no LangChain, other model, external Embedding, or Qdrant is allowed.
- Worker concurrency remains exactly 1.
- No database transaction may wait for Codex, attachment download, or document parsing.
- Agents create suggestions and Candidates only; formal Matter/WorkItem changes require a verified human Actor.
- Browser Actor IDs are never trusted; writes require Session Actor, Idempotency-Key, Correlation ID, and optimistic version checks.
- Secrets never enter PostgreSQL, Redis, Agent inputs, runtime directories, API responses, or logs.
- Real Feishu test messages and official long-connection acceptance remain `not_executed` until the user restores that phase.
- Personal Feishu login, client UI automation, read-state APIs, automatic outbound messages, OCR, and professional Agents remain prohibited.

## File Responsibility Map

- `domain/entities.py` and `domain/enums.py`: new aggregate state and invariants only; no framework imports.
- `application/agent_attempts.py`: lease-token fencing and stale-worker decisions.
- `application/document_extraction.py`: extraction preparation/result transactions and quota accounting.
- `integrations/document_extractors.py`: isolated parsing of one authorized local file.
- `application/matter_updates.py`: proposal creation and human approval transaction.
- `application/work_item_lifecycle.py`: audited WorkItem commands around domain transitions.
- `application/dashboard.py`: deterministic PostgreSQL-backed daily queue projection.
- `application/evaluations.py`: immutable case execution and metric aggregation.
- `application/setup.py` and `infrastructure/secrets.py`: masked setup state and local Secret storage.
- `infrastructure/models/core.py`, `repositories.py`, and `unit_of_work.py`: persistence mappings and port implementations.
- `api/routes/*` and `api/schemas/*`: HTTP validation and response mapping only.
- `apps/web/src/pages` and `components`: API-driven workflow UI with loading, empty, failure, permission, conflict, and retry states.
- `scripts/legal_workbench_ops.py` and `infra/launchd`: host startup, wake recovery, backup, diagnostics, cleanup, and safe stop.
- migrations `20260803_0007` through `20260803_0012`: independently reversible schema changes in dependency order.

---

### Task 1: Pin Codex Version and Add Attempt Fencing

**Files:**
- Create: `apps/backend/migrations/versions/20260803_0007_add_agent_attempt_fencing.py`
- Create: `apps/backend/src/legal_workbench/application/agent_attempts.py`
- Create: `apps/backend/tests/test_agent_attempt_fencing.py`
- Modify: `.env.example`
- Modify: `compose.yml`
- Modify: `infra/docker/backend.Dockerfile`
- Modify: `apps/backend/src/legal_workbench/config.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/domain/enums.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Modify: `apps/backend/src/legal_workbench/application/message_analysis.py`
- Modify: `apps/backend/src/legal_workbench/application/analysis_recovery.py`
- Modify: `apps/backend/src/legal_workbench/workers/tasks.py`
- Modify: `apps/backend/tests/test_analysis_recovery.py`
- Modify: `apps/backend/tests/test_message_analysis_handler.py`
- Modify: `apps/backend/tests/test_codex_runtime.py`

**Interfaces:**
- Produces: `AgentRunAttempt`, `AgentAttemptLease`, and `AgentRunAttemptRepository`.
- Produces: `claim_attempt(run_id, worker_id, lease_seconds) -> AgentAttemptLease`.
- Produces: conditional `heartbeat`, `complete`, and `fail` methods requiring `run_id + attempt_number + lease_token`.
- Consumes: existing `AgentRun`, `AnalyseFeishuMessageHandler`, and PostgreSQL recovery scan.

- [ ] **Step 1: Write failing domain and repository tests for stale Attempt rejection**

```python
async def test_late_worker_cannot_complete_new_attempt(uow_factory):
    service = AgentAttemptService(uow_factory, lease_seconds=60)
    first = await service.claim(run_id, worker_id="worker-a")
    await service.expire(first, failure_code="AGENT_LEASE_EXPIRED")
    second = await service.claim(run_id, worker_id="worker-b")

    with pytest.raises(StaleAgentAttemptError):
        await service.complete(first)

    stored = await load_attempts(uow_factory, run_id)
    assert stored[-1].lease_token == second.lease_token
    assert stored[-1].status == AgentAttemptStatus.RUNNING
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_agent_attempt_fencing.py -q`

Expected: collection or assertion failure because `AgentRunAttempt` and `AgentAttemptService` do not exist.

- [ ] **Step 3: Add migration and domain types**

Create `agent_run_attempts` with a unique `(run_id, attempt_number)`, unique `lease_token`, indexed `lease_expires_at`, lifecycle timestamps, failure code, and append-only historical rows. Set `CODEX_CLI_VERSION=0.146.0` in `.env.example`, matching the 2026-08-03 host verification; pass it as the Docker build arg and runtime environment; remove the Dockerfile version default.

```python
@dataclass(slots=True, frozen=True)
class AgentAttemptLease:
    run_id: UUID
    attempt_number: int
    lease_token: UUID

class StaleAgentAttemptError(DomainError):
    code = "STALE_AGENT_ATTEMPT"
```

- [ ] **Step 4: Implement conditional repository updates**

```python
stmt = (
    update(AgentRunAttemptModel)
    .where(
        AgentRunAttemptModel.run_id == lease.run_id,
        AgentRunAttemptModel.attempt_number == lease.attempt_number,
        AgentRunAttemptModel.lease_token == lease.lease_token,
        AgentRunAttemptModel.status == AgentAttemptStatus.RUNNING,
    )
    .values(status=AgentAttemptStatus.COMPLETED, finished_at=now)
)
if (await session.execute(stmt)).rowcount != 1:
    raise StaleAgentAttemptError()
```

- [ ] **Step 5: Thread the lease through runtime, heartbeat, success, and failure persistence**

`AnalyseFeishuMessageHandler._mark_running` returns `(AgentRun, AgentAttemptLease)`. Heartbeat and persistence receive that immutable lease. Candidate creation occurs only after the conditional Attempt completion succeeds in the same result transaction.

- [ ] **Step 6: Update PostgreSQL recovery**

Expired attempts become `expired`; recovery creates a new attempt with the next number and token. It never reuses a token and never marks a late result valid.

- [ ] **Step 7: Run RED→GREEN regression**

Run:

```bash
.venv/bin/python -m pytest apps/backend/tests/test_agent_attempt_fencing.py apps/backend/tests/test_analysis_recovery.py apps/backend/tests/test_message_analysis_handler.py apps/backend/tests/test_codex_runtime.py -q
.venv/bin/python -m ruff check apps/backend/src apps/backend/tests
.venv/bin/python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
```

Expected: all focused tests, Ruff, and mypy pass.

- [ ] **Step 8: Commit**

```bash
git add .env.example compose.yml infra/docker/backend.Dockerfile apps/backend
git commit -m "feat: fence Codex agent attempts"
```

---

### Task 2: Persist and Safely Extract Attachment Text

**Files:**
- Create: `apps/backend/migrations/versions/20260803_0008_add_document_extraction.py`
- Create: `apps/backend/src/legal_workbench/application/document_extraction.py`
- Create: `apps/backend/src/legal_workbench/integrations/document_extractors.py`
- Create: `apps/backend/src/legal_workbench/workers/document_tasks.py`
- Create: `apps/backend/tests/test_document_extraction.py`
- Create: `apps/backend/tests/test_document_extraction_process.py`
- Create: `apps/backend/tests/fixtures/documents/sample.txt`
- Create: `apps/backend/tests/fixtures/documents/sample.md`
- Modify: `apps/backend/pyproject.toml`
- Modify: `apps/backend/src/legal_workbench/config.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/domain/enums.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_operations.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/outbox.py`
- Modify: `apps/backend/src/legal_workbench/workers/tasks.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/feishu.py`

**Interfaces:**
- Produces: `MessageAttachment`, `DocumentVersion`, `DocumentExtraction`, `DocumentSegment`.
- Produces: `DocumentExtractor.extract(path, mime_type) -> ExtractedDocument`.
- Produces: `DocumentExtractionService.prepare/complete/fail` with no external work inside a transaction.
- Consumes: existing downloaded attachment rows and Outbox dispatcher.

- [x] **Step 1: Write failing security and format tests**

```python
def test_attachment_path_must_remain_below_root(tmp_path):
    policy = AttachmentPathPolicy(tmp_path / "attachments")
    with pytest.raises(UnsafeAttachmentPathError):
        policy.authorize(tmp_path / "attachments" / ".." / "secret.txt")

def test_scanned_pdf_is_body_unavailable(scanned_pdf):
    result = PdfTextExtractor().extract(scanned_pdf)
    assert result.status == ExtractionStatus.BODY_UNAVAILABLE
    assert result.segments == []
```

Also cover DOCX, TXT, Markdown, oversized files, quota exhaustion, parse timeout, filename sanitization, and no macro/script execution.

- [x] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_document_extraction.py apps/backend/tests/test_document_extraction_process.py -q`

Expected: failure because extraction models and services are absent.

- [x] **Step 3: Add dependencies and migration**

Add `pypdf>=5,<7` and `python-docx>=1.1,<2`. Rename `feishu_attachments` to `message_attachments` while preserving rows; add extraction metadata. Create document version, extraction, segment, and quota reservation tables. Downgrade restores the original table name and columns without deleting migrated attachment rows.

- [x] **Step 4: Implement deterministic extractors**

```python
@dataclass(frozen=True, slots=True)
class ExtractedSegment:
    page_number: int | None
    paragraph_number: int
    start_offset: int
    end_offset: int
    content: str
    content_hash: str

class DocumentExtractor(Protocol):
    def extract(self, path: Path, mime_type: str) -> ExtractedDocument:
        raise NotImplementedError
```

PDF extraction iterates pages without executing actions; DOCX reads paragraph XML only; TXT/Markdown decode UTF-8 with explicit failure codes. Empty PDF text becomes `body_unavailable`.

- [x] **Step 5: Run parser in an isolated bounded process**

Invoke `python -I -m legal_workbench.integrations.document_extractors` with one authorized file path, an output file in a per-extraction `0700` directory, a timeout, and bounded output. The child receives no database, Redis, Feishu, or Codex credentials.

- [x] **Step 6: Implement storage quota and download handoff**

Reserve bytes in PostgreSQL before download, enforce per-file and total limits, write to a safe resolved path with `0600`, compute SHA-256, then enqueue `DocumentExtractionRequested`. Release reservations on deterministic failure.

- [x] **Step 7: Run RED→GREEN regression**

Run:

```bash
.venv/bin/python -m pytest apps/backend/tests/test_document_extraction.py apps/backend/tests/test_document_extraction_process.py apps/backend/tests/test_feishu_ingestion_completion.py -q
.venv/bin/python -m ruff check apps/backend/src apps/backend/tests
.venv/bin/python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
```

- [x] **Step 8: Commit**

```bash
git add apps/backend
git commit -m "feat: extract message attachment content"
```

---

### Task 3: Add Bounded Attachment Segments and Citation Validation

**Files:**
- Create: `apps/backend/tests/test_attachment_context_citations.py`
- Modify: `apps/backend/src/legal_workbench/application/context_snapshots.py`
- Modify: `apps/backend/src/legal_workbench/agents/message_judgement.py`
- Modify: `apps/backend/src/legal_workbench/agents/models.py`
- Modify: `apps/backend/src/legal_workbench/application/message_analysis.py`
- Modify: `apps/backend/src/legal_workbench/application/queries.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/agents.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/feishu.py`
- Modify: `apps/backend/tests/test_context_snapshot_builder.py`
- Modify: `apps/backend/tests/test_message_analysis_handler.py`
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/pages/MessageDetailPage.tsx`

**Interfaces:**
- Consumes: `DocumentSegmentRepository.list_ready_for_attachments` from Task 2.
- Produces: `AttachmentCitation` and Snapshot `includedSegments/excludedSegments`.
- Produces: `validate_attachment_citations(result, snapshot)`.

- [x] **Step 1: Write failing Snapshot and business-rule tests**

```python
async def test_snapshot_records_included_and_excluded_attachment_segments(builder):
    snapshot = await builder.build_for_feishu_message(message_id)
    assert snapshot.content["includedSegments"][0]["contentHash"] == segment_hash
    assert snapshot.content["excludedSegments"]
    assert snapshot.truncated is True

def test_fact_citation_hash_must_match_snapshot():
    with pytest.raises(AgentOutputBusinessRuleError):
        validate_attachment_citations(result_with_wrong_hash, snapshot)
```

- [x] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_attachment_context_citations.py apps/backend/tests/test_context_snapshot_builder.py -q`

- [x] **Step 3: Extend Snapshot selection deterministically**

Select ready segments by attachment ID, page, paragraph, and UUID. Apply maximum segment count, single-segment characters, and total attachment characters. Persist both included identifiers and excluded identifiers with stable truncation reasons.

- [x] **Step 4: Extend Agent fact schema**

```python
class AttachmentCitation(BaseModel):
    attachment_id: UUID
    file_name: str
    page_number: int | None
    paragraph_number: int
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

class ConfirmedFact(BaseModel):
    statement: str
    source_message_id: str | None = None
    attachment_citation: AttachmentCitation | None = None
```

Exactly one evidence source is required. Business validation confirms that the cited attachment segment was included in the immutable Snapshot.

- [x] **Step 5: Persist auditable AgentRun sources and expose citations**

Create one `AgentRunSource` per included attachment segment with the real content hash and locator metadata. The UI renders a linkable page/paragraph citation and never exposes unrestricted local paths.

- [x] **Step 6: Run RED→GREEN regression and commit**

```bash
.venv/bin/python -m pytest apps/backend/tests/test_attachment_context_citations.py apps/backend/tests/test_context_snapshot_builder.py apps/backend/tests/test_message_analysis_handler.py -q
npm run typecheck
git add apps/backend apps/web
git commit -m "feat: cite attachment text in message analysis"
```

---

### Task 4: Implement MatterUpdateProposal with Optimistic Approval

**Files:**
- Create: `apps/backend/migrations/versions/20260803_0009_add_matter_update_proposals.py`
- Create: `apps/backend/src/legal_workbench/application/matter_updates.py`
- Create: `apps/backend/src/legal_workbench/api/routes/matter_update_proposals.py`
- Create: `apps/backend/src/legal_workbench/api/schemas/matter_updates.py`
- Create: `apps/backend/tests/test_matter_update_proposals.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/domain/enums.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Modify: `apps/backend/src/legal_workbench/application/handlers.py`
- Modify: `apps/backend/src/legal_workbench/application/results.py`
- Modify: `apps/backend/src/legal_workbench/api/routes/candidates.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/candidates.py`
- Modify: `apps/backend/src/legal_workbench/api/router.py`
- Modify: `apps/backend/tests/test_candidate_matter_work_item_slice.py`

**Interfaces:**
- Produces: `MatterUpdateProposal`, `ProposalFieldDecision`, `CreateMatterUpdateProposalHandler`, and `ReviewMatterUpdateProposalHandler`.
- Extends: Candidate `update_existing` response with `proposal_id`.
- Consumes: `LegalMatterRepository.get_for_update`, `WorkItemRepository.add_many`, audit, outbox, and idempotency repositories.

- [x] **Step 1: Write failing proposal approval tests**

```python
async def test_approval_rejects_stale_matter_version(handler):
    with pytest.raises(EntityVersionConflictError):
        await handler.execute(review_command(matter_version=proposal.base_matter_version + 1))

async def test_partial_approval_applies_only_selected_fields(handler):
    result = await handler.execute(review_command(approved_fields=["title", "newWorkItems"]))
    assert result.status == MatterUpdateProposalStatus.PARTIALLY_APPROVED
    assert result.matter.title == "法务最终标题"
    assert result.matter.owner_id == original_owner
```

- [x] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_matter_update_proposals.py -q`

- [x] **Step 3: Add migration and domain invariants**

Create `matter_update_proposals` with status check, candidate/matter foreign keys, `base_matter_version`, JSON proposed/final changes, reviewer metadata, and optimistic `version`. Add domain methods `approve`, `partially_approve`, `reject`, and `supersede`.

- [x] **Step 4: Create proposals from Candidate update action**

Map current Matter values, message-extracted values, and AI-suggested values into a fixed field schema. Candidate becomes `linked` only after the pending Proposal and Candidate-Matter link commit together.

- [x] **Step 5: Apply human decisions transactionally**

Lock Proposal and Matter, compare both expected versions, apply approved scalar fields through Matter domain methods, create approved WorkItems, append audit, outbox, and idempotency rows, then commit once.

- [x] **Step 6: Add API contracts**

```http
POST /api/v1/inbox/candidates/:candidateId/matter-update-proposals
GET  /api/v1/matter-update-proposals/:proposalId
POST /api/v1/matter-update-proposals/:proposalId/review
```

`review` accepts proposal version, matter version, per-field decisions, final values, and optional rejection reason.

- [x] **Step 7: Run RED→GREEN regression and commit**

```bash
.venv/bin/python -m pytest apps/backend/tests/test_matter_update_proposals.py apps/backend/tests/test_candidate_matter_work_item_slice.py -q
.venv/bin/python -m ruff check apps/backend/src apps/backend/tests
.venv/bin/python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
git add apps/backend
git commit -m "feat: complete candidate matter update workflow"
```

---

### Task 5: Complete the WorkItem Domain Lifecycle

**Files:**
- Create: `apps/backend/migrations/versions/20260803_0010_expand_work_item_lifecycle.py`
- Create: `apps/backend/src/legal_workbench/application/work_item_lifecycle.py`
- Create: `apps/backend/tests/test_work_item_lifecycle.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/domain/enums.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/application/commands.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/api/routes/work_items.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/workflow.py`
- Modify: `apps/backend/src/legal_workbench/application/queries.py`

**Interfaces:**
- Produces: `WorkItemActionCommand`, `WorkItemActionResult`, `WorkItem.transition(action, context, expected_version)`, and `WorkItemLifecycleHandler`.
- Reuses: existing canonical request hashing, idempotency replay validation, audit-event construction, and outbox-event construction helpers; if an existing helper does not cover WorkItem actions, add the narrowly scoped typed helper beside the handler and unit-test it.
- Produces: dependency `resolve/waive` repository operations.
- Consumes: existing Deadline and Dependency repositories.

- [ ] **Step 1: Write a transition-table test before production code**

```python
@pytest.mark.parametrize(
    ("initial", "action", "expected"),
    [
        (WorkItemStatus.TODO, "start", WorkItemStatus.IN_PROGRESS),
        (WorkItemStatus.IN_PROGRESS, "pause", WorkItemStatus.PAUSED),
        (WorkItemStatus.WAITING, "resume", WorkItemStatus.IN_PROGRESS),
        (WorkItemStatus.DONE, "reopen", WorkItemStatus.TODO),
    ],
)
def test_allowed_transitions(initial, action, expected):
    item = work_item(status=initial)
    item.apply(action=action, actor_id="legal", reason="verified", expected_version=1)
    assert item.status == expected
```

Add separate failing tests for wait without dependency, complete with open dependency, missing pause/block/reopen reasons, version conflicts, owner/deadline/action changes, and dependency resolution.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_work_item_lifecycle.py -q`

- [ ] **Step 3: Add `paused` migration and domain methods**

Update the database check constraint and enum mapping. Put all transition rules in `WorkItem`; clear or set waiting/block fields atomically and increment version exactly once per action.

- [ ] **Step 4: Implement one application handler for audited actions**

```python
class WorkItemLifecycleHandler:
    async def execute(self, command: WorkItemActionCommand) -> WorkItemActionResult:
        payload = {
            "workItemId": str(command.work_item_id),
            "action": command.action.value,
            "expectedVersion": command.expected_version,
            "reason": command.reason,
        }
        digest = request_hash(payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation="work_item_action", key=command.idempotency_key
            )
            replay = require_matching_replay(
                await uow.idempotency.get(
                    operation="work_item_action", key=command.idempotency_key
                ),
                expected_hash=digest,
                idempotency_key=command.idempotency_key,
            )
            if replay is not None:
                return WorkItemActionResult.from_replay(replay.response_payload)
            item = await uow.work_items.get_for_update(command.work_item_id)
            if item is None:
                raise EntityNotFoundError("Work item was not found.")
            dependencies = list(
                await uow.dependencies.list_by_work_item(command.work_item_id)
            )
            item.apply(
                action=command.action,
                actor_id=command.actor_id,
                reason=command.reason,
                expected_version=command.expected_version,
                open_dependencies=[
                    value for value in dependencies
                    if value.status == DependencyStatus.ACTIVE
                ],
            )
            await uow.work_items.save(item)
            await uow.audit_events.add(build_work_item_audit(item, command))
            await uow.outbox_events.add(build_work_item_outbox(item, command))
            result = WorkItemActionResult.from_item(item)
            await uow.idempotency.add(
                build_work_item_idempotency(command, digest, result)
            )
            await uow.commit()
            return result
```

- [ ] **Step 5: Add action and field-change endpoints**

Implement start, pause, wait, block, resume, complete, cancel, reopen, owner, deadline, next-action, add dependency, and resolve dependency. Require `If-Match` for every update.

- [ ] **Step 6: Run RED→GREEN regression and commit**

```bash
.venv/bin/python -m pytest apps/backend/tests/test_work_item_lifecycle.py apps/backend/tests/test_candidate_matter_work_item_slice.py -q
.venv/bin/python -m ruff check apps/backend/src apps/backend/tests
.venv/bin/python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
git add apps/backend
git commit -m "feat: complete work item lifecycle"
```

---

### Task 6: Replace the Mock Dashboard with a Deterministic PostgreSQL Queue

**Files:**
- Create: `apps/backend/src/legal_workbench/application/dashboard.py`
- Create: `apps/backend/src/legal_workbench/api/routes/dashboard.py`
- Create: `apps/backend/src/legal_workbench/api/schemas/dashboard.py`
- Create: `apps/backend/tests/test_dashboard_queue.py`
- Create: `apps/web/src/pages/DashboardPage.test.tsx`
- Modify: `apps/backend/src/legal_workbench/application/queries.py`
- Modify: `apps/backend/src/legal_workbench/api/router.py`
- Modify: `apps/web/src/pages/DashboardPage.tsx`
- Modify: `apps/web/src/services/api.ts`
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/App.tsx`
- Delete: `apps/web/src/services/adapters.ts`
- Delete: `apps/web/src/data/mock.ts`

**Interfaces:**
- Produces: `DashboardQueueService.get_today(actor_id, now) -> DashboardResponse`.
- Produces: `GET /api/v1/dashboard/today`.
- Consumes: Candidate, AgentRun, WorkItem, Deadline, ReviewPackage, Communication, and system-health queries.

- [ ] **Step 1: Write failing deterministic-order tests**

```python
async def test_dashboard_orders_hard_deadline_before_soft_high_risk(service):
    queue = await service.get_today(actor_id="legal", now=fixed_now)
    assert [item.id for item in queue.today_must_handle][:2] == [hard_deadline_id, soft_id]

async def test_every_dashboard_item_has_a_real_route(service):
    queue = await service.get_today(actor_id="legal", now=fixed_now)
    assert all(item.href.startswith(("/inbox/", "/matters/", "/agent-runs/", "/reviews", "/system")) for item in queue.all_items())
```

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_dashboard_queue.py -q`

- [ ] **Step 3: Implement the projection and sort key**

```python
def queue_sort_key(item: DashboardItem) -> tuple[object, ...]:
    return (
        0 if item.is_hard_deadline else 1,
        0 if item.is_overdue else 1,
        RISK_ORDER[item.legal_risk],
        PRIORITY_ORDER[item.confirmed_priority],
        -item.waiting_seconds,
        item.created_at,
        str(item.id),
    )
```

Return the eight required groups and include the exact reasons used for ranking. Codex priority remains a separate advisory field.

- [ ] **Step 4: Replace the React dashboard**

Use TanStack Query, QueryState, real counts, real object links, loading/empty/error/retry states, and system-degraded banners. Set `/` to redirect to `/dashboard`.

- [ ] **Step 5: Remove runtime Mock sources**

Delete `data/mock.ts` and `services/adapters.ts`. Pages outside this scope show explicit unavailable states if they lack real APIs.

- [ ] **Step 6: Run RED→GREEN regression and commit**

```bash
.venv/bin/python -m pytest apps/backend/tests/test_dashboard_queue.py -q
npm run test --workspace @legal-workbench/web -- --run
npm run typecheck
npm run build
git add apps/backend apps/web
git commit -m "feat: complete daily legal workbench"
```

---

### Task 7: Build Matter Proposal and WorkItem UI Operations

**Files:**
- Create: `apps/web/src/components/MatterUpdateComparison.tsx`
- Create: `apps/web/src/components/MatterUpdateComparison.test.tsx`
- Create: `apps/web/src/components/WorkItemActions.tsx`
- Create: `apps/web/src/components/WorkItemActions.test.tsx`
- Modify: `apps/web/src/pages/MessageDetailPage.tsx`
- Modify: `apps/web/src/pages/TaskDetailPage.tsx`
- Modify: `apps/web/src/services/api.ts`
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/styles/global.css`

**Interfaces:**
- Consumes: MatterUpdateProposal APIs from Task 4.
- Consumes: WorkItem lifecycle APIs from Task 5.
- Produces: four-column comparison and version-conflict recovery UX.

- [ ] **Step 1: Write failing component tests**

```tsx
it('keeps human final values distinct from AI suggestions', async () => {
  render(<MatterUpdateComparison proposal={proposal} />);
  expect(screen.getByText('当前值')).toBeVisible();
  expect(screen.getByText('消息提取值')).toBeVisible();
  expect(screen.getByText('AI建议值')).toBeVisible();
  expect(screen.getByText('法务最终值')).toBeVisible();
});
```

Add tests for partial approval, 409 refresh, every WorkItem action, loading, failure, retry, and permission errors.

- [ ] **Step 2: Verify RED**

Run: `npm run test --workspace @legal-workbench/web -- --run MatterUpdateComparison WorkItemActions`

- [ ] **Step 3: Implement proposal comparison and review mutations**

Use one stable mutation context per payload. Clear it only after success or deterministic 4xx. On 409, preserve the human draft, refetch Matter/Proposal, and show a conflict banner.

- [ ] **Step 4: Implement WorkItem action controls**

Derive available actions from server status, but let the backend remain authoritative. Every mutation sends the current version through `If-Match` and refreshes Matter, WorkItem, and dashboard queries.

- [ ] **Step 5: Run RED→GREEN and commit**

```bash
npm run test --workspace @legal-workbench/web -- --run
npm run typecheck
npm run build
git add apps/web
git commit -m "feat: operate matter updates and work items"
```

---

### Task 8: Add Evaluation Fixtures and Durable Quality Metrics

**Files:**
- Create: `apps/backend/migrations/versions/20260803_0011_add_evaluation_models.py`
- Create: `apps/backend/src/legal_workbench/application/evaluations.py`
- Create: `apps/backend/src/legal_workbench/api/routes/evaluations.py`
- Create: `apps/backend/src/legal_workbench/api/schemas/evaluations.py`
- Create: `apps/backend/tests/fixtures/evaluations/message_judgement_v1.json`
- Create: `apps/backend/tests/test_evaluations.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Modify: `apps/backend/src/legal_workbench/api/router.py`

**Interfaces:**
- Produces: `EvaluationCase`, `EvaluationRun`, `EvaluationResult`, and deterministic metric aggregation.
- Consumes: Fake or explicitly real Agent Runtime and immutable test fixtures.

- [ ] **Step 1: Write failing metric tests**

```python
def test_evaluation_metrics_count_irrelevant_candidate_as_false_positive():
    metrics = aggregate([result(expected_relevant=False, candidate_created=True)])
    assert metrics.irrelevant_candidate_false_positive_rate == 1.0
```

Cover legal relevance, category, deadline, role, facts, inference false positives, missing information, Schema first-pass, latency, failures, and retries.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_evaluations.py -q`

- [ ] **Step 3: Add migration and evaluation service**

Persist immutable case version, runtime type, AgentDefinition version, result payload, per-dimension scores, timing, failure, and retry counts. Fixtures contain invented non-sensitive Chinese messages only.

- [ ] **Step 4: Add explicit evaluation API and CLI path**

`POST /api/v1/evaluations/runs` defaults to Fake Runtime; real Runtime requires an explicit `allowRealRuntime=true` plus server feature gate. Evaluation never changes prompts or AgentDefinition status.

- [ ] **Step 5: Run RED→GREEN and commit**

```bash
.venv/bin/python -m pytest apps/backend/tests/test_evaluations.py -q
.venv/bin/python -m ruff check apps/backend/src apps/backend/tests
.venv/bin/python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
git add apps/backend
git commit -m "feat: evaluate message judgement quality"
```

---

### Task 9: Add Setup Status Without Starting Real Feishu

**Files:**
- Create: `apps/backend/migrations/versions/20260803_0012_add_setup_settings.py`
- Create: `apps/backend/src/legal_workbench/application/setup.py`
- Create: `apps/backend/src/legal_workbench/infrastructure/secrets.py`
- Create: `apps/backend/src/legal_workbench/api/routes/setup.py`
- Create: `apps/backend/src/legal_workbench/api/schemas/setup.py`
- Create: `apps/backend/tests/test_setup_status.py`
- Create: `apps/web/src/pages/SetupPage.tsx`
- Create: `apps/web/src/pages/SetupPage.test.tsx`
- Modify: `apps/backend/src/legal_workbench/config.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Modify: `apps/backend/src/legal_workbench/api/router.py`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/services/api.ts`
- Modify: `apps/web/src/types/api.ts`

**Interfaces:**
- Produces: masked `SetupStatus`, local `SecretProvider`, and setup routes.
- Consumes: Codex health from Task 1, system status, and existing Feishu connection metadata.
- Does not start or validate a real Feishu connection in the current phase.

- [ ] **Step 1: Write failing redaction and status tests**

```python
async def test_setup_status_never_returns_secret(client, configured_secret):
    response = await client.get("/api/v1/setup/status", cookies=session)
    assert response.status_code == 200
    assert configured_secret not in response.text
    assert response.json()["feishu"]["credentials"]["configured"] is True
```

Cover missing credentials, version mismatch, unauthenticated Worker, runtime unreachable, ready, stable error codes, and Correlation ID.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_setup_status.py -q`

- [ ] **Step 3: Implement settings metadata and atomic local secrets**

Secret files use `0700/0600`, atomic replace, masked hints, and no log values. Codex secret access is available only in the Worker wiring.

- [ ] **Step 4: Implement status and deferred Feishu responses**

Expose all required setup routes. Feishu validate/start/stop return `not_executed` with a stable `REAL_FEISHU_PHASE_DEFERRED` code during this user-deferred phase. Codex validate and smoke-test remain real when Worker authentication is available.

- [ ] **Step 5: Implement nine-step Setup UI**

Display every step, exact state, explanation, and Correlation ID. Secret fields are write-only and clear after submission. The page never claims the deferred Feishu steps succeeded.

- [ ] **Step 6: Run RED→GREEN and commit**

```bash
.venv/bin/python -m pytest apps/backend/tests/test_setup_status.py -q
npm run test --workspace @legal-workbench/web -- --run SetupPage
npm run typecheck
git add apps/backend apps/web
git commit -m "feat: add local setup and integration onboarding"
```

---

### Task 10: Harden Mac Operations and System Status

**Files:**
- Create: `scripts/legal_workbench_ops.py`
- Create: `scripts/smoke_test_downstream_loop.py`
- Create: `infra/launchd/com.legal-workbench.supervisor.plist.example`
- Create: `infra/launchd/com.legal-workbench.backup.plist.example`
- Create: `apps/backend/tests/test_mac_operations.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/system_status.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/agents.py`
- Modify: `apps/backend/src/legal_workbench/api/routes/system.py`
- Modify: `apps/backend/src/legal_workbench/config.py`
- Modify: `apps/backend/src/legal_workbench/application/analysis_recovery.py`
- Modify: `apps/web/src/pages/SystemStatusPage.tsx`
- Modify: `compose.yml`
- Modify: `README.md`
- Modify: `docs/design/DEPLOYMENT.md`

**Interfaces:**
- Produces: `start`, `stop`, `wake-check`, `backup`, `diagnostics`, and `cleanup` operation commands.
- Extends: system health with disk, backup, latest message/run, pending recovery, and dead-letter metrics.
- Consumes: Attempt recovery, document quota, Compose health, and PostgreSQL.

- [ ] **Step 1: Write failing operation tests**

```python
def test_diagnostics_redacts_credentials(tmp_path):
    archive = build_diagnostics(settings_with_secrets(), output_dir=tmp_path)
    assert "app-secret" not in read_archive_text(archive)
    assert "OPENAI_API_KEY" not in read_archive_text(archive)
```

Cover wake recovery order, backup retention, safe stop ordering, Codex run cleanup, attachment quota, and Redis-loss recovery selection.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_mac_operations.py -q`

- [ ] **Step 3: Implement safe operations CLI**

Use `subprocess.run` with argument arrays, explicit repository path, timeouts, and checked return codes. Backup writes to a configured directory, verifies a non-empty dump, then atomically records latest success metadata. Stop first disables intake, waits for active short transactions, stops Worker/Scheduler, then runs Compose stop.

- [ ] **Step 4: Implement wake recovery and launchd templates**

Wake check verifies Docker, PostgreSQL, Redis, API, Worker, Scheduler, Codex status, disk, and backup before invoking PostgreSQL recovery. It records real Feishu reconcile as skipped while that phase is deferred.

- [ ] **Step 5: Extend status API and UI**

Display all required components and timestamps. Unknown values are `unknown`, not healthy. Dangerous actions require confirmation and retain stable idempotency keys.

- [ ] **Step 6: Run RED→GREEN and commit**

```bash
.venv/bin/python -m pytest apps/backend/tests/test_mac_operations.py apps/backend/tests/test_worker_redis_recovery.py apps/backend/tests/test_analysis_recovery.py -q
npm run test --workspace @legal-workbench/web -- --run
npm run typecheck
git add scripts infra apps README.md docs/design/DEPLOYMENT.md compose.yml
git commit -m "chore: harden Mac local operations"
```

---

### Task 11: Migrations, Full Verification, Documentation, Push, and Draft PR

**Files:**
- Modify: `README.md`
- Modify: `QA_REPORT.md`
- Modify: `docs/CODEX_HANDOFF.md`
- Modify: `docs/INTEGRATIONS.md`
- Modify: `docs/design/SYSTEM_DESIGN.md`
- Modify: `docs/design/DATA_MODEL.md`
- Modify: `docs/design/API_CONTRACTS.md`
- Modify: `docs/design/AGENT_PROTOCOL.md`
- Modify: `docs/design/DEPLOYMENT.md`
- Modify: `docs/design/IMPLEMENTATION_PLAN.md`
- Modify: `scripts/smoke_test_codex_triage.py`

**Interfaces:**
- Consumes: every prior task.
- Produces: verified migration head, downstream smoke report, exact QA evidence, pushed branch, and Draft PR.

- [ ] **Step 1: Update authoritative documentation from implemented behavior**

Record exact models, APIs, health states, version source, fencing rules, extraction support, citations, proposal approval, WorkItem transitions, dashboard sorting, recovery, and deferred real Feishu status. Remove statements contradicted by code.

- [ ] **Step 2: Run static and unit verification**

```bash
git diff --check
.venv/bin/python -m compileall apps/backend/src
.venv/bin/python -m ruff check apps/backend/src apps/backend/tests
.venv/bin/python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
.venv/bin/python -m pytest apps/backend/tests --disable-warnings
npm run typecheck
npm run test --workspace @legal-workbench/web -- --run
npm run build
docker compose config --quiet
```

- [ ] **Step 3: Run PostgreSQL migration round trip**

On a dedicated test database:

```bash
.venv/bin/alembic -c apps/backend/alembic.ini upgrade head
.venv/bin/alembic -c apps/backend/alembic.ini downgrade 20260801_0006
.venv/bin/alembic -c apps/backend/alembic.ini upgrade head
.venv/bin/alembic -c apps/backend/alembic.ini current
```

Expected final head: `20260803_0012`.

- [ ] **Step 4: Run downstream smoke and recovery exercises**

Run the non-sensitive persisted-message fixture through attachment extraction, Fake/real-if-ready Codex, Candidate, Proposal/Matter, WorkItem, dashboard, Redis flush recovery, expired Attempt, wake check, backup, and diagnostics. Report real Codex separately. Report real Feishu and official long connection as `not_executed`.

- [ ] **Step 5: Perform self-review**

Inspect the full branch diff for security, transaction boundaries, migration downgrade, Actor trust, idempotency, stale Attempt protection, Mock remnants, log secrets, and documentation accuracy. Fix every actionable issue and rerun affected tests.

- [ ] **Step 6: Commit final documentation and QA evidence**

```bash
git add README.md QA_REPORT.md docs scripts
git commit -m "docs: verify downstream operational loop"
```

- [ ] **Step 7: Push and open Draft PR**

```bash
git push -u origin agent/real-feishu-codex-operational-loop
gh pr create --draft --base main --head agent/real-feishu-codex-operational-loop --title "Complete real Feishu-to-matter operational loop" --body-file /tmp/legal-workbench-pr-body.md
```

The PR body must distinguish automatic tests, real PostgreSQL, real Codex if executed, deferred real Feishu, manual unread acceptance, known limitations, migrations, rollback, and exact commits.
