# Feishu Real Mac Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining gaps from merged PR #6 so the current Mac's authorized Feishu account can feed official and safely readable local data through Unified Ingestion, PostgreSQL, policy-controlled ContextSnapshot/Codex analysis, Candidate creation, and the existing human-review UI.

**Architecture:** Preserve the existing App/Bot connector and add capabilities to the current User OAuth/polling path. Official API data remains authoritative; a new read-only local adapter may supplement history, discovery, and downloaded resources only when it can prove an ordinary readable schema and message relationship. Every message still enters `IngestFeishuEventHandler`; PostgreSQL owns facts, leases, checkpoints, provenance, documents, analysis policy, and audit, while token bodies stay exclusively in `LocalSecretProvider` generations.

**Tech Stack:** Python 3.12; FastAPI; SQLAlchemy 2 async; PostgreSQL 18; Alembic; HTTPX; Celery/Redis; React/TypeScript/Vite/Ant Design; pytest; Vitest.

## Execution status

Implementation and automated acceptance are complete for Tasks 1-7 and the code/artifact portions of Task 8. Live official user-API probes, one PostgreSQL message ingestion, and one message-linked native document snapshot were executed with sanitized evidence. Workbench-owned OAuth/Refresh, a confirmed non-sensitive attachment body, unread state, browser UI QA, and real isolated Codex remain open environment/manual gates and are recorded as such in the capability artifacts.

## Global constraints

- Never read or export Feishu cookies, browser/session tokens, passwords, Keychain items, or process memory; never bypass local database encryption.
- Never write the Feishu client database or automatically mark messages read, reply as the user, create a formal Matter, or send unreviewed content.
- Official `app_event` / `user_api` data outranks `local_client`; local records cannot overwrite a matching official message.
- Local message records must normalize to a standard Feishu envelope and pass through `IngestFeishuEventHandler`; local attachments must be copied into the private workbench attachment root before extraction.
- PostgreSQL is the only business fact store. Redis is queue/coordination only. Codex receives bounded snapshots and never secret references or client directories.
- Real capability results use only `passed`, `failed`, `partial`, or `unsupported`. Manual dependency is recorded in the reason, not represented as a fake success.

---

### Task 1: OAuth permission contract and missing-scope state

**Files:**
- Modify: `apps/backend/src/legal_workbench/api/routes/feishu_user.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_user_auth.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/feishu_user.py`
- Modify: `apps/web/src/pages/FeishuScopesPage.tsx`
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/backend/tests/test_feishu_user_oauth.py`
- Modify: `apps/web/src/pages/FeishuScopesPage.test.tsx`

- [ ] Write a failing OAuth behavior test proving the authorization request contains `im:message.p2p_msg:get_as_user`, `im:message.group_msg:get_as_user`, `im:message:readonly`, `im:chat:readonly`, `drive:drive.search:readonly`, `drive:drive.metadata:readonly`, and `docs:document.content:read`.
- [ ] Write a failing completion/API/UI test proving omitted granted scopes produce `permission_missing`, expose only missing scope names, and never expose tokens.
- [ ] Implement the current official scope set and persist the actual token response scope set already returned by Feishu.
- [ ] Run backend OAuth and frontend page tests; scan response/audit serialization for secret values.

### Task 2: Message-linked native Feishu document context

**Files:**
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/application/context_snapshots.py`
- Modify: `apps/backend/tests/test_context_snapshot_builder.py`
- Modify: `apps/backend/tests/test_postgres_document_extraction.py`

- [ ] Add a failing real-builder test with one message-linked `FeishuDocument`, successful latest extraction, and native `DocumentSegment`; assert the snapshot contains正文 and citation fields `documentId`, `documentToken`, `paragraphNumber`, `contentHash`, `untrustedInput=true`.
- [ ] Add a negative test proving an unrelated imported/folder document is excluded.
- [ ] Add repository queries that join only selected messages through `feishu_message_document_links` and return latest successful native segments with document metadata.
- [ ] Merge native and attachment segments under the existing segment/character/single-segment bounds; record allowed document IDs/tokens in `permissionSnapshot`.
- [ ] Run snapshot, native document, message analysis, and PostgreSQL document tests.

### Task 3: Personal attachment official attempt and metadata-only fallback

**Files:**
- Modify: `apps/backend/src/legal_workbench/integrations/feishu_user_client.py`
- Create: `apps/backend/src/legal_workbench/application/feishu_user_attachments.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_personal_sync.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/outbox.py`
- Modify: `apps/web/src/pages/MessageDetailPage.tsx`
- Modify: `apps/backend/tests/test_attachment_download_pipeline.py`
- Modify: `apps/backend/tests/test_feishu_personal_sync.py`
- Modify: `apps/web/src/pages/MessageDetailPage.test.tsx`

- [ ] Write a failing test proving a User API resource rejection marks the attachment failed/body-unavailable with `resource_unavailable_under_user_identity` and still creates analysis work for the text.
- [ ] Write a success-path test using a permitted user resource response and the existing private-file/extraction pipeline.
- [ ] Implement a User client binary-resource attempt without logging response bodies or bearer values; use a dedicated personal attachment service, not the App credential client.
- [ ] Ensure `FeishuMessageAttachmentsPending` is actively handled for personal messages and always converges to extraction or analysis fallback.
- [ ] Render “附件已检测 / 正文暂不可读取 / 文件名 / 类型 / 大小” and the stable reason in the existing message detail UI.

### Task 4: Thread replies, source provenance, and official-over-local idempotency

**Files:**
- Modify: `apps/backend/src/legal_workbench/integrations/feishu_user_client.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_personal_sync.py`
- Modify: `apps/backend/src/legal_workbench/integrations/feishu_events.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_handlers.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Create: `apps/backend/migrations/versions/20260808_0016_feishu_real_closure.py`
- Modify: `apps/backend/tests/test_feishu_personal_sync.py`
- Modify: `apps/backend/tests/test_feishu_event_sources.py`
- Add/Modify PostgreSQL ingestion tests.

- [ ] Write a failing test proving each distinct discovered `thread_id` is paginated with `container_id_type=thread` and replies enter Unified Ingestion once.
- [ ] Write a failing API/local duplicate test: local first then official enriches provenance/source; official first then local cannot overwrite content.
- [ ] Add `source_channel`, provenance, and content hash facts without changing the tenant/message unique identity.
- [ ] Implement thread pagination and source-priority merge rules in the ingestion handler.
- [ ] Run thread, ingestion, event-source, Outbox, and PostgreSQL idempotency tests.

### Task 5: Short-transaction sync lease and checkpoint fencing

**Files:**
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_personal_sync.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/migrations/versions/20260808_0016_feishu_real_closure.py`
- Modify: `apps/backend/tests/test_feishu_personal_sync.py`
- Create/Modify: PostgreSQL sync lease tests.

- [ ] Write failing tests for one-owner lease, expired-lease recovery, no UoW open during HTTP, per-page ingestion outside checkpoint transaction, and stale-owner checkpoint CAS rejection.
- [ ] Add lease owner, expiry, fencing version, and claimed end watermark to `FeishuSyncCheckpoint`.
- [ ] Implement `claim -> commit`, external fetch/ingest, and fenced short `advance/fail -> commit` transitions.
- [ ] Preserve overlap replay and PostgreSQL message idempotency; never persist a transient remote page as Redis truth.
- [ ] Run unit and PostgreSQL lease/checkpoint recovery tests.

### Task 6: Crash-safe token generations

**Files:**
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_user_auth.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/secrets.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/__init__.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Modify: `apps/backend/migrations/versions/20260808_0016_feishu_real_closure.py`
- Modify: `apps/backend/tests/test_feishu_user_oauth.py`
- Create/Modify PostgreSQL concurrent refresh tests.

- [ ] Write failing tests for refresh single ownership, pre-created pending generation, crash after both new secret files but before DB activation, recovery adoption, and orphan cleanup.
- [ ] Store only generation/reference/status/lease metadata in PostgreSQL; token bodies remain atomic `0600` LocalSecretProvider files.
- [ ] Split refresh into short claim transaction, remote refresh, atomic generation secret write, short CAS activation, and best-effort retired/orphan cleanup.
- [ ] Recover a complete pending generation before attempting another refresh; reject stale owners and never use the same refresh generation concurrently.
- [ ] Run unit and PostgreSQL concurrency/crash-recovery tests and inspect tables/logs for token bodies.

### Task 7: Read-only LocalFeishuConnector and discovery artifact

**Files:**
- Create: `apps/backend/src/legal_workbench/integrations/feishu_local_connector.py`
- Create: `apps/backend/src/legal_workbench/application/feishu_local_sync.py`
- Create: `apps/backend/scripts/discover_local_feishu.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_scopes.py`
- Modify: `apps/backend/src/legal_workbench/config.py`
- Modify: `.env.example`
- Create: `apps/backend/tests/test_feishu_local_connector.py`
- Create: `apps/backend/tests/test_feishu_local_sync.py`
- Generate: `artifacts/feishu-local/discovery.json`

- [ ] Write failing synthetic-fixture tests proving excluded credential/browser stores are never opened or reported, files are opened read-only, encrypted/unknown databases are classified unsupported without bypass, and the report contains only safe path categories/schema/count/time metadata.
- [ ] Write failing normalized local message tests for stable `local:{account}:{chat}:{message}:{version-or-time}` event IDs, Unified Ingestion, unapproved P2P scope discovery, and API/local deduplication.
- [ ] Write a failing local attachment test proving a trusted message-resource index relation, SHA-256, private copy, and existing extraction Outbox; prove an unlinked cache file is refused.
- [ ] Implement an allowlisted macOS discovery inventory and parser registry. No known/readable schema means no message extraction.
- [ ] Run the connector against the current Mac. Record encrypted Feishu databases as an actual boundary; do not derive keys or inspect prohibited stores.

### Task 8: Capability runner, real OAuth/E2E, and release verification

**Files:**
- Modify: `apps/backend/src/legal_workbench/integrations/feishu_personal_capabilities.py`
- Modify: `apps/backend/tests/test_feishu_personal_capabilities.py`
- Modify: `artifacts/feishu-personal-sync/capability-validation.json`
- Update relevant API/design/handoff documentation.

- [ ] Expand the live runner to 13 capabilities, eliminate `not_executed`, and guarantee only `passed/failed/partial/unsupported` with sanitized reasons and optional `manual_validation_required` reason.
- [ ] Run OAuth+PKCE in the current logged-in browser, persist actual granted scopes, force one refresh rotation, and execute official probes with non-sensitive sample IDs.
- [ ] Allow/register one non-sensitive test scope, sync one real message into PostgreSQL, run MessageAnalysisPolicy and real ContextSnapshot; run real Codex/Candidate only if the configured runtime is genuinely authenticated.
- [ ] Sync one test message with a Feishu Docx link and verify the exact message-linked native segment is in ContextSnapshot.
- [ ] Run Alembic `upgrade head -> downgrade 0015 -> upgrade head` against an isolated test database.
- [ ] Run all required backend/frontend commands, targeted PostgreSQL/Redis reliability tests, and browser QA of changed pages.
- [ ] Update capability/discovery artifacts using actual attempts only; scan artifacts/git diff for credentials, cookies, personal message bodies, and unapproved attachments.
