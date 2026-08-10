# Legal Agent Reliability and Knowledge Hardening Design

## 1. Scope and delivery boundary

This change hardens the existing Legal Butler, specialist DAG, synthesis grounding, and
PostgreSQL knowledge pipeline on top of `origin/main@2d6106e`. It remains a single-user local Mac
modular monolith using PostgreSQL, Redis/Celery, Outbox, Unit of Work, Codex Runtime, and Human
Review.

The real `Codex-Obs法务项目` material audit is deliberately deferred because the user requested
functional work first and the visible OneDrive directory is currently blocked by macOS TCC. The
scanner, importer, inventory schema, deterministic token estimator, and fixture-backed integration
tests are still delivered. No result from the OneDrive `.noindex` placeholder store is treated as a
real audit.

Out of scope:

- new professional Agents;
- multi-user identity, SSO, RBAC, tenancy, or services;
- a second document parser or external embedding/LLM service;
- OCR or additional production parsers beyond PDF, DOCX, TXT, and Markdown;
- automatic communication, automatic legal classification by Codex, or automatic PR merge.

## 2. Architecture

The implementation extends the current chain instead of replacing it:

```text
Local read-only source
→ deterministic scanner
→ generic DocumentSource / DocumentVersion
→ existing isolated document extractor
→ DocumentExtraction / DocumentSegment
→ KnowledgeDocument / KnowledgeChunk
→ PostgreSQL FTS + pg_trgm
→ deterministic authority and token budget gates
→ AuthorizedLegalContext
→ leased AgentRun
→ grounded specialist and Butler output
→ DraftArtifact / ReviewPackage / Human Review
```

Absolute paths are an importer concern. Persistent provenance records use a configured source-root
identifier, relative path, filename, content hash, timestamps, and scan lineage. Agent inputs and
ordinary logs never contain an absolute path or legal正文.

## 3. Local source, versioning, and incremental ingestion

### 3.1 Generic document provenance

The existing attachment-specific document path is generalized without synthesizing Feishu
attachments:

- `LocalDocumentSource` is the logical file at `(source_root_key, relative_path)`;
- `LocalDocumentObservation` is append-only scan provenance linking a source to a
  `DocumentVersion`, including observed metadata and state;
- `DocumentVersion.attachment_id` and `DocumentSegment.attachment_id` become nullable only for
  local-source content;
- a local-content `DocumentVersion` is unique by SHA-256 and can be referenced by multiple source
  observations, so duplicate files are parsed and chunked once;
- the Feishu attachment path retains its current uniqueness and behavior.

An XOR-style domain invariant distinguishes attachment-backed and local-source document versions.
Repository methods expose the distinction explicitly; callers never infer it from nulls.

### 3.2 Scanner and importer

`make knowledge-import SOURCE="..."` invokes a local CLI application service. The scanner:

1. requires an existing directory and opens source files read-only;
2. rejects `.noindex`/File Provider backing-store paths to avoid treating placeholders as content;
3. excludes `.git`, `node_modules`, `.venv`, cache/build/temp/tooling directories, hidden temporary
   files, and deterministically named backup directories;
4. records relative paths only in normal output and logs;
5. streams SHA-256 without loading a whole file into memory;
6. supports only PDF, DOCX, TXT, Markdown through the existing isolated extractor;
7. isolates single-file parse errors and commits each file result independently;
8. reuses the latest observation when metadata and SHA-256 are unchanged;
9. links a new path with an existing hash to the existing parsed content;
10. creates a new observation/version link when content changes;
11. marks unseen sources `missing` after a completed scan without deleting prior versions,
    segments, chunks, retrieval logs, or AgentRun provenance.

Each scan has a durable batch record with discovered, unchanged, added, changed, duplicate,
unsupported, failed, and missing counts. Sensitive text is never placed in logs.

### 3.3 Inventory

The same scanner/extractor and token estimator produce
`artifacts/knowledge-ingestion/legal-material-inventory.json` when a readable real source is later
available. The schema reports logical and allocated bytes, counts/sizes by extension, parseable,
unsupported and failed counts, extracted characters, estimated raw/unique tokens, SHA-256
duplicate savings, category totals, exclusion policy, errors by safe code, and A/B per-run token
comparison. It never sends content to Codex.

## 4. Token estimation and budget

No tokenizer is added as a production dependency. `DeterministicTokenEstimator` uses an installed
compatible tokenizer when explicitly supplied; otherwise it reports `estimated=true` and uses
`ceil(UTF-8 byte length / 4)`. The estimator version and exact/estimated flag are persisted on
chunks, inventory, and retrieval logs.

Knowledge chunks are split deterministically at paragraph/line boundaries and then safe character
boundaries so every new chunk fits `LEGAL_KNOWLEDGE_MAX_SINGLE_CHUNK_TOKENS`.

Retrieval is deterministic:

```text
metadata eligibility
→ FTS / pg_trgm candidate ranking
→ text-hash deduplication
→ authority priority
→ stable score/id ordering
→ single-chunk, total-token and chunk-count budgets
→ AuthorizedLegalContext
```

Configuration:

- `LEGAL_KNOWLEDGE_MAX_CHUNKS`;
- `LEGAL_KNOWLEDGE_MAX_TOKENS`;
- `LEGAL_KNOWLEDGE_MAX_SINGLE_CHUNK_TOKENS`.

Defaults are conservative initial operational values and the checked-in documentation explains
that they must be recalibrated from the deferred real inventory before production acceptance.
Every search log records candidate count, selected chunk count/tokens, budget-excluded count/tokens,
query hash, filters, component/final scores, estimator version, and budget snapshot. Full query text
is not logged.

## 5. Authority taxonomy

`KnowledgeDocument` gains deterministic legal metadata:

```text
authority_type:
  unknown, law, administrative_regulation, judicial_interpretation,
  department_rule, local_regulation, local_government_rule,
  normative_document, guiding_case, court_case, regulatory_guidance,
  contract, company_policy, business_rule, legal_opinion,
  internal_precedent

authority_role:
  formal_legal_basis, persuasive_authority, contractual_basis,
  internal_basis, strategy_reference

authority_status:
  effective, superseded, repealed, unknown

metadata_status:
  ready, pending_metadata
```

It also stores issuer, authoritative title, document number, effective dates, jurisdiction, and an
`enabled` retrieval flag. The type-to-role matrix is domain code, not prompt text:

- legislation/regulations/interpretations/rules/normative documents → formal legal basis;
- guiding/court cases and regulatory guidance → persuasive authority;
- contracts → contractual basis;
- company policy and business rules → internal basis;
- legal opinions and internal precedents → strategy reference;
- unknown → no role and pending metadata.

The API rejects an invalid type/role pair. Repealed or superseded material is excluded as a current
formal basis. It can be used only when the request explicitly supplies a historical `as_of` date
within its effective period. Unknown status forces a confidence ceiling and at least one missing
information entry when cited.

First-import classification uses only normalized relative directory names, filenames, and supplied
sidecar metadata. Ambiguous material becomes `unknown/pending_metadata`; Codex is not asked to
classify it.

## 6. LegalBasis and grounding

`LegalBasisItem` becomes:

```text
proposition
source_refs
authority_role
jurisdiction
effective_date
```

Runtime validation resolves each source reference against the authorized source metadata and
fails closed when its declared role differs from the deterministic taxonomy. Company policy,
business rules, legal opinions, internal precedents, and contracts cannot satisfy
`formal_legal_basis`.

Butler synthesis uses per-item grounding objects:

- core facts: `fact`, `source_refs`;
- issues: `issue`, `source_refs`;
- risks: `description`, `severity`, `likelihood`, `support_refs`;
- strategy: `action`, `rationale`, `support_refs`;
- next actions: `action`, `support_refs`;
- conflicts: `topic`, `agent_positions`, `support_refs`, `resolution_needed`.

The synthesis authorized union contains only original snapshot/message/attachment/knowledge refs
authorized to participating valid runs. Specialist run refs are retained as lineage but cannot be
used as a final support ref. Any support ref outside the original authorized union rejects the
output. The complete structured grounding payload is stored on the DraftArtifact and
ReviewPackage, not flattened to strings.

## 7. DAG dependency and rerun semantics

`DependencyContextAssembler` is the single code path for normal execution and rerun:

1. read only `step.depends_on`;
2. resolve each dependency's latest valid Run (`COMPLETED` or `NEEDS_MORE_INFORMATION`);
3. reject execution if a direct dependency has no valid Run;
4. include only those direct dependency outputs;
5. propagate the original authorized `source_refs` and `internal_precedent_refs` used by those
   dependency runs;
6. add specialist Run IDs only as provenance metadata.

Sibling output never enters downstream input. `AgentPlanStep.latest_valid_run_id` is updated only
by a valid terminal run, so a failed rerun cannot erase the last valid output. Each dependent run
persists the dependency Run IDs it consumed. A dependent output is stale when any direct
dependency has a different latest valid Run; stale outputs are excluded from synthesis and require
an explicit rerun. Rerunning a Step reconstructs dependencies through the same assembler and then
reruns only the affected synthesis; it does not rerun unrelated siblings.

## 8. Unified leases, attempts, and recovery

Legal runs stop constructing `RUNNING` rows directly. `AgentExecutionService` generalizes the
existing message-analysis attempt path for every real Codex call:

```text
QUEUED → PREPARING → RUNNING → VALIDATING → terminal
```

Each physical call claims an `AgentRunAttempt` with lease token, worker ID, expiry, and heartbeat.
The Runtime receives a heartbeat callback. Completion/failure is accepted only while the current
lease token is valid; a stale owner cannot write output.

The same service is used by `message_judgement`, Butler planning, specialist, and Butler synthesis.
Existing message behavior and recall gates remain intact.

`AgentRecoveryService` extends the PostgreSQL recovery scan under an advisory lock. It finds stale
Legal plans/steps/runs, expires the current attempt with fencing, and emits one idempotent Outbox
continuation for the smallest unfinished unit:

- planning crash → resume planning;
- specialist crash → retry only that Step;
- synthesis crash → rerun synthesis only;
- completed Step → never rerun;
- repeated Celery delivery → state-based no-op/replay;
- max attempts → failed/dead-letter while preserving partial valid steps.

The plan is always reconstructed from PostgreSQL, not an in-memory wave result.

## 9. Knowledge management API and UI

The existing React/Ant Design system repurposes the existing `/library` route as the knowledge
management entry. It is not a system-wide
redesign. The page supports:

- list/filter documents and source state;
- view provenance without exposing the absolute root to Agent payloads;
- edit authority type/role, jurisdiction, effective dates/status, and enabled state;
- view chunks with locators and token counts;
- view retrieval hit/audit summaries.

Backend PATCH commands require Actor, `If-Match`, idempotency, Audit, and UoW transaction. The
frontend provides loading, empty, error, retry, disabled, pending-metadata and parse-failed states.
Review grounding items open a source drawer that resolves stored source metadata and locators.

## 10. Migration and compatibility

Alembic `20260809_0019` is reversible to `0018`. It adds local source/scan/observation tables,
generic document linkage, authority metadata, chunk token data, retrieval budget audit fields,
latest valid/dependency provenance fields, and structured ReviewPackage grounding.

Existing `0018` rows are conservatively mapped:

- `company_policy` and `business_rule` become internal basis;
- contract templates become contractual basis;
- internal/legal opinions become strategy reference;
- the broad legacy `regulation` category becomes unknown/pending metadata rather than being
  elevated to formal law;
- other ambiguous rows become unknown/pending metadata.

Downgrade removes new local knowledge records and columns only after tests prove the pre-0019
schema is restored. No source file is altered.

## 11. Verification

TDD covers scanner exclusions/read-only behavior, incremental/deduplicated/versioned import,
single-file failure isolation, budget enforcement/logging, authority matrix, historical/unknown
status behavior, sibling isolation, dependency source propagation, rerun reconstruction, stale
dependencies, synthesis grounding, fencing, crash recovery, idempotent Celery delivery, and
partial success.

Integration verification covers fresh Alembic head, `0019 → 0018 → 0019`, real PostgreSQL/Redis,
fixture-backed knowledge import, and API persistence. Real Codex E2E covers planning, specialist,
synthesis and grounded results only when the existing explicit Runtime gates and isolated
credentials are available; otherwise the exact gate is a remaining limit.

Required final commands remain:

```text
make lint
make test
npm run build
docker compose config --quiet
```

The branch is pushed and opened as a Draft PR. It is never automatically merged.
