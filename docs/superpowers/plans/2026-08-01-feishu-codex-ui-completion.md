# Feishu, Codex, and Workflow UI Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the local-Mac workflow from persisted Feishu events through observable Codex analysis to human Candidate confirmation.

**Architecture:** Extend the existing FastAPI modular monolith. Both Feishu transports call one application ingestion service; PostgreSQL remains the source of truth and Outbox/Celery remain a rebuildable delivery layer. Codex continues to run outside database transactions, and the React client consumes authenticated APIs plus SSE with polling fallback.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Celery, Redis, PostgreSQL 18, lark-oapi, React 18, TypeScript, React Router, TanStack Query, Ant Design, Vitest.

## Global Constraints

- Codex is the only AI runtime; do not add another model or embedding service.
- PostgreSQL is the sole business fact store; Redis loss must be recoverable.
- Codex worker concurrency is 1, prefetch is 1, late acknowledgement and worker-loss rejection stay enabled.
- Event receipt performs validation, normalization, idempotent persistence, and Outbox writes only.
- No Codex process waits inside a database transaction.
- No Candidate creates or changes a formal Matter without a human action.
- All ports bind to `127.0.0.1` by default.
- Do not add knowledge, specialist legal agents, microservices, Kubernetes, or a second queue.

---

### Task 1: Persist Feishu operational state and immutable message history

**Files:**
- Create: `apps/backend/migrations/versions/20260801_0005_complete_feishu_ingestion.py`
- Modify: `apps/backend/src/legal_workbench/domain/enums.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/__init__.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Test: `apps/backend/tests/test_feishu_ingestion_completion.py`

**Interfaces:**
- Produces: `IntegrationConnection`, `FeishuMessageVersion`, and `FeishuAttachment` records plus repository methods for status, history, filters, and recovery scans.

- [ ] Write tests proving tenant-scoped event/message uniqueness, edit/recall append-only history, attachment metadata, and persisted connection transitions.
- [ ] Run the focused test and confirm failures are caused by missing models and methods.
- [ ] Add enum/domain/model/repository behavior and reversible migration `20260801_0005`.
- [ ] Run the focused tests, Ruff, mypy, migration upgrade/downgrade/upgrade, and `git diff --check`.

### Task 2: Normalize supported Feishu events through one application service

**Files:**
- Create: `apps/backend/src/legal_workbench/integrations/feishu_events.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_handlers.py`
- Modify: `apps/backend/src/legal_workbench/api/routes/integrations.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/feishu.py`
- Test: `apps/backend/tests/test_feishu_ingestion_completion.py`

**Interfaces:**
- Consumes: repositories from Task 1.
- Produces: `normalize_feishu_event(payload) -> NormalizedFeishuEvent` and the shared `IngestFeishuEventHandler` used by webhook, long connection, and reconcile paths.

- [ ] Add failing table-driven tests for text, post, reply/thread, file, image, unsupported, edit, recall, and duplicate events.
- [ ] Run the focused tests and verify each missing behavior fails for the intended reason.
- [ ] Implement canonical plain text, structured content, attachment extraction, unsupported reasons, append-only revisions, and Outbox policy.
- [ ] Run focused and existing ingestion tests and static checks.

### Task 3: Add long-connection lifecycle, controlled attachment download, and reconciliation

**Files:**
- Create: `apps/backend/src/legal_workbench/integrations/feishu_event_sources.py`
- Create: `apps/backend/src/legal_workbench/application/feishu_operations.py`
- Modify: `apps/backend/src/legal_workbench/integrations/feishu_client.py`
- Modify: `apps/backend/src/legal_workbench/integrations/feishu_connector.py`
- Modify: `apps/backend/src/legal_workbench/config.py`
- Modify: `.env.example`
- Modify: `compose.yml`
- Test: `apps/backend/tests/test_feishu_event_sources.py`

**Interfaces:**
- Produces: `FeishuEventSource.start/stop/health`, official-SDK `LongConnectionFeishuEventSource`, webhook status source, `reconcile_feishu_window`, and controlled attachment download under the configured attachment root.

- [ ] Add failing lifecycle tests for fail-closed credentials, 1/2/4/8/16/30 second backoff, reset after recovery, graceful stop, download hash/status, and idempotent reconcile audit.
- [ ] Implement the protocol, SDK adapter, connector lifecycle, status persistence, download boundary, and reconcile/reconnect API actions.
- [ ] Run phase-one tests and all backend checks.
- [ ] Update QA and design/API/deployment documents with simulated versus real verification labels.
- [ ] Commit exactly `feat: complete Feishu local message ingestion`.

### Task 4: Harden Codex preflight, snapshots, output repair, and analysis revisions

**Files:**
- Create: `apps/backend/migrations/versions/20260801_0006_harden_codex_analysis.py`
- Create: `apps/backend/src/legal_workbench/agents/health.py`
- Modify: `apps/backend/src/legal_workbench/agents/codex_cli.py`
- Modify: `apps/backend/src/legal_workbench/agents/definitions.py`
- Modify: `apps/backend/src/legal_workbench/application/context_snapshots.py`
- Modify: `apps/backend/src/legal_workbench/application/message_analysis.py`
- Modify: domain/model/repository files from Task 1.
- Test: `apps/backend/tests/test_codex_analysis_completion.py`

**Interfaces:**
- Produces: `CodexHealthProbe.check()`, snapshot builder/selection version metadata, one schema-repair retry using the same snapshot, append-only `CandidateRevision`, and AgentRun status history.

- [ ] Add failing tests for executable/version/auth/run-root statuses, per-item and total truncation metadata, prompt-injection constraints, one repair retry, immutable Candidate revisions, and domain-only status transitions.
- [ ] Implement the health probe, prompt v2, runtime repair attempt, snapshot version inputs, state history, revision persistence, and reversible migration `20260801_0006`.
- [ ] Run focused tests, the existing runtime suite, static checks, and migration round trip.

### Task 5: Recover work from PostgreSQL and provide an honest Codex smoke script

**Files:**
- Create: `apps/backend/src/legal_workbench/application/recovery.py`
- Create: `scripts/smoke_test_codex_triage.py`
- Modify: `apps/backend/src/legal_workbench/workers/tasks.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/celery_app.py`
- Modify: `apps/backend/src/legal_workbench/api/routes/agents.py`
- Test: `apps/backend/tests/test_analysis_recovery.py`

**Interfaces:**
- Produces: database-locked scans for missing jobs and expired leases, retry/cancel/dead-letter actions, scheduled recovery, and a smoke runner that records real or explicitly blocked results without inventing token use.

- [ ] Add failing tests for queued-message rediscovery, stale queued requeue, expired running lease failure/retry, max-attempt dead letter, and Candidate non-duplication.
- [ ] Implement recovery with PostgreSQL advisory/row locks and Celery beat dispatch.
- [ ] Add the eleven specified smoke cases with Fake Runtime default and real-runtime opt-in.
- [ ] Run phase-two tests and update QA/documentation.
- [ ] Commit exactly `feat: harden Codex message analysis runtime`.

### Task 6: Expose operational APIs and SSE

**Files:**
- Create: `apps/backend/src/legal_workbench/api/routes/messages.py`
- Create: `apps/backend/src/legal_workbench/api/routes/system.py`
- Create: `apps/backend/src/legal_workbench/api/routes/events.py`
- Create: `apps/backend/src/legal_workbench/application/system_status.py`
- Modify: agent, candidate, outbox, router, schema, and query files.
- Test: `apps/backend/tests/test_operational_api.py`

**Interfaces:**
- Produces: searchable message list/detail/history, full analysis revisions, run retry/cancel, real system health/metrics/recovery actions, and minimal-ID SSE events.

- [ ] Add failing API tests for authentication, Idempotency-Key, Correlation ID, filters, retry/cancel guards, system state, SSE framing, and redaction.
- [ ] Implement APIs by reusing existing actions and deterministic application services.
- [ ] Run API tests and all backend checks.

### Task 7: Replace workflow mocks with routed, query-backed operational pages

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/src/main.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/services/api.ts`
- Modify: `apps/web/src/types/api.ts`
- Create: `apps/web/src/services/realtime.ts`
- Create: `apps/web/src/components/AsyncState.tsx`
- Create/modify: inbox, message detail, Agent runs, run detail, and system pages.
- Test: `apps/web/src/**/*.test.tsx`

**Interfaces:**
- Produces: React Router routes, TanStack Query resources, SSE reconnect with bounded polling fallback, shared API error/correlation rendering, and idempotent Candidate actions.

- [ ] Add failing Vitest tests for inbox filtering, details fact/inference separation, run state changes, SSE fallback, mutation-key reuse, error display, and Candidate confirmation.
- [ ] Add Router, Query, testing dependencies and test configuration.
- [ ] Implement only `/inbox`, `/inbox/:messageId`, `/candidates/:candidateId`, `/agent-runs`, `/agent-runs/:runId`, `/system`, and existing matter routes.
- [ ] Remove operational mock claims, preserve explicit placeholders outside this round, and add loading/empty/error/unauthorized/unavailable/retry/updated-at states.
- [ ] Run frontend tests, typecheck, and build.
- [ ] Update QA and all required docs.
- [ ] Commit exactly `feat: complete operational workflow UI`.

### Task 8: System verification, fault injection, review, and publication

**Files:**
- Modify only documentation corrections revealed by verification.

- [ ] Run `git diff --check`, compileall, Ruff, mypy, full pytest, frontend tests/typecheck/build, and Compose config/build/up.
- [ ] Run Alembic upgrade/downgrade/upgrade against PostgreSQL 18 and the PostgreSQL/Redis integration suite.
- [ ] Stop/start Redis and worker, terminate a controlled Codex smoke process, restart API, simulate Feishu source disconnect, and record observed recovery.
- [ ] Review the final diff for architecture, security, migration reversibility, logging redaction, and unrelated changes.
- [ ] Push `agent/feishu-codex-ui-completion`, create the requested Draft PR, attach available UI screenshots, and verify GitHub checks.
