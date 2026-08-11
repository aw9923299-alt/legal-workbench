# Matter Continuity v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate and consume deterministic related-Matter proposals in the canonical Feishu message-analysis path without allowing automatic Matter mutation.

**Architecture:** Reuse existing FeishuMessage, CandidateMatterLink, Communication, ContextSnapshot and MessageCandidate persistence. A focused application resolver reads only human-confirmed links and successfully sent Communications, emits deterministic proposals, stores Matter IDs in the immutable ContextSnapshot, and lets the canonical message-analysis handler persist those proposals onto Candidate. The frontend surfaces/preselects them while retaining explicit human confirmation.

**Tech Stack:** Python 3.12, FastAPI application services, SQLAlchemy/PostgreSQL, Pydantic domain/API contracts, pytest, React/TypeScript, TanStack Query, Ant Design, Vitest.

## Global Constraints

- No automatic CandidateMatterLink creation or Matter mutation.
- No new Agent, queue, provider, vector store or parallel runtime.
- Only strong deterministic signals: reply-to-sent-Communication and same thread/root human-confirmed link.
- Continuity resolution must be replayable from PostgreSQL facts and included in ContextSnapshot hashing.
- Existing human review, optimistic locking, idempotency and audit boundaries remain authoritative.
- Runtime claims must distinguish IMPLEMENTED / WIRED / TESTED / RUNTIME_PROVEN / PRODUCTION_PROVEN.

---

### Task 1: Add failing continuity resolver and repository tests

**Files:**
- Create: `apps/backend/tests/test_matter_continuity.py`
- Modify: `apps/backend/tests/test_context_snapshot_builder.py`
- Modify: `apps/backend/tests/test_message_analysis_handler.py`
- Test: `apps/backend/tests/test_postgres_message_triage.py`

**Interfaces:**
- Produces expected `MatterContinuityProposal` behavior for reply-to-Communication and same-thread confirmed links.
- Proves snapshot `relevant_matter_ids` and Candidate `related_matter_proposals` are currently missing.

- [ ] Write unit tests that expect duplicate signals for one Matter to merge and weak same-chat-only evidence to produce no proposal.
- [ ] Write ContextSnapshotBuilder test expecting deterministic continuity Matter IDs in the immutable snapshot.
- [ ] Write canonical message-analysis test expecting candidate proposals to survive `_persist_success()`.
- [ ] Write PostgreSQL integration test for the real joins.
- [ ] Commit the failing tests.

### Task 2: Implement deterministic continuity resolver and repository reads

**Files:**
- Create: `apps/backend/src/legal_workbench/application/matter_continuity.py`
- Modify: `apps/backend/src/legal_workbench/application/ports/agents.py`
- Modify: `apps/backend/src/legal_workbench/application/ports/reviews.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`

**Interfaces:**
- Produces `MatterContinuityProposal` dataclass and `MatterContinuityResolver.resolve(message, context_messages)`.
- Candidate repository read returns confirmed Matter link evidence for Feishu message database IDs.
- Communication repository read returns sent Communication evidence by external Feishu message IDs.

- [ ] Add the smallest typed proposal/read-record structures that make the deterministic behavior explicit.
- [ ] Extend current repositories with read-only methods; use existing models and indexes where possible.
- [ ] Rank `reply_to_communication=1.0`, `same_thread_confirmed_link=0.95`, merge by Matter and sort stably.
- [ ] Exclude unsent/failed Communications and non-human-confirmed candidate links.
- [ ] Run targeted backend tests and commit.

### Task 3: Wire continuity into ContextSnapshot and canonical analysis persistence

**Files:**
- Modify: `apps/backend/src/legal_workbench/application/context_snapshots.py`
- Modify: `apps/backend/src/legal_workbench/application/message_analysis.py`

**Interfaces:**
- ContextSnapshot contains `relevant_matter_ids` and `content.matterContinuityProposals`.
- MessageCandidate persists the same proposal payload on create and pending-analysis replacement.
- Audit event `matter_continuity_candidates_materialized` records only diagnostic evidence.

- [ ] Resolve continuity inside `ContextSnapshotBuilder.build_for_feishu_message()` after context-message selection and before hash calculation.
- [ ] Include continuity payload in the snapshot content/hash so retries cannot silently change proposal evidence.
- [ ] Persist candidate proposals from the immutable snapshot rather than rerunning the resolver after Codex execution.
- [ ] Add audit event with run/snapshot/Matter IDs when proposals exist.
- [ ] Run targeted unit/integration tests and commit.

### Task 4: Surface and consume proposals in Message Detail

**Files:**
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/pages/MessageDetailPage.tsx`
- Modify: `apps/web/src/pages/MessageDetailPage.test.tsx`

**Interfaces:**
- Adds typed `RelatedMatterProposal`.
- Message detail shows the ranked recommendations and deterministic signal labels.
- Opening link/update modal preselects the top proposal while still allowing another Matter to be chosen.

- [ ] Add a strict frontend proposal type matching the backend JSON contract.
- [ ] Render a compact “可能关联事项” block only when proposals exist.
- [ ] Replace direct `setLinkAction` calls with a helper that preselects top proposal and lazily loads all Matters only when the modal is opened.
- [ ] Add tests for rendering and preselection; do not test implementation details.
- [ ] Run frontend unit tests/typecheck and commit.

### Task 5: Full verification and architecture review

**Files:**
- Modify only if verification uncovers a real defect.

**Interfaces:**
- CI and runtime evidence determine final capability level.

- [ ] Run/trigger backend Ruff, mypy, pytest with PostgreSQL/Redis integration, latest Alembic round-trip, frontend tests/typecheck/build, Compose config and image smoke gates.
- [ ] If connector environment cannot run local commands, open a Draft PR and use GitHub Actions as the executable verification environment.
- [ ] Inspect failed jobs/logs, fix real defects and rerun until green or externally blocked.
- [ ] Review final diff for parallel architecture, accidental auto-link behavior, missing audit boundaries and stale docs.
- [ ] Record exact evidence level: IMPLEMENTED / WIRED / TESTED / RUNTIME_PROVEN / PRODUCTION_PROVEN.
