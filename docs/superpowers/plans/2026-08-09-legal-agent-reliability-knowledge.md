# Legal Agent Reliability and Knowledge Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add incremental local legal-knowledge ingestion, bounded authority-aware retrieval,
leased/recoverable Legal Agent execution, dependency-correct reruns, and item-level Butler
grounding to the existing modular monolith.

**Architecture:** Extend the current Document/Segment/Knowledge pipeline and the existing
`AgentAttemptService`. PostgreSQL remains authoritative; every Runtime call uses a fenced attempt,
every knowledge selection is deterministic and audited, and every final synthesis item cites an
original authorized source.

**Tech Stack:** Python 3.12, Pydantic 2, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 18, Redis/Celery,
React 18, TypeScript, Ant Design, uv 0.12.3, Node 24.15.0.

## Global Constraints

- Base commit is `origin/main@2d6106e`; branch is
  `codex/legal-agent-reliability-knowledge`.
- Do not read or modify the real `Codex-Obs法务项目` directory in this phase.
- Do not add a production tokenizer, parser, LLM, embedding API, vector service, Agent, service,
  user/SSO/RBAC/tenancy boundary, or UI framework.
- Preserve Human Review, UoW, Outbox, PostgreSQL source of truth, Redis coordination, and existing
  Feishu/Candidate behavior.
- Every new behavior follows RED → GREEN → REFACTOR and every task ends with a focused commit.
- Local source paths never enter Codex input or ordinary logs.

---

### Task 1: Authority, token and provenance domain contracts plus migration 0019

**Files:**

- Modify: `apps/backend/src/legal_workbench/domain/enums.py`
- Modify: `apps/backend/src/legal_workbench/domain/documents.py`
- Modify: `apps/backend/src/legal_workbench/domain/knowledge.py`
- Modify: `apps/backend/src/legal_workbench/domain/agents.py`
- Modify: `apps/backend/src/legal_workbench/domain/reviews.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/__init__.py`
- Create: `apps/backend/migrations/versions/20260809_0019_harden_legal_knowledge.py`
- Test: `apps/backend/tests/test_knowledge_authority_domain.py`
- Test: `apps/backend/tests/test_local_document_domain.py`

**Interfaces:**

- Produces `AuthorityType`, `AuthorityRole`, `AuthorityStatus`, `KnowledgeMetadataStatus`,
  `LocalDocumentSourceStatus`, and `KnowledgeScanStatus` string enums.
- Produces `authority_role_for_type(authority_type) -> AuthorityRole | None` and
  `validate_authority_role(authority_type, authority_role) -> None`.
- Produces `LocalDocumentSource`, `LocalKnowledgeScan`, and `LocalDocumentObservation` domain
  records.
- Adds `AgentPlanStep.latest_valid_run_id`, `AgentRun.dependency_run_ids`, chunk token metadata,
  retrieval budget metrics, and `ReviewPackage.grounding_payload`.

- [ ] **Step 1: Write failing domain tests**

```python
def test_company_policy_cannot_be_formal_legal_basis() -> None:
    with pytest.raises(DomainValidationError):
        validate_authority_role(
            AuthorityType.COMPANY_POLICY,
            AuthorityRole.FORMAL_LEGAL_BASIS,
        )

def test_local_source_rejects_absolute_relative_path() -> None:
    with pytest.raises(DomainValidationError):
        LocalDocumentSource(
            id=uuid4(),
            source_root_key="fixture-root",
            relative_path="/absolute/path",
            display_name="contract.pdf",
            status=LocalDocumentSourceStatus.ACTIVE,
        )
```

Run:

```bash
cd apps/backend
uv run --locked pytest tests/test_knowledge_authority_domain.py tests/test_local_document_domain.py -q
```

Expected: imports fail because the new contracts do not exist.

- [ ] **Step 2: Implement minimal domain contracts and migration**

The type/role table is a literal mapping. `UNKNOWN` maps to `None`; callers cannot override the
mapping. Existing broad `regulation` rows migrate to `unknown/pending_metadata`.

- [ ] **Step 3: Verify migration syntax and domain tests**

```bash
uv run --locked pytest tests/test_knowledge_authority_domain.py tests/test_local_document_domain.py -q
uv run --locked alembic -c alembic.ini heads
```

Expected: tests pass and the only head is `20260809_0019`.

- [ ] **Step 4: Commit**

```bash
git add apps/backend/src/legal_workbench/domain apps/backend/src/legal_workbench/infrastructure/models \
  apps/backend/migrations/versions/20260809_0019_harden_legal_knowledge.py apps/backend/tests
git commit -m "feat(knowledge): model authority and local provenance"
```

### Task 2: Deterministic token estimator, scanner and incremental importer

**Files:**

- Create: `apps/backend/src/legal_workbench/application/token_budget.py`
- Create: `apps/backend/src/legal_workbench/application/knowledge_ingestion.py`
- Create: `apps/backend/src/legal_workbench/integrations/local_knowledge.py`
- Create: `apps/backend/src/legal_workbench/scripts/knowledge_import.py`
- Modify: `apps/backend/src/legal_workbench/application/ports/documents.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Modify: `apps/backend/src/legal_workbench/application/document_extraction.py`
- Modify: `Makefile`
- Test: `apps/backend/tests/test_knowledge_ingestion.py`
- Test: `apps/backend/tests/test_knowledge_import_integration.py`

**Interfaces:**

- Produces `DeterministicTokenEstimator.estimate(text) -> TokenEstimate`.
- Produces `LocalKnowledgeScanner.scan(source: Path) -> LocalScanManifest`.
- Produces `KnowledgeIngestionService.import_source(source, source_root_key, correlation_id)`.
- Produces `make knowledge-import SOURCE="/fixtures/legal-materials"`.

- [ ] **Step 1: Write failing scanner and importer tests**

Tests use `tmp_path` and literal PDF/DOCX/TXT/Markdown fixtures. They assert exclusion of `.git`,
cache/build/temp/backup directories, rejection of absolute relative paths and `.noindex` sources,
read-only source behavior, SHA-256 deduplication, unchanged no-op, changed new observation,
unsupported isolation, parse-failure isolation, and missing-source retirement.

Run:

```bash
cd apps/backend
uv run --locked pytest tests/test_knowledge_ingestion.py tests/test_knowledge_import_integration.py -q
```

Expected: import failures for the missing scanner/service.

- [ ] **Step 2: Implement scanner and repository methods**

The scanner returns metadata only. The service reads a file through the existing isolated
extractor, persists a generic `DocumentVersion`, the existing `DocumentExtraction` and
`DocumentSegment`, then registers `KnowledgeDocument/KnowledgeChunk`. Each file uses an isolated
UoW; the batch record is finalized only after all files are attempted.

- [ ] **Step 3: Implement CLI and Make target**

```make
knowledge-import:
	$(BACKEND_UV) python -m legal_workbench.scripts.knowledge_import --source "$(SOURCE)"
```

The CLI prints only counts, safe codes, source-root key, and scan ID.

- [ ] **Step 4: Run tests and commit**

```bash
uv run --locked pytest tests/test_knowledge_ingestion.py tests/test_knowledge_import_integration.py \
  tests/test_document_extraction.py -q
git add Makefile apps/backend/src/legal_workbench apps/backend/tests
git commit -m "feat(knowledge): import local materials incrementally"
```

### Task 3: Inventory artifact schema and bounded retrieval

**Files:**

- Create: `apps/backend/src/legal_workbench/application/material_inventory.py`
- Create: `apps/backend/src/legal_workbench/scripts/knowledge_inventory.py`
- Modify: `apps/backend/src/legal_workbench/domain/knowledge.py`
- Modify: `apps/backend/src/legal_workbench/application/knowledge.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/knowledge.py`
- Modify: `apps/backend/src/legal_workbench/config.py`
- Modify: `.env.example`
- Modify: `Makefile`
- Test: `apps/backend/tests/test_material_inventory.py`
- Test: `apps/backend/tests/test_knowledge_token_budget.py`
- Test: `apps/backend/tests/test_postgres_knowledge_retrieval.py`

**Interfaces:**

- Produces `MaterialInventoryService.build(source) -> MaterialInventory` without Codex calls.
- Produces budgeted `KnowledgeRetrievalService.search(request, budget)` with a `KnowledgeBudget`
  snapshot.
- Persists candidate/selected/excluded counts and tokens on `KnowledgeRetrievalLog`.

- [ ] **Step 1: Write failing inventory and budget tests**

Use hand-derived text byte counts. Assert exact estimated flag/method, raw versus unique SHA token
totals, A/B per-run difference, stable authority-first selection, text-hash deduplication,
single-chunk exclusion, max chunks, max total tokens, and audit metrics.

- [ ] **Step 2: Implement estimator-backed inventory and budget selection**

Candidate SQL keeps metadata + FTS + trigram scoring. Application code performs stable SHA text
deduplication and the three budgets. It never truncates a retrieved source silently.

- [ ] **Step 3: Run focused and PostgreSQL tests**

```bash
cd apps/backend
uv run --locked pytest tests/test_material_inventory.py tests/test_knowledge_token_budget.py -q
LEGAL_WORKBENCH_RUN_POSTGRES_TESTS=1 uv run --locked pytest \
  tests/test_postgres_knowledge_retrieval.py -q
```

- [ ] **Step 4: Commit**

```bash
git add .env.example Makefile apps/backend
git commit -m "feat(knowledge): enforce retrieval token budgets"
```

### Task 4: Authority-aware LegalBasis validation and synthesis contracts

**Files:**

- Modify: `apps/backend/src/legal_workbench/agents/legal_contracts.py`
- Modify: `apps/backend/src/legal_workbench/agents/legal_butler.py`
- Modify: `apps/backend/src/legal_workbench/agents/contracts.py`
- Modify: `apps/backend/src/legal_workbench/agents/definitions.py`
- Modify: `apps/backend/src/legal_workbench/application/legal_context.py`
- Test: `apps/backend/tests/test_legal_agent_contracts.py`
- Create: `apps/backend/tests/test_authority_taxonomy_validation.py`
- Create: `apps/backend/tests/test_butler_grounding.py`

**Interfaces:**

- `LegalBasisItem` includes authority role, jurisdiction, and effective date.
- `AuthorizedLegalContext` carries `source_authorities` keyed by source ref.
- `validate_legal_work_product_sources` validates declared role/status/as-of.
- `validate_butler_synthesis_sources` rejects non-original and unauthorized support refs.

- [ ] **Step 1: Write failing authority and synthesis grounding tests**

Tests place law, company policy, internal opinion, and contract in one authorized set. Only law can
be formal, only contract contractual, policy internal, and opinion strategy. Repealed current law
is rejected; explicit historical `as_of` within its period is accepted; unknown status requires
confidence `<= 0.6` and missing information.

- [ ] **Step 2: Implement strict models and validators**

Specialist Run refs may appear in `participating_agents`/lineage only. The recursive support-ref
collector accepts only original authorized refs for every fact, issue, risk, strategy, action, and
conflict.

- [ ] **Step 3: Run tests and commit**

```bash
cd apps/backend
uv run --locked pytest tests/test_legal_agent_contracts.py \
  tests/test_authority_taxonomy_validation.py tests/test_butler_grounding.py -q
git add apps/backend/src/legal_workbench/agents apps/backend/src/legal_workbench/application/legal_context.py \
  apps/backend/tests
git commit -m "feat(agents): enforce authority-aware grounding"
```

### Task 5: Direct dependency context and rerun reconstruction

**Files:**

- Create: `apps/backend/src/legal_workbench/application/legal_dependencies.py`
- Modify: `apps/backend/src/legal_workbench/application/legal_agent_orchestrator.py`
- Modify: `apps/backend/src/legal_workbench/application/ports/agents.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/domain/agents.py`
- Modify: `apps/backend/tests/test_legal_agent_orchestrator.py`
- Create: `apps/backend/tests/test_legal_agent_dependencies.py`

**Interfaces:**

- Produces `DependencyContextAssembler.build(plan_id, step_id) -> DependencyContext`.
- `DependencyContext` contains direct outputs, original source union, precedent union, dependency
  Run IDs, and stale/invalid diagnostics.

- [ ] **Step 1: Write failing sibling/dependency/rerun/stale tests**

The literal DAG is A contract, B IP, C depends only A. Tests assert C never receives B, normal and
rerun C receive A's latest valid output and original refs, failed/skipped dependencies block C, a
failed rerun does not replace A's latest valid Run, and C becomes stale after a newer valid A.

- [ ] **Step 2: Implement one assembler for normal and rerun**

Delete the all-results upstream dictionary and every `upstream_outputs={}` rerun path. Persist
dependency Run IDs on the child Run and update `latest_valid_run_id` only after a valid terminal
result.

- [ ] **Step 3: Run tests and commit**

```bash
cd apps/backend
uv run --locked pytest tests/test_legal_agent_dependencies.py \
  tests/test_legal_agent_orchestrator.py tests/test_legal_agent_orchestrator_concurrency.py -q
git add apps/backend/src/legal_workbench apps/backend/tests
git commit -m "fix(agents): isolate DAG dependency context"
```

### Task 6: Unified fenced Agent execution and Legal recovery

**Files:**

- Create: `apps/backend/src/legal_workbench/application/agent_execution.py`
- Create: `apps/backend/src/legal_workbench/application/agent_recovery.py`
- Modify: `apps/backend/src/legal_workbench/application/message_analysis.py`
- Modify: `apps/backend/src/legal_workbench/application/legal_agent_orchestrator.py`
- Modify: `apps/backend/src/legal_workbench/application/analysis_recovery.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/celery_app.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/outbox.py`
- Modify: `apps/backend/src/legal_workbench/workers/tasks.py`
- Modify: `apps/backend/src/legal_workbench/application/ports/agents.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Test: `apps/backend/tests/test_message_analysis_handler.py`
- Create: `apps/backend/tests/test_agent_execution_service.py`
- Create: `apps/backend/tests/test_legal_agent_recovery.py`
- Create: `apps/backend/tests/test_postgres_legal_agent_recovery.py`

**Interfaces:**

- `AgentExecutionService.prepare(run_id, worker_id) -> PreparedAgentExecution` claims an attempt and returns a
  lease-aware heartbeat.
- `complete(lease, execution)` and `fail(lease, error)` are fenced.
- `AgentRecoveryService.recover()` returns role-specific recovered/dead-letter counts.

- [ ] **Step 1: Write failing lifecycle/fencing/crash tests**

Tests assert `QUEUED → PREPARING → RUNNING → VALIDATING → terminal`, one attempt for every Runtime
call, heartbeat extension, stale-owner rejection, duplicate delivery no-op, planning/specialist/
synthesis crash continuation, completed-Step preservation, synthesis-only retry, partial success,
and max-attempt dead-letter.

- [ ] **Step 2: Implement the generic service and adapt message analysis**

Keep message recall eligibility checks immediately before Runtime start and before success commit.
The new service owns attempt mechanics; message analysis retains Candidate-specific behavior.

- [ ] **Step 3: Convert Legal orchestration into state-based continuation**

Each delivery reads the plan from PostgreSQL and runs only the smallest unfinished role. Recovery
emits existing explicit Outbox work with stable idempotency keys.

- [ ] **Step 4: Run focused/PostgreSQL/Redis tests and commit**

```bash
cd apps/backend
uv run --locked pytest tests/test_agent_execution_service.py tests/test_legal_agent_recovery.py \
  tests/test_message_analysis_handler.py tests/test_analysis_recovery.py -q
LEGAL_WORKBENCH_RUN_POSTGRES_TESTS=1 uv run --locked pytest \
  tests/test_postgres_legal_agent_recovery.py tests/test_postgres_redis_flush_recovery.py -q
git add apps/backend/src/legal_workbench apps/backend/tests
git commit -m "feat(agents): recover all leased legal runs"
```

### Task 7: Preserve structured grounding in ReviewPackage and API

**Files:**

- Modify: `apps/backend/src/legal_workbench/application/legal_agent_orchestrator.py`
- Modify: `apps/backend/src/legal_workbench/domain/reviews.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/reviews.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/agents.py`
- Modify: `apps/backend/src/legal_workbench/api/routes/agents.py`
- Modify: `apps/backend/src/legal_workbench/api/routes/reviews.py`
- Create: `apps/backend/src/legal_workbench/api/schemas/knowledge.py`
- Create: `apps/backend/src/legal_workbench/api/routes/knowledge.py`
- Modify: `apps/backend/src/legal_workbench/api/router.py`
- Create: `apps/backend/tests/test_legal_agent_api.py`
- Create: `apps/backend/tests/test_knowledge_api.py`

**Interfaces:**

- Review responses expose item-level grounding and resolvable source metadata.
- Knowledge APIs list/detail/PATCH documents, list chunks, and list retrieval hits.

- [ ] **Step 1: Write failing API tests**

Tests assert structured source refs survive DB/API roundtrip, absolute paths are absent, invalid
authority edits return 422/409, PATCH uses Actor/If-Match/idempotency/Audit, disabled documents do
not retrieve, and chunk/hit endpoints return locator/token/count metadata.

- [ ] **Step 2: Implement handlers, schemas and routes**

Routes call application handlers/repositories through UoW; they never execute ORM directly.

- [ ] **Step 3: Run tests and commit**

```bash
cd apps/backend
uv run --locked pytest tests/test_legal_agent_api.py tests/test_knowledge_api.py \
  tests/test_security_and_outbox.py -q
git add apps/backend/src/legal_workbench apps/backend/tests
git commit -m "feat(api): expose managed grounded knowledge"
```

### Task 8: Knowledge management and source drawer UI

**Files:**

- Create: `apps/web/src/pages/KnowledgePage.tsx`
- Create: `apps/web/src/pages/KnowledgePage.test.tsx`
- Create: `apps/web/src/components/SourceReferenceDrawer.tsx`
- Create: `apps/web/src/components/SourceReferenceDrawer.test.tsx`
- Modify: `apps/web/src/components/LegalButlerPanel.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/services/api.ts`
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/styles/global.css`

**Interfaces:**

- Adds `/knowledge` using the existing Ant Design shell and tokens.
- Adds item-level source actions to Butler/review grounding sections.

- [ ] **Step 1: Write failing UI behavior tests**

Tests cover list loading/empty/error/retry, pending metadata, authority edit, enable/disable, chunk
view, retrieval hit view, absolute-path absence, and source drawer locator/title/type display.

- [ ] **Step 2: Implement the smallest existing-design UI**

Use current responsive primitives and no new UI framework. AI output is labeled as draft and source
metadata as authorized evidence, never as approved fact.

- [ ] **Step 3: Run frontend gates and commit**

```bash
npm run test --workspace @legal-workbench/web
npm run typecheck
npm run build
git add apps/web
git commit -m "feat(web): manage grounded legal knowledge"
```

### Task 9: Migration/integration/Real E2E, docs and publication

**Files:**

- Modify: `apps/backend/tests/test_real_codex_legal_agent_e2e.py`
- Create: `apps/backend/tests/test_real_codex_legal_reliability_e2e.py`
- Modify: `docs/design/AGENT_PROTOCOL.md`
- Modify: `docs/design/KNOWLEDGE_RETRIEVAL.md`
- Modify: `docs/design/DATA_MODEL.md`
- Modify: `docs/design/API_CONTRACTS.md`
- Modify: `docs/design/SYSTEM_DESIGN.md`
- Modify: `docs/CODEX_HANDOFF.md`
- Modify: `README.md`

**Interfaces:**

- Produces final test evidence and current implementation boundaries.

- [ ] **Step 1: Run fresh migration and downgrade/upgrade**

```bash
cd apps/backend
uv run --locked alembic -c alembic.ini upgrade head
uv run --locked alembic -c alembic.ini downgrade 20260809_0018
uv run --locked alembic -c alembic.ini upgrade head
```

- [ ] **Step 2: Run PostgreSQL + Redis, import, budget, DAG, recovery, authority and grounding tests**

Run the named focused suites with `LEGAL_WORKBENCH_RUN_POSTGRES_TESTS=1`; record exact counts and
skip reasons.

- [ ] **Step 3: Run Real Codex E2E**

```bash
LEGAL_WORKBENCH_ENABLE_REAL_CODEX=true \
LEGAL_WORKBENCH_RUN_REAL_CODEX_TESTS=1 \
uv run --locked pytest tests/test_real_codex_legal_reliability_e2e.py -m real_codex -q
```

The test uses non-sensitive fixtures and asserts planning/specialist/synthesis recovery, DAG sibling
isolation, authority roles, item-level original refs, pending ReviewPackage, and no Communication.
If the explicit isolated credential gate is unavailable, preserve and report the exact skip/failure.

- [ ] **Step 4: Update formal docs and run full gates**

```bash
PATH=/private/tmp/legal-workbench-uv-0.12.3/bin:$PATH make lint
PATH=/private/tmp/legal-workbench-uv-0.12.3/bin:$PATH make test
npm run build
docker compose config --quiet
git diff --check
```

- [ ] **Step 5: Commit docs, verify scope, push and open Draft PR**

```bash
git add README.md docs apps/backend/tests/test_real_codex_legal_agent_e2e.py \
  apps/backend/tests/test_real_codex_legal_reliability_e2e.py
git commit -m "docs: record legal reliability verification"
git push -u origin codex/legal-agent-reliability-knowledge
```

Open a Draft PR against `main`; do not merge it.
