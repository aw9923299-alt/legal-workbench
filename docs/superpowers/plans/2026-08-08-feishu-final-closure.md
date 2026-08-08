# Feishu Personal Sync Final Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the production-oriented Feishu Personal Sync loop with one runtime composition root, one automatic-analysis policy gate, capability-scoped authorization, fail-closed refresh recovery, a Mac-host local connector, and credential-backed Feishu/Codex evidence.

**Architecture:** Keep the existing modular monolith and its PostgreSQL, UnitOfWork, Outbox, LocalSecretProvider, lease/fencing, ContextSnapshot and human-review boundaries. FastAPI and Celery obtain identical personal-sync services from one infrastructure composition root; every automatic attachment terminal state delegates to one application gate that re-reads the persisted message disposition before enqueueing analysis.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, PostgreSQL 18, Alembic, Celery/Redis, HTTPX, React 18, TypeScript, Vite, Ant Design, pytest, Vitest.

## Global Constraints

- Codex remains the only AI runtime; Fake runtime cannot count as real acceptance.
- PostgreSQL remains the only business fact store; Redis is queue and coordination only.
- Feishu token bodies remain only in `LocalSecretProvider`, never PostgreSQL, Redis, logs, audit payloads, frontend state or Codex inputs.
- No external Feishu HTTP or Codex execution may hold a database transaction open.
- Official source precedence is `app_event > user_api > local_client`; a tenant/message identity maps to one business message.
- Local Feishu access is Mac-host-only, read-only, schema-allowlisted, credential-excluding and never decrypts opaque data.
- Candidate creation stops at `pending_confirmation`; no Matter, WorkItem or outbound communication is automatically created.

---

### Task 1: AutomaticAnalysisGate

**Files:**
- Create: `apps/backend/src/legal_workbench/application/automatic_analysis_gate.py`
- Modify: `apps/backend/src/legal_workbench/application/document_extraction.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_operations.py`
- Modify: `apps/backend/tests/test_attachment_download_pipeline.py`
- Create: `apps/backend/tests/test_automatic_analysis_gate.py`

**Interfaces:**
- Produces: `AutomaticAnalysisGate.request_if_allowed(message_id: UUID, *, actor_id: str, actor_source: str, correlation_id: str, force_new_run: bool = False) -> AutomaticAnalysisDecision`.
- Consumes: existing Feishu message and Outbox repositories through `UnitOfWorkFactory`.

- [ ] Add failing tests where terminal downloaded, metadata-only, body-unavailable, extraction-failed and local-materialized attachments for `store_only` messages create no analysis Outbox, while `analyze` creates exactly one.
- [ ] Run the focused tests and confirm failure because attachment services enqueue directly.
- [ ] Implement the gate so it loads the PostgreSQL message, requires `analysis_disposition == "analyze"`, deduplicates pending analysis Outbox, and returns a stable decision reason.
- [ ] Replace every automatic attachment enqueue with the gate; keep the explicit manual analysis API outside the gate.
- [ ] Run gate, extraction, attachment and message-analysis tests to green.

### Task 2: PersonalSyncRuntimeFactory parity

**Files:**
- Create: `apps/backend/src/legal_workbench/infrastructure/feishu_personal_runtime.py`
- Modify: `apps/backend/src/legal_workbench/api/routes/feishu_user.py`
- Modify: `apps/backend/src/legal_workbench/workers/tasks.py`
- Modify: `apps/backend/tests/test_feishu_personal_sync.py`
- Create: `apps/backend/tests/test_feishu_personal_runtime.py`

**Interfaces:**
- Produces: `PersonalSyncRuntimeFactory.open()`, `PersonalSyncRuntime.sync_scope(scope_id)`, and `PersonalSyncRuntime.sync_all_eligible_scopes()`.
- Runtime owns one HTTPX lifecycle and assembles OAuth, token, user client, policy, ingestion, thread, document, attachment, lease/checkpoint and folder synchronization dependencies.

- [ ] Add a failing parity test asserting manual and scheduled entrypoints call the same runtime methods and the runtime behavior includes attachment metadata fallback, document links and thread replies.
- [ ] Run the parity test and confirm the existing API/worker duplicate assembly fails it.
- [ ] Implement the infrastructure composition root and a small runtime facade over the existing application services.
- [ ] Replace FastAPI and Celery assembly with the shared factory; remove duplicated constructors.
- [ ] Run personal-sync, route and worker tests to green.

### Task 3: Capability-scoped authorization and UI

**Files:**
- Create: `apps/backend/src/legal_workbench/application/feishu_capabilities.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_user_auth.py`
- Modify: `apps/backend/src/legal_workbench/api/routes/feishu_user.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/feishu_user.py`
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/pages/FeishuScopesPage.tsx`
- Modify: `apps/backend/tests/test_feishu_user_oauth.py`
- Modify: `apps/web/src/pages/FeishuScopesPage.test.tsx`

**Interfaces:**
- Produces: `FeishuCapability`, `CapabilityRequirement(all_of, any_of)`, `CapabilityProjection`, and `project_capabilities(granted_scopes)`.
- API authorization response includes capability name, status, granted and missing scope names without secret references.

- [ ] Add failing table tests proving missing document/drive scopes do not disable messages, chat read scopes are alternatives, missing message scopes disable only messages, and missing core identity makes authorization unusable.
- [ ] Add a failing UI test for independent Messages, Chat discovery, Documents, Drive and Attachments rows.
- [ ] Implement deterministic capability projection and make global authorization status depend only on token/core identity health.
- [ ] Gate each API operation on its own capability and render per-capability status in the existing Ant Design page.
- [ ] Run backend capability/OAuth and frontend page tests to green.

### Task 4: Fenced refresh phases and fault recovery

**Files:**
- Modify: `apps/backend/src/legal_workbench/domain/enums.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_user_auth.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Create: `apps/backend/migrations/versions/20260808_0017_feishu_refresh_phases.py`
- Modify: `apps/backend/tests/test_feishu_user_oauth.py`

**Interfaces:**
- Adds persisted `rotation_phase`, `rotation_request_started_at`, `rotation_fence`, `rotation_result_written_at`, and `rotation_reauth_reason` metadata.
- Refresh phases are `idle`, `claimed`, `request_started`, and `result_durable`.

- [ ] Add failing fault-injection tests for before/after request-started, after HTTP success before bundle, after bundle fsync, before/after activation commit, cleanup failure and stale-owner activation.
- [ ] Run tests and confirm missing phase/fence behavior.
- [ ] Implement short claim and request-started transactions, external refresh, durable generation bundle, fenced CAS activation and best-effort orphan cleanup.
- [ ] On any expired/failed `request_started` state without a durable bundle, persist `reauth_required` and never invoke refresh with the old generation again.
- [ ] Run refresh unit and PostgreSQL concurrency tests to green.

### Task 5: Mac-host LocalFeishuConnector ingestion

**Files:**
- Modify: `apps/backend/src/legal_workbench/integrations/feishu_local_connector.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_scopes.py`
- Modify: `apps/backend/tests/test_feishu_local_connector.py`
- Modify: `Makefile`
- Create: `infra/launchd/com.legal-workbench.local-feishu.plist.example`
- Modify: `docs/design/DEPLOYMENT.md`

**Interfaces:**
- `python -m legal_workbench.integrations.feishu_local_connector --sync --tenant-key <key> --output <path>` runs on the Mac host.
- Produces a sanitized status including `supported_but_no_readable_local_records` when no allowlisted records exist.

- [ ] Add failing executable tests for read-only boundaries, unknown/opaque schema refusal, credential-directory exclusion, P2P unapproved/disabled defaults, unified ingestion and official-over-local deduplication.
- [ ] Implement the async host sync runner using `LocalMessageIngestionAdapter`, `MessageAnalysisPolicy`, existing scope service and UoW; never mount Mac Library paths into Compose.
- [ ] Add Make and optional launchd entry plus short deployment instructions.
- [ ] Run local connector and source-priority tests and execute the real host command to refresh a sanitized artifact.

### Task 6: Migration, PostgreSQL and Redis reliability

**Files:**
- Modify/create focused tests under `apps/backend/tests/` for SQLAlchemy refresh metadata, Outbox analysis gate, sync fencing and source priority.

**Interfaces:**
- Migration upgrades and downgrades without token-body columns or data loss.

- [ ] Run a fresh isolated PostgreSQL database to `head`.
- [ ] Run `head -> 20260808_0016 -> head` and inspect the schema.
- [ ] Run PostgreSQL-marked sync, refresh and ingestion tests.
- [ ] Run Redis/Celery Outbox and scheduled-sync coordination tests.
- [ ] Scan PostgreSQL models/migrations and runtime artifacts for token bodies.

### Task 7: Workbench OAuth, refresh and real Feishu acceptance

**Files:**
- Modify: `artifacts/feishu-personal-sync/capability-validation.json`
- Modify: relevant setup/handoff documentation only after actual attempts.

**Interfaces:**
- Uses Workbench-created PKCE authorization and LocalSecretProvider generations; never imports lark-cli tokens.

- [ ] Configure App ID, LocalSecretProvider App Secret and registered localhost redirect URI.
- [ ] Complete browser authorization using the current logged-in Mac Feishu session and verify callback/UserAuthorization provenance.
- [ ] Force one refresh, verify generation increments, and read messages again with the rotated token.
- [ ] Execute manual and Celery scheduled sync against a non-sensitive scope and record sanitized results.
- [ ] Scan PostgreSQL, Redis, logs, frontend artifacts and Codex run directories for the test token fingerprints without printing token bodies.

### Task 8: Real Codex AgentRun/Candidate and negative policy E2E

**Files:**
- Modify: `artifacts/feishu-personal-sync/e2e-validation.json`
- Modify: handoff/status documentation only with actual evidence.

**Interfaces:**
- Uses `CodexCliRuntime`, persisted ContextSnapshot, AgentRun and Candidate APIs.

- [ ] Verify the exact Workbench runtime command/version/authentication and set `LEGAL_WORKBENCH_ENABLE_REAL_CODEX=true` in the local runtime configuration.
- [ ] Sync one non-sensitive `analyze` message using the Workbench OAuth authorization, publish Outbox, execute real Codex and query the resulting pending Candidate.
- [ ] Verify no Matter, WorkItem or Communication was created.
- [ ] Process a non-sensitive `store_only` group attachment to a terminal state and assert no analysis Outbox, snapshot, run or Candidate.
- [ ] Record only sanitized identifiers/counts and explicit partial/failed/unsupported blockers.

### Task 9: Full verification and Git delivery

**Files:**
- All task-related modified files only.

**Interfaces:**
- Produces branch `codex/feishu-final-closure` and a Draft PR to `main`.

- [ ] Run Ruff, mypy, the full backend pytest suite, frontend typecheck, Vitest and production build.
- [ ] Run `git diff --check`, inspect status/diff for unrelated files and scan tracked changes for secrets or sensitive message bodies.
- [ ] Commit functional changes on `codex/feishu-final-closure`.
- [ ] Push the branch and create a Draft PR targeting `main`; do not merge.
- [ ] Report only fresh verified results and explicit external blockers.
