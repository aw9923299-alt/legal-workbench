# `entities.py` / `ports.py` Import and Dependency Impact

Date: 2026-08-09
Baseline: `origin/main@d009612`

## Measured impact

| Source | Size | Definitions | Direct importers | Imported names |
|---|---:|---:|---:|---:|
| `domain/entities.py` | 2,445 lines | 46 classes | 72 files | 346 |
| `application/ports.py` | 466 lines | 30 protocols | 25 files | 28 |

The main coupling hotspot is not behavioral coupling between every entity. It is the
single public import path used by application services, adapters, repositories, API
mapping, and tests. Rewriting all 72 importers at once would increase regression risk
without improving the modular-monolith boundary.

## Cohesion map

The existing definitions form these bounded contexts:

| Context | Domain objects | Application ports |
|---|---|---|
| Audit and control | `AuthenticatedActorId`, `AuditEvent`, `OutboxEvent`, `IdempotencyRecord` | audit, outbox, idempotency, unit of work |
| Candidate intake | `MessageCandidate` | candidate repository |
| Matters | `LegalMatter`, `MatterUpdateProposal`, `ProposalFieldDecision` | matter and proposal repositories |
| Work items | `WorkItem`, `PriorityConfirmation`, `Deadline`, `WorkItemDependency` | work-item, priority, deadline, dependency repositories |
| Reviews | `ReviewPackage`, `ReviewRecord`, `Communication` | review and communication repositories |
| Agents | snapshots, definitions, runs, attempts, sources, revisions, draft artifacts | snapshot, definition, run, attempt, source, draft repositories |
| Feishu | raw events, messages and versions, OAuth authorization, sync checkpoint, connection, attachments | Feishu, user authorization, and personal-sync repositories |
| Documents | extracted content, versions, segments, native Feishu documents and subscriptions | document and storage-quota repositories |
| Evaluations | evaluation case, run, and result | evaluation repository |
| Setup | settings, credentials, scopes, integration checks | setup repository |

Shared deterministic helpers (`utc_now`, `text_hash`, `require_aware`) have no
infrastructure dependencies and belong in `domain/common.py`.

## Target dependency direction

```text
api / workers / integrations ──> application ──> domain
infrastructure ────────────────> application ports + domain
agents ────────────────────────> application contracts + domain
```

No new package, service, database schema, or network boundary is introduced. Domain
modules continue to import only Python standard-library code plus `domain.enums` and
`domain.errors`.

## Migration strategy

1. Add a failing architecture contract that imports each target bounded-context module,
   verifies legacy public imports remain identical, and rejects forbidden domain-layer
   dependencies.
2. Move definitions by cohesive blocks into focused domain modules. Keep
   `domain/entities.py` as a compatibility facade that re-exports the same public names.
3. Replace `application/ports.py` with an `application/ports/` package grouped by the
   same contexts. Keep `from legal_workbench.application.ports import ...` compatible
   through `ports/__init__.py`.
4. Run the focused architecture test, Ruff, mypy, and the full backend suite after each
   migration stage. Importer rewrites are limited to internal boundary improvements;
   unrelated production and test imports remain compatible.

## Cycle risks and controls

- Domain context modules must not import one another through `domain.entities`; shared
  helpers come only from `domain.common`.
- Port modules may import domain context modules but never infrastructure implementations.
- The unit-of-work protocol is the only intentional composition point. It imports the
  focused repository protocols and exposes them as attributes.
- `ports/__init__.py` is a re-export facade only; it contains no behavior.
- An AST-based test guards forbidden `domain -> application/api/infrastructure/agents`
  imports, and an import walk guards runtime cycles.

## Contract and schema impact

The architecture cleanup changes no database model, Alembic revision, domain behavior,
or HTTP payload. The separate Personal Sync time correction intentionally replaces the
ambiguous `startedAt` response field with `claimedAt`, `windowStart`, `windowEnd`, and
`completedAt`; that explicit API change is outside the compatibility promise for the
file split.
