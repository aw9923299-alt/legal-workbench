# Phase 2 Legal Agent Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persisted two-stage Legal Butler, five grounded professional legal Agents,
PostgreSQL knowledge retrieval, human-triggered orchestration and reviewable UI on the existing
Codex Runtime.

**Architecture:** Extend the existing modular monolith and Agent audit path. A deterministic
`LegalAgentOrchestrator` validates a maximum-four-step DAG, executes ready waves outside database
transactions, persists parent/child runs, synthesizes partial results and creates only drafts and
pending review packages.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, PostgreSQL 18, Alembic, Celery,
Redis, React 18, TypeScript, Vite, Ant Design, Node 24.15.0, uv 0.12.3.

## Global Constraints

- Codex remains the only reasoning/generation AI and `CodexCliRuntime` remains the only real
  Runtime.
- PostgreSQL remains the only business source of truth; Redis is coordination only.
- All external communication remains behind the existing Human Review Gate.
- Specialist Agents have no Shell, arbitrary filesystem, database, Feishu token or unrestricted
  network access.
- A Butler plan has at most four registered specialist steps and no recursive Agent dispatch.
- No SSO, RBAC, multi-tenant, multi-user, Kubernetes, cloud or microservice work.
- Existing OAuth, Feishu, recall, Candidate, Matter, WorkItem, Outbox, Audit, idempotency and lease
  behavior must remain backward compatible.

---

### Task 1: Node 24 baseline and architecture documents

**Files:**
- Modify: `.node-version`
- Modify: `package.json`
- Modify: `apps/web/package.json`
- Modify: `README.md`
- Modify: `.github/workflows/ci.yml`
- Create: `docs/superpowers/specs/2026-08-09-legal-agent-layer-design.md`

**Interfaces:**
- Consumes: local Node `v24.15.0`.
- Produces: repository-wide `>=24 <25` engine contract and CI Node 24 selection.

- [ ] **Step 1: Change the locked Node version and engines**

```text
.node-version = 24.15.0
package engines = >=24 <25
```

- [ ] **Step 2: Install from the existing lockfile and verify**

Run: `npm ci --no-audit --no-fund && node --version && npm run typecheck`
Expected: Node `v24.15.0`, install and typecheck exit 0.

- [ ] **Step 3: Commit**

```bash
git add .node-version package.json apps/web/package.json README.md .github/workflows/ci.yml docs/superpowers
git commit -m "docs: design legal agent layer"
```

### Task 2: Professional and Butler contracts

**Files:**
- Create: `apps/backend/src/legal_workbench/agents/legal_contracts.py`
- Create: `apps/backend/src/legal_workbench/agents/legal_butler.py`
- Create: `apps/backend/src/legal_workbench/agents/professional.py`
- Modify: `apps/backend/src/legal_workbench/agents/definitions.py`
- Test: `apps/backend/tests/test_legal_agent_contracts.py`

**Interfaces:**
- Produces: `ButlerPlanningOutput`, `ButlerSynthesisOutput`, `LegalWorkProduct`, five specialized
  output models, `LEGAL_SPECIALIST_KEYS`, and `build_legal_agent_definitions()`.

- [ ] **Step 1: Write failing schema and grounding tests**

```python
def test_contract_review_requires_clause_locator_and_grounded_legal_basis() -> None:
    with pytest.raises(ValidationError):
        ContractReviewProduct.model_validate(ungrounded_contract_fixture)
```

Run: `cd apps/backend && uv run --locked pytest tests/test_legal_agent_contracts.py -q`
Expected: import failure because the models do not exist.

- [ ] **Step 2: Implement strict Pydantic envelopes and definitions**

```python
LEGAL_SPECIALIST_KEYS = frozenset({
    "legal_consultation", "contract_review", "dispute_complaint",
    "ip_copyright", "labor_employment",
})
```

- [ ] **Step 3: Run tests and commit**

Run: `cd apps/backend && uv run --locked pytest tests/test_legal_agent_contracts.py -q`
Expected: all tests pass.

```bash
git add apps/backend/src/legal_workbench/agents apps/backend/tests/test_legal_agent_contracts.py
git commit -m "feat(agents): add legal work product contracts"
```

### Task 3: Plan, step and parent-child run domain model

**Files:**
- Modify: `apps/backend/src/legal_workbench/domain/enums.py`
- Modify: `apps/backend/src/legal_workbench/domain/agents.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Test: `apps/backend/tests/test_legal_execution_plan.py`

**Interfaces:**
- Produces: `AgentExecutionPlan.validate_steps(registered_keys)`, `AgentPlanStep`,
  `AgentExecutionPlanStatus`, `AgentPlanStepStatus`, `AgentRunRole`.

- [ ] **Step 1: Write failing DAG tests**

```python
def test_plan_rejects_cycle_and_more_than_four_specialists() -> None:
    with pytest.raises(DomainValidationError):
        AgentExecutionPlan.create(...cyclic_steps...)
```

Run: `cd apps/backend && uv run --locked pytest tests/test_legal_execution_plan.py -q`
Expected: import failure.

- [ ] **Step 2: Implement plan validation and run linkage fields**

The topological validator must reject unknown dependencies and cycles and return deterministic
ready waves ordered by step sequence.

- [ ] **Step 3: Run tests and commit**

```bash
git add apps/backend/src/legal_workbench/domain apps/backend/tests/test_legal_execution_plan.py
git commit -m "feat(domain): model legal agent execution plans"
```

### Task 4: Alembic persistence and repositories

**Files:**
- Create: `apps/backend/migrations/versions/20260809_0018_add_legal_agent_layer.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/application/ports/agents.py`
- Modify: `apps/backend/src/legal_workbench/application/ports/documents.py`
- Modify: `apps/backend/src/legal_workbench/application/ports/infrastructure.py`
- Modify: `apps/backend/src/legal_workbench/application/ports/__init__.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/__init__.py`
- Test: `apps/backend/tests/test_postgres_legal_agent_persistence.py`

**Interfaces:**
- Produces: plan/step repositories, knowledge repositories, retrieval audit repository, and
  parent/child run queries.

- [ ] **Step 1: Write failing PostgreSQL repository roundtrip tests**

The test persists a plan, two dependent steps, parent/child runs, one knowledge document/chunk and
one retrieval log, then reads exact IDs/statuses/provenance back.

- [ ] **Step 2: Add reversible migration and SQLAlchemy mappings**

Run: `cd apps/backend && uv run --locked alembic -c alembic.ini upgrade head`
Expected: `20260809_0018` is head.

- [ ] **Step 3: Implement repositories and run integration test**

Run: `cd apps/backend && LEGAL_WORKBENCH_RUN_POSTGRES_TESTS=1 uv run --locked pytest tests/test_postgres_legal_agent_persistence.py -q`
Expected: pass against migrated PostgreSQL.

- [ ] **Step 4: Commit**

```bash
git add apps/backend/migrations apps/backend/src/legal_workbench apps/backend/tests/test_postgres_legal_agent_persistence.py
git commit -m "feat(storage): persist legal plans and knowledge retrieval"
```

### Task 5: Generic Codex Runtime contract registry

**Files:**
- Create: `apps/backend/src/legal_workbench/agents/contracts.py`
- Modify: `apps/backend/src/legal_workbench/agents/runtime.py`
- Modify: `apps/backend/src/legal_workbench/agents/codex_cli.py`
- Modify: `apps/backend/src/legal_workbench/application/message_analysis.py`
- Test: `apps/backend/tests/test_codex_runtime.py`
- Test: `apps/backend/tests/test_professional_codex_runtime.py`

**Interfaces:**
- Produces: `LegalAgentContractRegistry.prepare_input(...)`, `validate_output(...)`, and generic
  `AgentExecutionResult.output: BaseModel`.
- Preserves: message judgement input/output and source business validation.

- [ ] **Step 1: Write failing contract selection tests**

```python
async def test_runtime_validates_contract_review_with_the_registered_schema(tmp_path: Path) -> None:
    result = await runtime.execute(contract_definition, run, legal_context)
    assert isinstance(result.output, ContractReviewProduct)
```

- [ ] **Step 2: Generalize Runtime without adding tools**

The Runtime receives a prepared JSON payload in `AgentExecutionContext.input_payload`; registry
validation occurs before process start and after output read. Repair reuses that exact payload.

- [ ] **Step 3: Run old and new runtime tests and commit**

Run: `cd apps/backend && uv run --locked pytest tests/test_codex_runtime.py tests/test_professional_codex_runtime.py tests/test_message_analysis_handler.py -q`
Expected: all pass.

```bash
git add apps/backend/src/legal_workbench/agents apps/backend/src/legal_workbench/application/message_analysis.py apps/backend/tests
git commit -m "refactor(runtime): support registered legal agent contracts"
```

### Task 6: Knowledge registration and retrieval

**Files:**
- Create: `apps/backend/src/legal_workbench/domain/knowledge.py`
- Create: `apps/backend/src/legal_workbench/application/knowledge.py`
- Create: `apps/backend/src/legal_workbench/infrastructure/knowledge.py`
- Test: `apps/backend/tests/test_knowledge_retrieval.py`
- Test: `apps/backend/tests/test_postgres_knowledge_retrieval.py`

**Interfaces:**
- Produces:
  `KnowledgeRetrievalService.search(KnowledgeSearchRequest) -> list[KnowledgeSearchResult]` and
  `KnowledgeRegistrationService.register_document_version(...)`.

- [ ] **Step 1: Write failing filter/ranking/precedent tests**

Tests prove agent type, matter type, jurisdiction, document type, effective date and source priority
affect eligibility/ranking; expired sources are excluded; internal precedent is labeled and cannot
satisfy formal legal basis.

- [ ] **Step 2: Implement FTS + pg_trgm repository query**

The query uses PostgreSQL `websearch_to_tsquery('simple', :query)` and
`similarity(normalized_text, :normalized_query)`, then adds deterministic authority/effective scores.

- [ ] **Step 3: Run unit and PostgreSQL tests and commit**

```bash
git add apps/backend/src/legal_workbench apps/backend/tests/test_knowledge_retrieval.py apps/backend/tests/test_postgres_knowledge_retrieval.py
git commit -m "feat(knowledge): retrieve grounded legal sources"
```

### Task 7: Deterministic LegalAgentOrchestrator

**Files:**
- Create: `apps/backend/src/legal_workbench/application/legal_context.py`
- Create: `apps/backend/src/legal_workbench/application/legal_agent_orchestrator.py`
- Create: `apps/backend/src/legal_workbench/application/legal_agent_results.py`
- Test: `apps/backend/tests/test_legal_agent_orchestrator.py`
- Test: `apps/backend/tests/test_legal_agent_orchestrator_concurrency.py`

**Interfaces:**
- Produces:
  `LegalAgentOrchestrator.execute(LegalAgentTrigger) -> LegalAgentOrchestrationResult`,
  `rerun_step(plan_id, step_id, ...)`, and persisted artifact/review IDs.

- [ ] **Step 1: Write failing single, parallel, sequential, partial and retry tests**

The concurrency test uses a controlled Runtime barrier to prove independent steps overlap while a
dependent step starts only after its prerequisite completes.

- [ ] **Step 2: Implement short-transaction orchestration**

Use topological waves and `asyncio.TaskGroup`. Each Runtime call is between a prepare transaction
and a result transaction. Synthesis always receives explicit failures and conflicts.

- [ ] **Step 3: Run tests and commit**

Run: `cd apps/backend && uv run --locked pytest tests/test_legal_agent_orchestrator.py tests/test_legal_agent_orchestrator_concurrency.py -q`
Expected: all pass.

```bash
git add apps/backend/src/legal_workbench/application apps/backend/tests/test_legal_agent_orchestrator*.py
git commit -m "feat(orchestration): run bounded legal agent DAGs"
```

### Task 8: API, Outbox and Worker triggers

**Files:**
- Create: `apps/backend/src/legal_workbench/api/schemas/legal_agents.py`
- Create: `apps/backend/src/legal_workbench/api/routes/legal_agents.py`
- Modify: `apps/backend/src/legal_workbench/api/router.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/outbox.py`
- Modify: `apps/backend/src/legal_workbench/workers/tasks.py`
- Modify: `apps/backend/src/legal_workbench/application/handlers.py`
- Modify: `apps/backend/src/legal_workbench/application/queries.py`
- Test: `apps/backend/tests/test_legal_agent_api.py`
- Test: `apps/backend/tests/test_legal_agent_outbox.py`

**Interfaces:**
- Produces manual trigger/list/detail/rerun endpoints and idempotent `LegalButlerRequested` handling.

- [ ] **Step 1: Write failing authenticated API and duplicate-trigger tests**

Tests assert stable idempotent replay, persisted plan reference, no outbound event and parent-child
query shape.

- [ ] **Step 2: Implement API and explicit Outbox handler**

The API queues a persisted request; Workers pass IDs only and compose the same orchestrator used by
tests. Unknown event types remain fail-closed.

- [ ] **Step 3: Run API/Outbox tests and commit**

```bash
git add apps/backend/src/legal_workbench apps/backend/tests/test_legal_agent_api.py apps/backend/tests/test_legal_agent_outbox.py
git commit -m "feat(api): trigger and inspect legal butler runs"
```

### Task 9: Evaluation fixtures and real E2E runners

**Files:**
- Create: `apps/backend/tests/fixtures/evaluations/legal_agents_v1.json`
- Create: `apps/backend/src/legal_workbench/application/legal_agent_evaluations.py`
- Create: `scripts/run_legal_agent_e2e.py`
- Test: `apps/backend/tests/test_legal_agent_evaluations.py`
- Test: `apps/backend/tests/test_legal_agent_e2e_fake.py`

**Interfaces:**
- Produces deterministic quality scores and explicit Fake/Real result classification.

- [ ] **Step 1: Write failing fixture/scoring and Case A/B pipeline tests**

- [ ] **Step 2: Add five specialist fixtures, Butler fixtures and dual-gated real runner**

The real runner refuses unless `LEGAL_WORKBENCH_ENABLE_REAL_CODEX=true` and
`--allow-real-runtime` are both present.

- [ ] **Step 3: Run Fake tests and an available Real Runtime smoke**

Run: `cd apps/backend && uv run --locked pytest tests/test_legal_agent_evaluations.py tests/test_legal_agent_e2e_fake.py -q`
Expected: Fake pipeline tests pass and are labeled Fake.

- [ ] **Step 4: Commit**

```bash
git add apps/backend scripts/run_legal_agent_e2e.py
git commit -m "test(agents): evaluate professional legal work products"
```

### Task 10: Matter and Agent Center UI

**Files:**
- Create: `apps/web/src/components/LegalAgentWorkspace.tsx`
- Create: `apps/web/src/components/LegalAgentWorkspace.test.tsx`
- Modify: `apps/web/src/pages/TaskDetailPage.tsx`
- Modify: `apps/web/src/pages/AgentCenterPage.tsx`
- Modify: `apps/web/src/services/api.ts`
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/services/apiLabels.ts`
- Modify: `apps/web/src/styles/global.css`
- Test: `apps/web/src/pages/AgentCenterPage.test.tsx`

**Interfaces:**
- Consumes legal plan APIs.
- Produces `让管家处理`, plan/specialist/synthesis/review UI and parent-child run collection.

- [ ] **Step 1: Write failing interaction/responsive component tests**

Tests cover objective/requirements submission, specialist-only selection, partial/conflict display,
review warning and parent-child labels.

- [ ] **Step 2: Implement with existing Ant Design/tokens**

Use responsive cards at 390, compact dependencies at 1024 and a dense plan timeline at 1440. Do not
add a UI framework or display unverified Runtime success.

- [ ] **Step 3: Run Vitest/typecheck/build and commit**

```bash
npm run test --workspace @legal-workbench/web
npm run typecheck
npm run build
git add apps/web
git commit -m "feat(web): add legal butler workspace"
```

### Task 11: Full verification and browser QA

**Files:**
- Create: `docs/ui-review/2026-08-09-legal-agent-layer.md`
- Modify: `docs/design/AGENT_PROTOCOL.md`
- Modify: `docs/design/DATA_MODEL.md`
- Modify: `docs/design/API_CONTRACTS.md`
- Modify: `docs/design/KNOWLEDGE_RETRIEVAL.md`
- Modify: `docs/CODEX_HANDOFF.md`

**Interfaces:**
- Produces release evidence with explicit Fake/Real and environment boundaries.

- [ ] **Step 1: Run migration fresh and downgrade/upgrade roundtrip**

```bash
cd apps/backend
uv run --locked alembic -c alembic.ini upgrade head
uv run --locked alembic -c alembic.ini downgrade 20260808_0017
uv run --locked alembic -c alembic.ini upgrade head
```

- [ ] **Step 2: Run full gates**

```bash
make lint
make test
npm run build
docker compose config --quiet
```

- [ ] **Step 3: Run PostgreSQL/Redis orchestration tests and Real E2E**

Record exact Case A/B status, parent-child counts, citation checks, review package status and the
absence of Communication rows.

- [ ] **Step 4: Browser verification**

Use Playwright MCP at 1440×900, 1024×768 and 390×844 for the Matter and Agent Center routes, main
dialog, plan states, console/network and page overflow. Save before/after screenshots and the QA
report.

- [ ] **Step 5: Commit documentation**

```bash
git add docs
git commit -m "docs: record legal agent verification"
```
