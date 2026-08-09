# Phase 2 Legal Butler and Professional Agents Design

Date: 2026-08-09
Base: `origin/main@45024ad`
Branch: `codex/legal-agent-layer`

## 1. Goal

Deliver the first usable legal-work production layer inside the existing modular monolith:

```text
confirmed Candidate / existing Matter / WorkItem
→ legal_butler planning
→ bounded specialist DAG
→ legal_butler synthesis
→ DraftArtifact + ReviewPackage
→ human review
```

The implementation keeps PostgreSQL as the business source of truth, Redis/Celery as queue and
coordination infrastructure, Codex as reasoning only, deterministic application services as the
only writers, and the existing review gate as the only path toward external communication.

## 2. Scope boundaries

- Local single-user Mac deployment only.
- No SSO, RBAC, multi-tenant or multi-user permission model.
- No Kubernetes, cloud deployment, microservices, new LLM, external embedding service, or second
  Agent Runtime.
- No Agent receives Shell, arbitrary filesystem, database credentials, Feishu tokens, or
  unrestricted network tools.
- No Agent mutates Matter or WorkItem and no Agent sends a message.
- A plan contains at most four specialist steps. There is no model-driven recursive dispatch.
- Existing OAuth, Feishu sync, recall rules, Candidate, Matter, WorkItem, Outbox, Audit,
  idempotency, leases and recovery remain intact.
- The repository Node baseline moves from 22.23.2 to local Node 24.15.0 by explicit user request;
  Python remains 3.12 and uv remains 0.12.3.

## 3. Considered approaches

### A. Extend the existing Runtime and modular monolith (selected)

Add typed contracts, plan/step persistence, parent-child run metadata, retrieval metadata and a
deterministic orchestrator around the current `AgentDefinition`, `AgentRun`, `ContextSnapshot`,
`CodexCliRuntime`, `DraftArtifact` and `ReviewPackage` models. This preserves audit continuity and
the current safety boundary.

### B. Let Butler issue Agent calls directly (rejected)

This reduces application code but makes recursion, tool expansion, retry and audit behavior model
controlled. It violates the deterministic orchestration and no-recursion requirements.

### C. Build a separate specialist Runtime (rejected)

This avoids generalizing the current message-specific Runtime, but duplicates security controls,
leases, output repair, persistence and health checks. It creates two incompatible audit paths.

## 4. Domain and persistence

### 4.1 Execution plan

`AgentExecutionPlan` is an aggregate with immutable plan content and deterministic status changes.

```text
id, matter_id, work_item_id, objective
status: planned | running | partial | completed | failed | needs_information
planning_run_id, synthesis_run_id
synthesis_strategy, missing_information, requires_user_input
correlation_id, idempotency_key, created_by, created_at, updated_at, version
```

`AgentPlanStep` stores:

```text
id, execution_plan_id, step_id, sequence
agent_key, objective, depends_on[], context_requirements[]
status: pending | ready | running | completed | failed | skipped | needs_information
latest_run_id, attempt_count, failure_code, failure_message
created_at, updated_at, version
```

Plan validation is pure domain behavior:

- the specialist registry is exactly `legal_consultation`, `contract_review`,
  `dispute_complaint`, `ip_copyright`, `labor_employment`;
- one to four steps;
- unique non-empty step IDs;
- dependencies refer to steps in the same plan;
- Kahn topological validation rejects cycles;
- an explicitly requested single specialist produces a one-step plan;
- no step may target `legal_butler` or `message_judgement`.

### 4.2 Parent/child runs

The existing `agent_runs` table gains nullable:

```text
execution_plan_id, plan_step_id, parent_run_id, retry_of_run_id
run_role: standalone | butler_planning | specialist | butler_synthesis
```

Planning is the root run. Specialist and synthesis runs reference the planning run as parent. A
manual or automatic retry creates a new child run and records `retry_of_run_id`; no historical run
is overwritten. Existing message runs default to `standalone`, preserving compatibility.

### 4.3 Knowledge metadata

The existing `DocumentVersion`/`DocumentSegment` pipeline remains the only file parsing path.
Knowledge registration imports already extracted segments and records their original segment IDs;
it does not parse files again.

`knowledge_documents` stores:

```text
source_type, source_id, document_version_id?, matter_id?
title, document_type, agent_types[], matter_types[], jurisdiction
effective_from?, effective_to?, status, source_priority
internal_precedent, confidentiality, approved_by, created_at, updated_at, version
```

`knowledge_chunks` stores the authorized retrieval projection:

```text
knowledge_document_id, document_segment_id?, sequence, locator
text, normalized_text, text_hash, search_vector
```

For files, content and provenance come from `DocumentSegment`. Approved historical Matter handling
may create a bounded derived chunk from an approved review summary and is always marked
`internal_precedent=true`. It can inform process or strategy but cannot satisfy a formal legal-basis
citation.

`knowledge_retrieval_logs` stores query hash, filters, selected chunk IDs, component scores,
correlation ID, AgentRun ID and timestamp. It stores no secret or unrestricted path.

## 5. Agent contracts

### 5.1 Butler planning

`legal_butler@1.0.0` uses one registered definition and a phase discriminator. Planning output is:

```text
phase=planning
objective, matter_id, work_item_id, task_types
steps[{step_id, agent_key, objective, depends_on, context_requirements}]
missing_information, requires_user_input, synthesis_strategy
```

The Butler output is advisory until the application validator accepts it. The orchestrator never
executes an unregistered Agent, more than four steps, or a cyclic graph.

### 5.2 LegalWorkProduct envelope

Every specialist output requires:

```text
executive_summary
facts[{fact, source_refs}]
issues[]
legal_basis[{proposition, source_refs, jurisdiction, effective_date}]
analysis[]
risks[{description, severity, likelihood}]
recommended_actions[]
missing_information[]
assumptions[]
draft_response
confidence
citations[]
```

Business validation enforces:

- every fact has a source reference;
- every legal basis item has a source reference, jurisdiction and effective date;
- every analysis conclusion references facts, legal basis or upstream results;
- every citation matches an authorized ContextSnapshot or retrieval result;
- `internal_precedent` cannot be used as a formal legal-basis source;
- insufficient evidence is expressed as missing information, not invented content.

The domain-specific schemas extend the envelope:

- `legal_consultation`: question identification, legal relationships and executable advice;
- `contract_review`: summary, parties, commercial terms, clause-located risks, missing terms,
  proposed changes, fallback positions and negotiation points;
- `dispute_complaint`: timeline, claims, counterparty positions, evidence/gaps, arguments, defenses,
  risk matrix, strategy and next actions;
- `ip_copyright`: rights objects/basis, authorization chain, infringement elements, defenses,
  evidence and risk across copyright, trademark, portrait/image, music/material licensing and
  content similarity;
- `labor_employment`: relationship, discipline, termination, resignation, compensation,
  substantive basis, procedure and evidence, with substantive and procedural risks separated.

### 5.3 Butler synthesis

Synthesis receives only the accepted plan, authorized citations, completed specialist envelopes and
structured failure summaries. It returns:

```text
phase=synthesis
matter_assessment, core_facts, key_legal_issues, integrated_risks
recommended_strategy, next_actions, missing_information, draft_response
participating_agents, citations, conflicts
```

Conflicting specialist conclusions are appended to `conflicts`; the Butler cannot silently choose
one. The application service persists the synthesis as a `DraftArtifact` and creates a pending
`ReviewPackage` with an internal-only target. This never creates a `Communication`.

## 6. Runtime generalization

`CodexCliRuntime` remains the only real Runtime. A `LegalAgentContractRegistry` maps each Agent key
to its input model, output model, business validator and deterministic input builder. The current
message contract becomes one registry entry without changing its behavior.

Runtime execution still uses:

- one isolated run directory and empty HOME/CODEX_HOME;
- exact prompt and JSON Schema snapshots;
- disabled Shell, browser, MCP Apps, plugins, skills and model-driven multi-Agent;
- bounded stdout/stderr/output;
- timeout/terminate/kill and heartbeat;
- at most one same-context schema repair;
- Pydantic validation followed by business validation.

The Runtime accepts a fully prepared input payload. It never queries Matter, documents, knowledge
or PostgreSQL.

## 7. Deterministic orchestration

`LegalAgentOrchestrator` owns the full state machine:

1. build and persist an immutable authorized Matter ContextSnapshot;
2. create and execute Butler Planning run;
3. validate and persist the plan and steps;
4. repeatedly select the next ready topological wave;
5. run independent steps concurrently with `asyncio.TaskGroup`;
6. mark step outcomes in short UoW transactions;
7. skip dependency descendants after an upstream failure;
8. execute Butler Synthesis with completed outputs and explicit failure summaries;
9. persist DraftArtifact and pending ReviewPackage;
10. emit audit/outbox events, never an outbound send event.

External Codex calls happen outside database transactions. Each write phase opens its own UoW.
The correlation ID is shared by plan, runs, artifacts, review package, audit and outbox records.

Failure semantics:

- one step failure does not erase successful siblings;
- completed siblings are included in synthesis;
- a dependent step is skipped with an upstream failure code;
- no completed specialists means plan `failed` and a reviewable failure artifact;
- missing-information results set plan `needs_information`;
- some success plus some failure/skip sets `partial`;
- retry/rerun creates a new AgentRun for one plan step and can request a new synthesis;
- a duplicate trigger with the same idempotency key returns the existing plan.

## 8. Triggers and APIs

Manual API:

```text
POST /api/v1/matters/{matter_id}/legal-agent-runs
GET  /api/v1/matters/{matter_id}/legal-agent-runs
GET  /api/v1/legal-agent-plans/{plan_id}
POST /api/v1/legal-agent-plans/{plan_id}/steps/{step_id}/rerun
```

The create request supports `workItemId`, `objective`, `specialRequirements` and optional
`specialistAgentKey`. The response is a persisted plan/run reference, never an uncommitted
in-memory job.

Automatic trigger:

- after Candidate confirmation creates/links a Matter, the deterministic handler emits one
  `LegalButlerRequested` outbox event using a unique source key;
- an important new message linked to an existing Matter may emit the same event only through a
  deterministic eligibility rule;
- a database unique trigger key prevents duplicates;
- the Worker resolves IDs and invokes the same orchestrator used by the manual path.

## 9. UI design

Figma file `Dj6mMELyo2xq1kSocHDNxW` remains the recorded design workspace. On 2026-08-09 the
authenticated Starter/View seat is still at the MCP call limit, so the repository design map and
the real browser baseline are the usable design authority; no Figma modification is claimed.

The existing Matter page gains a primary `让管家处理` action and a compact objective dialog. Below
the current matter/work-item content, one legal-work panel shows:

- execution plan and step dependencies;
- specialist run status with source/citation count;
- synthesis sections, conflicts, missing information and response draft;
- DraftArtifact/ReviewPackage status and a fixed human-review warning.

The Agent Center changes from a flat technical table to a responsive collection. Butler root rows
expand into Planning → Specialist steps → Synthesis. Status labels are `Running`, `Completed`,
`Partial`, `Failed`, `Needs Information`; technical statuses remain available in details. Mobile
uses cards and does not horizontally compress the run table.

All new UI states cover loading, empty, error, retry, disabled and no-data. A completed AgentRun is
never presented as an approved legal conclusion.

## 10. Evaluation and E2E

Each specialist ships a versioned non-sensitive fixture and scoring expectations for schema,
grounding, coverage, citations, hallucination, risk, actionability, missing information and draft
usefulness. Butler fixtures score routing, unnecessary/missing Agent calls, dependency correctness
and synthesis completeness. Fake Runtime proves pipeline behavior only.

Real Codex E2E uses the existing isolated `CodexCliRuntime` and explicit real-runtime gate:

- Case A: general consultation → Butler → `legal_consultation` → synthesis → artifact/review;
- Case B: cooperation contract + copyright → Butler → `contract_review` and `ip_copyright` →
  synthesis.

Acceptance checks verify parent/child runs, citations, structured specialist outputs, synthesis,
no Communication creation and a pending human ReviewPackage. If isolated authentication is not
available, the exact gate result is reported as a remaining limit and is not called passed.

## 11. Migration and compatibility

One reversible Alembic migration adds plan/step, knowledge/retrieval and AgentRun relationship
columns. Existing rows receive server defaults or nullable columns. Downgrade drops only the new
objects and columns. Existing message analysis, Candidate revision, review and Feishu flows keep
their APIs and semantics.
