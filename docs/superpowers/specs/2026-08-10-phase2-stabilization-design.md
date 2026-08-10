# Phase 2 Stabilization / Production Hardening Design

**Date:** 2026-08-10

**Status:** Approved
**Scope:** Reliability hardening of the existing Legal Butler / Specialist Agent system in PR #12

## Outcome

Close the remaining production-correctness gaps in PR #12 without adding Agents, providers, services, automatic communications, or a new Plan generation/epoch model. PostgreSQL remains the durable source of truth; Redis/Celery remain coordination; all Agent output remains draft-only and behind Human Review.

## Current assessment

PR #12 already has the right foundations: bounded deterministic orchestration, Attempt lease/heartbeat/fencing, PostgreSQL recovery, direct dependency context, deterministic knowledge retrieval, authority taxonomy, grounded Butler synthesis, and a pending ReviewPackage rather than automatic Communication.

The remaining merge blockers are above the individual Attempt layer:

1. A recovery expiry is not guarded by a database predicate proving that the Attempt lease is actually expired, and recovery does not fail closed when expiry loses a race.
2. Step and Plan mutations do not consistently prove that the completing Run is still the current Run, so overlapping reruns or stale completion can overwrite newer lineage.
3. A stale downstream Step is removed from synthesis output, but sources from its old Run can still enter the new synthesis authorization set.
4. Current-law analysis repeatedly derives `date.today()` during one Plan, so recovery or rerun across midnight can change the applicable date.
5. Specialist citation audit metadata is model-supplied instead of rebuilt from canonical server-side source metadata.
6. The production Web image uses Node 22 while Local/CI use Node 24, and CI validates Compose without building the production images.

## Design

### 1. Execution and recovery fencing

- Retain the existing `AgentRunAttempt` lease token as the physical worker fence.
- Make recovery expiry a compare-and-set operation: the Attempt must still be `running`, must match the Run and attempt number, and its stored lease must be at or before the recovery timestamp.
- If recovery cannot expire the current Attempt, it must leave Run, Step, and Plan facts unchanged for that candidate.
- For Specialist completion/failure, lock the Step and require `step.latest_run_id == run.id` before mutating Step state.
- For synthesis completion/failure, lock the Plan and require `plan.synthesis_run_id == run.id` before mutating Plan state or creating the accepted DraftArtifact/ReviewPackage.
- Start an explicit rerun under a Plan row lock. Reject it while the Plan is already active, and reserve the Step by setting its current Run inside the same transaction that creates the Run.
- Reuse existing status, version, current/latest Run fields and database row locks. Do not add a generation/epoch state model.

### 2. DAG lineage and source authorization

- A valid dependency is the dependency Step's `latest_valid_run_id` with a terminal valid Step status.
- A Specialist Run persists exactly the direct dependency Run IDs it consumed.
- Upstream rerun invalidates downstream Steps whose persisted dependency IDs no longer equal the dependencies' latest valid Run IDs.
- Synthesis may include failure placeholders for invalidated Steps, but may authorize sources only from valid current Step results. A stale, failed, skipped, or superseded Run cannot expand synthesis authorization.
- Historical Runs, artifacts, reviews, and audit events remain append-only.

### 3. Stable legal analysis date

- Add `analysis_effective_date` to `AgentExecutionPlan` and persist it once when the Plan is created.
- `analysis_effective_date` means the stable current-law evaluation date for the Plan. It is reused by retries, recovery, reruns, Specialist retrieval, validation, and synthesis.
- `historical_as_of` remains an optional explicit historical-law instruction. It is never inferred from or replaced by `analysis_effective_date`.
- When `historical_as_of` is present, retrieval and legal-basis validation use it as the historical applicability date while retaining the separately persisted `analysis_effective_date` for audit.
- Existing Plans are migrated with a deterministic backfill derived from their creation date.

### 4. Canonical Specialist citations

- A model may select only an authorized `sourceRef`.
- After fail-closed source and authority validation, the server rebuilds citation title, source type, locator, content hash, and internal-precedent marker from persisted authorized source metadata.
- Model-supplied audit metadata is discarded. Unknown or missing canonical metadata fails closed.
- Legal-basis authority role/status/effective-date validation continues to use deterministic authority metadata, not citation prose.

### 5. Build consistency

- `.node-version` remains the Node source of truth and the Web production image is aligned to Node 24.15.0.
- Python stays on the 3.12 line. Exact patch pinning is used only where it reduces actual drift without creating a second source of truth; Local, CI, Docker, and documentation must state the same policy.
- uv remains pinned to 0.12.3 and Codex CLI remains supplied by the single deployment setting.
- CI builds both production Dockerfiles in addition to Compose validation.

### 6. Verification

Regression tests are added before implementation for:

- concurrent rerun rejection and stale Specialist/synthesis completion;
- lease-expiry compare-and-set races;
- downstream invalidation and stale source isolation;
- stable analysis date across retry/recovery/rerun;
- Specialist citation canonicalization and unauthorized/missing metadata rejection.

A PostgreSQL-backed synthetic E2E uses a clearly named Fake Runtime to cover:

`Message -> Candidate -> Matter/WorkItem -> Butler -> Specialist -> Knowledge -> Synthesis -> pending ReviewPackage`

It asserts that no Communication is created. Real Codex remains a separate, credential-gated, non-sensitive test and is never represented by Fake Runtime evidence.

## Non-goals

- No new Specialist, LLM provider, vector database, service, RBAC, SSO, or UI redesign.
- No automatic Feishu send or Communication creation.
- No Agent writes to formal Matter/WorkItem records.
- No real legal-material scan or production token-budget calibration.
- No merge.
