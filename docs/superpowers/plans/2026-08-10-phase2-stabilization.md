# Phase 2 Stabilization Implementation Plan

> Execute in order with regression tests first. Do not add a Plan generation/epoch model, new Agent, provider, service, automatic Communication, or real-corpus access.

**Goal:** Prove that the current Legal Agent system remains correct, recoverable, source-grounded, reproducible, and human-controlled across retries, stale workers, reruns, recovery, and production builds.

**Architecture:** Extend the existing `AgentRunAttempt`, `AgentExecutionPlan`, `AgentPlanStep`, PostgreSQL repositories, `LegalAgentOrchestrator`, and deterministic knowledge pipeline. Use existing row locks, status/version fields, current/latest Run IDs, and Attempt lease CAS as fences. Preserve append-only historical Runs, artifacts, reviews, and audit data.

---

## Task 1: Recovery lease-expiry CAS

**Files:**
- Modify: `apps/backend/tests/test_agent_attempt_fencing.py`
- Modify: `apps/backend/tests/test_postgres_agent_attempt_fencing.py`
- Modify: `apps/backend/tests/test_analysis_recovery.py`
- Modify: `apps/backend/src/legal_workbench/application/ports/agents.py`
- Modify: `apps/backend/src/legal_workbench/application/agent_attempts.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/application/analysis_recovery.py`

1. Add failing tests proving an unexpired or already-terminal Attempt cannot be expired and recovery leaves Run/Step/Plan unchanged when expiry CAS fails.
2. Add the expiry timestamp to the repository contract and require `lease_expires_at <= expired_at` in the SQL update.
3. Make recovery stop processing a candidate when expiry CAS returns false.
4. Run the focused attempt/recovery unit and PostgreSQL tests.

## Task 2: Step/Plan current-run fencing and concurrent rerun

**Files:**
- Modify: `apps/backend/tests/test_legal_agent_orchestrator.py`
- Modify: `apps/backend/tests/test_legal_agent_orchestrator_concurrency.py`
- Modify: `apps/backend/tests/test_analysis_recovery.py`
- Modify: `apps/backend/src/legal_workbench/application/legal_agent_orchestrator.py`
- Modify: `apps/backend/src/legal_workbench/application/analysis_recovery.py`

1. Add failing tests for overlapping rerun rejection, stale Specialist success/failure, stale synthesis completion, and recovery terminal handling of a superseded Step Run.
2. Reserve reruns under a Plan row lock and reject rerun while the Plan is active.
3. Require Specialist Step current Run equality before Step mutation.
4. Require synthesis Plan current Run equality before Plan mutation and artifact/review persistence.
5. Apply the same current-Run guard during terminal recovery.
6. Run focused orchestrator, concurrency, and recovery tests.

## Task 3: DAG lineage and stale source isolation

**Files:**
- Modify: `apps/backend/tests/test_legal_agent_orchestrator.py`
- Modify: `apps/backend/tests/test_legal_agent_dependencies.py`
- Modify: `apps/backend/src/legal_workbench/application/legal_agent_orchestrator.py`
- Modify if needed: `apps/backend/src/legal_workbench/application/legal_dependencies.py`

1. Extend the upstream-rerun regression so a stale downstream source is absent from synthesis authorization and citations.
2. Build synthesis authorization only from valid current Step results plus the synthesis ContextSnapshot.
3. Keep invalidated Step failure placeholders without adding their Run sources.
4. Assert rerun dependency IDs equal the dependencies' latest valid Run IDs.
5. Run focused DAG/orchestrator tests.

## Task 4: Stable analysis date and historical semantics

**Files:**
- Add: `apps/backend/migrations/versions/20260810_0020_stabilize_legal_agent_execution.py`
- Modify: `apps/backend/src/legal_workbench/domain/agents.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/application/legal_agent_orchestrator.py`
- Modify: `apps/backend/tests/test_legal_agent_orchestrator.py`
- Modify: `apps/backend/tests/test_postgres_legal_agent_persistence.py`
- Modify: `apps/backend/tests/test_postgres_migrations.py` or the existing migration round-trip test

1. Add failing tests with an injected clock spanning midnight; retries, recovery, reruns, retrieval, and synthesis must retain one `analysis_effective_date`.
2. Add non-null `analysis_effective_date` to Plan with deterministic created-date backfill and reversible downgrade.
3. Persist the date once at Plan creation and reconstruct triggers from the Plan thereafter.
4. Keep `historical_as_of` separate and use it only for explicit historical applicability.
5. Replace phase-local `date.today()` calls.
6. Run domain, repository, orchestrator, migration, and historical authority tests.

## Task 5: Canonical Specialist citations

**Files:**
- Modify: `apps/backend/tests/test_legal_agent_contracts.py`
- Modify: `apps/backend/tests/test_professional_codex_runtime.py`
- Modify: `apps/backend/src/legal_workbench/agents/legal_contracts.py`
- Modify: `apps/backend/src/legal_workbench/agents/contracts.py`
- Modify as needed: `apps/backend/src/legal_workbench/application/legal_agent_orchestrator.py`

1. Add failing tests showing model-supplied title/type/locator/hash are replaced by authorized server metadata and missing canonical metadata fails closed.
2. Change Specialist validation to return a product with canonical citations.
3. Rebuild citation fields from authorized source metadata and derive the internal-precedent marker server-side.
4. Retain authority status/role/effective-date validation independently of citation prose.
5. Run focused Specialist contract/runtime tests.

## Task 6: Full synthetic Fake Runtime E2E

**Files:**
- Add: `apps/backend/tests/test_synthetic_fake_legal_agent_e2e.py`
- Modify if needed: shared test fixtures only

1. Create only non-sensitive synthetic Message, legal-rule, and contract fixtures.
2. Use actual PostgreSQL handlers for Message analysis, Candidate confirmation, Matter/WorkItem creation, Knowledge retrieval, orchestration, DraftArtifact, and ReviewPackage.
3. Name and mark the runtime/test as Fake Runtime synthetic evidence.
4. Assert current Run lineage, grounded citations, pending Human Review, and unchanged Communication count.
5. Keep `test_real_codex_legal_agent_e2e.py` separately gated.

## Task 7: Build and CI consistency

**Files:**
- Modify: `infra/docker/web.Dockerfile`
- Modify: `.github/workflows/ci.yml`
- Modify as justified: `.python-version`, `infra/docker/backend.Dockerfile`
- Modify: `README.md`
- Modify: `docs/design/DEPLOYMENT.md`

1. Add a static regression/check proving the Web image Node major equals `.node-version`.
2. Align the Web build image to Node 24.15.0.
3. Keep one clear Python 3.12 policy; pin patch only if the current tools can consume the same source without duplication.
4. Add CI production builds for backend and web Dockerfiles while retaining Compose validation.
5. Verify built image runtime versions and production startup targets.

## Task 8: Documentation and full acceptance

**Files:**
- Modify: `README.md`
- Modify: `docs/design/AGENT_PROTOCOL.md`
- Modify: `docs/design/DATA_MODEL.md`
- Modify: `docs/design/KNOWLEDGE_RETRIEVAL.md`
- Modify: `docs/design/DEPLOYMENT.md`
- Modify: `docs/CODEX_HANDOFF.md`

1. Update implementation status, Plan/Step fencing, analysis-date semantics, canonical citations, E2E evidence boundaries, and Docker/CI source-of-truth policy.
2. Run lint/typecheck, backend and frontend tests, PostgreSQL/Redis integration, Alembic fresh upgrade and downgrade/upgrade, production Docker builds, synthetic Fake E2E, and `git diff --check`.
3. Run Real Codex E2E only if all explicit credentials/runtime gates are available; otherwise report it as unrun without treating Fake Runtime as equivalent.
4. Confirm no Communication bypass, no Redis business facts, no sensitive fixture/material, and no unrelated refactor.
5. Review the final diff and issue `READY TO MERGE`, `READY AFTER FIXES`, or `NOT READY`. Do not merge.
