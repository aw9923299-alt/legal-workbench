# Feishu Personal Message and Document Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only Feishu user OAuth, durable personal message synchronization, scoped discovery, native document ingestion, and deterministic analysis gating without changing the existing Bot ingestion or human-review boundaries.

**Architecture:** Keep Bot/App delivery unchanged and add a User control/data plane beside it. User history is normalized into the existing `IngestFeishuEventHandler`; PostgreSQL owns authorizations, scopes, checkpoints, documents, audit, and Outbox facts, while versioned token files under `LocalSecretProvider` are atomically switched by PostgreSQL metadata after a refresh lease. Native Feishu documents use dedicated source/version records and generalized controlled segments, and only deterministic `MessageAnalysisPolicy` decisions create analysis Outbox work.

**Tech Stack:** Python 3.12+; FastAPI; Pydantic; SQLAlchemy 2 async; PostgreSQL 18; Alembic; Celery/Redis; HTTPX; React 18; TypeScript; TanStack Query; Ant Design; Vitest; Playwright MCP.

## Global Constraints

- Preserve existing App/Bot ingestion and add read-only User OAuth; do not implement `send_as_user`.
- User API messages must enter `UserMessageAdapter -> IngestFeishuEventHandler`; never insert `FeishuMessage` directly.
- PostgreSQL remains the only business fact store; Redis is queue and coordination only.
- `user_access_token` and `refresh_token` may exist only in `LocalSecretProvider`; never PostgreSQL text/JSON, Redis, frontend, logs, audit payloads, or Codex inputs.
- Refresh is single-owner across processes and rotates access/refresh references atomically after external I/O.
- Codex does not call Feishu or read the secret root; all external communications retain the existing review gate.
- Phase 0 credential-backed checks are reported as `not_executed` when credentials/authorization/sample IDs are absent.
- New groups and P2P chats default to `unapproved/disabled`; P2P backfill is explicitly bounded.
- Do not use packet capture, local Feishu cache parsing, hooks, or UI automation as an integration mechanism.
- Reuse Ant Design, existing project tokens, routing, query state, API clients, and responsive collection patterns.

---

### Task 1: Capability validation contract and persistence foundation

**Files:**
- Create: `apps/backend/src/legal_workbench/application/feishu_capabilities.py`
- Create: `apps/backend/scripts/verify_feishu_personal_capabilities.py`
- Create: `apps/backend/tests/test_feishu_capabilities.py`
- Modify: `apps/backend/src/legal_workbench/domain/enums.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/__init__.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Create: `apps/backend/migrations/versions/20260808_0013_add_feishu_user_authorizations.py`
- Create: `apps/backend/tests/test_sqlalchemy_feishu_user_models.py`

**Interfaces:**
- Produces: `FeishuUserAuthorization`, `FeishuOAuthAttempt`, `FeishuCapabilityResult`, repository methods for authorization/OAuth attempts, and a JSON validation report whose unrun rows have `status="not_executed"`.

- [ ] **Step 1: Write failing model and capability-entry tests**

```python
def test_missing_real_configuration_marks_every_capability_not_executed(tmp_path):
    report = build_not_executed_report(reason="missing_credentials")
    assert {row.status for row in report.results} == {"not_executed"}
    assert "token" not in report.model_dump_json().lower()

def test_authorization_table_contains_refs_not_token_columns():
    table = Base.metadata.tables["feishu_user_authorizations"]
    assert {"access_token_ref", "refresh_token_ref", "refresh_claim_id"} <= set(table.columns)
    assert "access_token" not in table.columns and "refresh_token" not in table.columns
```

- [ ] **Step 2: Run the tests and confirm missing symbols/tables fail**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_capabilities.py apps/backend/tests/test_sqlalchemy_feishu_user_models.py -q`

- [ ] **Step 3: Add focused entities, mappings, repositories, UoW ports, and the `0013` reversible migration**

```python
@dataclass(slots=True)
class FeishuUserAuthorization:
    id: UUID
    user_open_id: str
    tenant_key: str
    granted_scopes: list[str]
    access_token_ref: str
    refresh_token_ref: str
    access_expires_at: datetime
    refresh_expires_at: datetime | None
    token_version: int
    status: FeishuAuthorizationStatus
    refresh_claim_id: UUID | None = None
    refresh_claimed_until: datetime | None = None
```

- [ ] **Step 4: Add and run the credential-free capability CLI**

Run: `.venv/bin/python apps/backend/scripts/verify_feishu_personal_capabilities.py --output artifacts/feishu-personal-sync/capability-validation.json`

Expected: exit 0; all eleven rows are `not_executed`; output contains no secret/token value.

### Task 2: OAuth PKCE, secure token storage, and concurrent refresh rotation

**Files:**
- Create: `apps/backend/src/legal_workbench/integrations/feishu_oauth.py`
- Create: `apps/backend/src/legal_workbench/application/feishu_user_authorization.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/secrets.py`
- Modify: `apps/backend/src/legal_workbench/config.py`
- Create: `apps/backend/tests/test_feishu_user_authorization.py`
- Create: `apps/backend/tests/test_postgres_feishu_token_refresh.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `FeishuOAuthClient.exchange_code`, `FeishuOAuthClient.refresh`, `FeishuUserAuthorizationService.begin`, `.complete`, `.revoke`, and `UserTokenProvider.get_access_token(authorization_id)`.
- Consumes: Task 1 authorization/OAuth repositories.

- [ ] **Step 1: Write failing PKCE, secret-permission, redaction, and refresh-race tests**

```python
def test_pkce_uses_s256():
    request = create_pkce_request()
    assert request.challenge_method == "S256"
    assert request.challenge == b64url(sha256(request.verifier.encode()).digest())

@pytest.mark.asyncio
async def test_concurrent_refresh_calls_remote_once(provider, oauth):
    tokens = await asyncio.gather(*(provider.get_access_token(AUTH_ID) for _ in range(8)))
    assert len(set(tokens)) == 1
    assert oauth.refresh_calls == 1
```

- [ ] **Step 2: Run and observe failures for missing OAuth/provider behavior**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_user_authorization.py apps/backend/tests/test_postgres_feishu_token_refresh.py -q`

- [ ] **Step 3: Implement short DB refresh leases and versioned secret references**

```text
lock authorization -> claim UUID + expiry -> commit
read old refresh secret -> remote refresh outside transaction
write access_vN and refresh_vN files -> lock authorization
verify claim/version -> switch both refs + expiries + version -> commit
delete old versioned files
```

- [ ] **Step 4: Re-run tests and scan persisted/loggable objects for token values**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_user_authorization.py apps/backend/tests/test_postgres_feishu_token_refresh.py apps/backend/tests/test_setup_status.py -q`

### Task 3: User API client, unified message adapter, checkpoint, and recovery

**Files:**
- Create: `apps/backend/src/legal_workbench/integrations/feishu_user_client.py`
- Create: `apps/backend/src/legal_workbench/integrations/feishu_user_sync.py`
- Create: `apps/backend/src/legal_workbench/application/feishu_personal_sync.py`
- Modify: `apps/backend/src/legal_workbench/integrations/feishu_events.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_handlers.py`
- Modify: `apps/backend/src/legal_workbench/config.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Create: `apps/backend/migrations/versions/20260808_0014_add_feishu_sync_checkpoints.py`
- Create: `apps/backend/tests/test_feishu_personal_sync.py`
- Create: `apps/backend/tests/test_postgres_feishu_personal_sync.py`

**Interfaces:**
- Produces: `UserMessageAdapter.to_event`, `FeishuPersonalSyncService.sync_scope`, `FeishuSyncCheckpoint`, and `FeishuUserSyncRunner.run_once`.
- Consumes: Task 2 `UserTokenProvider` and existing `IngestFeishuEventHandler`.

- [ ] **Step 1: Write failing stable-ID, unified-ingestion, overlap, duplicate, checkpoint, and partial-failure tests**

```python
def test_user_history_event_id_is_stable():
    assert adapter.to_event(item).event_id == "uat:tenant-a:om-1:1785596460000"

@pytest.mark.asyncio
async def test_resume_uses_five_minute_overlap_and_advances_only_after_ingest(service):
    result = await service.sync_scope(scope_id=SCOPE_ID)
    assert result.requested_start == CHECKPOINT_TIME - timedelta(minutes=5)
    assert result.checkpoint.last_message_id == "om-last"
```

- [ ] **Step 2: Verify red failures**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_personal_sync.py apps/backend/tests/test_postgres_feishu_personal_sync.py -q`

- [ ] **Step 3: Implement paginated user reads and adapter-only ingestion**

```python
result = await IngestFeishuEventHandler(self._uow_factory).execute(
    adapter.to_command(item, authorization=authorization, scope=scope)
)
```

- [ ] **Step 4: Verify duplicate sync creates one message/version-trigger set and restart resumes from PostgreSQL**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_personal_sync.py apps/backend/tests/test_postgres_feishu_personal_sync.py apps/backend/tests/test_feishu_ingestion_completion.py -q`

### Task 4: Discovery, typed scopes, backfill bounds, and per-scope controls

**Files:**
- Modify: `apps/backend/src/legal_workbench/domain/enums.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_scopes.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/migrations/versions/20260808_0014_add_feishu_sync_checkpoints.py`
- Modify: `apps/backend/tests/test_feishu_scopes.py`
- Modify: `apps/backend/tests/test_postgres_feishu_scopes.py`

**Interfaces:**
- Produces: `IntegrationScopeType.P2P/GROUP`, `backfill_days`, `high_value`, `discovery_source`, and `FeishuPersonalSyncService.discover`.
- Consumes: Task 3 user client and sync service.

- [ ] **Step 1: Write failing discovery-default and bounded-P2P tests**

```python
assert discovered_group.status == IntegrationScopeStatus.UNAPPROVED
assert discovered_group.sync_mode == IntegrationSyncMode.DISABLED
with pytest.raises(DomainValidationError):
    await service.register_known_chat(scope_type="p2p", backfill_days=None, ...)
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_scopes.py apps/backend/tests/test_postgres_feishu_scopes.py -q`

- [ ] **Step 3: Implement discovery upsert and Allow/Exclude/Pause/Resume with optimistic versioning**

```text
GET /im/v1/chats with user token -> group scope upsert -> unapproved/disabled
known P2P registration -> required 7/30/90-day backfill -> unapproved/disabled
```

- [ ] **Step 4: Re-run scope and sync tests**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_scopes.py apps/backend/tests/test_postgres_feishu_scopes.py apps/backend/tests/test_feishu_personal_sync.py -q`

### Task 5: Native Feishu document search, links, folder subscriptions, and controlled segments

**Files:**
- Create: `apps/backend/src/legal_workbench/application/feishu_documents.py`
- Modify: `apps/backend/src/legal_workbench/integrations/feishu_user_client.py`
- Modify: `apps/backend/src/legal_workbench/application/context_snapshots.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/src/legal_workbench/application/ports.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/repositories.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/unit_of_work.py`
- Create: `apps/backend/migrations/versions/20260808_0015_add_feishu_documents.py`
- Create: `apps/backend/tests/test_feishu_documents.py`
- Create: `apps/backend/tests/test_postgres_feishu_documents.py`

**Interfaces:**
- Produces: `extract_feishu_document_links`, `FeishuDocumentService.search/import_document/sync_folder`, message-document provenance, native document versions, folder subscriptions, and generalized `document_segments` rows.
- Consumes: Task 3 user client and existing ContextSnapshot truncation policies.

- [ ] **Step 1: Write failing link, idempotent import, Markdown segment, permission-loss, and folder-bound tests**

```python
assert extract_feishu_document_links("https://acme.feishu.cn/docx/DocToken") == [
    FeishuDocumentRef(token="DocToken", document_type="docx")
]
assert second_import.version_id == first_import.version_id
assert all(segment.content_hash == sha256(segment.content.encode()).hexdigest() for segment in segments)
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_documents.py apps/backend/tests/test_postgres_feishu_documents.py -q`

- [ ] **Step 3: Implement network-outside-transaction fetch and transactionally persisted versions/segments/audit**

```text
resolve requested token -> fetch Markdown with UAT outside transaction
hash Markdown -> lock document identity -> add version and segments if new
link source message -> AuditEvent -> commit
```

- [ ] **Step 4: Verify ContextSnapshot includes only linked, bounded native segments**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_documents.py apps/backend/tests/test_context_snapshot_builder.py apps/backend/tests/test_postgres_feishu_documents.py -q`

### Task 6: Deterministic collection-versus-analysis policy and attachment degradation

**Files:**
- Create: `apps/backend/src/legal_workbench/application/message_analysis_policy.py`
- Modify: `apps/backend/src/legal_workbench/integrations/feishu_events.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_handlers.py`
- Modify: `apps/backend/src/legal_workbench/application/document_extraction.py`
- Modify: `apps/backend/src/legal_workbench/application/feishu_operations.py`
- Modify: `apps/backend/src/legal_workbench/domain/entities.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/models/core.py`
- Modify: `apps/backend/migrations/versions/20260808_0014_add_feishu_sync_checkpoints.py`
- Create: `apps/backend/tests/test_message_analysis_policy.py`
- Modify: `apps/backend/tests/test_feishu_ingestion_completion.py`
- Modify: `apps/backend/tests/test_attachment_download_pipeline.py`

**Interfaces:**
- Produces: `MessageAnalysisDecision(disposition, reason)` with p2p/mention/reply/high-value/task-deadline rules and `store_only` for ordinary group/system/greeting messages.

- [ ] **Step 1: Write a literal decision table and Outbox behavior tests**

```python
@pytest.mark.parametrize(("case", "expected"), [
    (p2p_task, "analyze"),
    (group_mention_self, "analyze"),
    (group_deadline, "analyze"),
    (ordinary_group, "store_only"),
    (p2p_greeting, "store_only"),
])
def test_policy(case, expected):
    assert policy.decide(case).disposition == expected
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_message_analysis_policy.py apps/backend/tests/test_feishu_ingestion_completion.py apps/backend/tests/test_attachment_download_pipeline.py -q`

- [ ] **Step 3: Persist policy decision and create analysis Outbox only for `analyze`**

```text
unsupported -> persist unsupported, no analysis
user attachment without proven official path -> metadata + not_requested + resource_unavailable_under_user_identity
store_only -> message status received, no analysis/download Outbox
analyze -> existing attachment/download/analysis chain
```

- [ ] **Step 4: Re-run policy, ingestion, extraction, and Outbox tests**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_message_analysis_policy.py apps/backend/tests/test_feishu_ingestion_completion.py apps/backend/tests/test_attachment_download_pipeline.py apps/backend/tests/test_document_extraction.py apps/backend/tests/test_security_and_outbox.py -q`

### Task 7: FastAPI control plane, Setup/SSE projection, workers, and process wiring

**Files:**
- Create: `apps/backend/src/legal_workbench/api/routes/feishu_user.py`
- Create: `apps/backend/src/legal_workbench/api/routes/feishu_documents.py`
- Create: `apps/backend/src/legal_workbench/api/schemas/feishu_user.py`
- Create: `apps/backend/src/legal_workbench/api/schemas/feishu_documents.py`
- Modify: `apps/backend/src/legal_workbench/api/router.py`
- Modify: `apps/backend/src/legal_workbench/application/setup.py`
- Modify: `apps/backend/src/legal_workbench/api/schemas/setup.py`
- Modify: `apps/backend/src/legal_workbench/api/routes/events.py`
- Modify: `apps/backend/src/legal_workbench/workers/tasks.py`
- Modify: `apps/backend/src/legal_workbench/infrastructure/outbox.py`
- Modify: `compose.yml`
- Create: `apps/backend/tests/test_feishu_user_api.py`
- Modify: `apps/backend/tests/test_setup_status.py`
- Modify: `apps/backend/tests/test_security_and_outbox.py`

**Interfaces:**
- Produces: `/api/v1/integrations/feishu-user/*`, document endpoints, setup personal-identity projection, `feishu-user.updated` invalidation, explicit sync/discovery Outbox handlers, and an optional `feishu-user-sync` integrations-profile process.

- [ ] **Step 1: Write failing OpenAPI/auth/idempotency/no-token-response and SSE invalidation tests**

```python
assert "/api/v1/integrations/feishu-user/authorize" in app.openapi()["paths"]
assert "accessToken" not in json.dumps(status_response.json()).lower()
assert unauthenticated_sync.status_code == 401
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_user_api.py apps/backend/tests/test_setup_status.py apps/backend/tests/test_security_and_outbox.py -q`

- [ ] **Step 3: Implement thin routes and deterministic worker/process dispatch**

```text
FastAPI: authorize/callback/status/revoke/discover/sync/search/import/subscribe
Worker/process: no request-thread polling; per-scope exceptions become durable partial status
API responses: IDs, timestamps, status, error code, correlation ID only
```

- [ ] **Step 4: Re-run API/setup/outbox tests**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_user_api.py apps/backend/tests/test_setup_status.py apps/backend/tests/test_security_and_outbox.py -q`

### Task 8: Feishu data-source UI with Figma and rendered browser evidence

**Files:**
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/services/api.ts`
- Modify: `apps/web/src/services/RealtimeProvider.tsx`
- Modify: `apps/web/src/pages/SetupPage.tsx`
- Modify: `apps/web/src/pages/SetupPage.test.tsx`
- Modify: `apps/web/src/pages/FeishuScopesPage.tsx`
- Modify: `apps/web/src/pages/FeishuScopesPage.test.tsx`
- Modify: `apps/web/src/styles/global.css`
- Create: `docs/ui-upgrade/06-feishu-personal-sync-functional-qa.md`
- Create: `artifacts/ui-upgrade/before/feishu-scopes-{1440,1024,390}.png`
- Create: `artifacts/ui-upgrade/after/feishu-scopes-{1440,1024,390}.png`

**Interfaces:**
- Consumes: Task 7 REST/SSE contracts.
- Produces: personal account, chat scopes, cloud documents, sync status, and advanced known-chat registration areas with explicit verified/not-executed language.

- [ ] **Step 1: Use Figma/Playwright to capture the current page and map existing Ant tokens/components**

```text
Route: /settings/feishu-scopes
Viewports: 1440x900, 1024x768, 390x844
Evidence: navigation, loading/error/empty state, existing table overflow, console/network facts
```

- [ ] **Step 2: Write failing component tests for account status, typed scope/backfill, search/import, folder subscribe, and secret-free responses**

Run: `npm run test --workspace @legal-workbench/web -- FeishuScopesPage.test.tsx SetupPage.test.tsx`

- [ ] **Step 3: Implement with existing Ant Design and responsive list/card patterns**

```text
No new UI framework; no green for unverified status; actions require real API calls;
known chat ID stays in Advanced; mobile controls retain 44px targets and no page overflow.
```

- [ ] **Step 4: Run frontend tests/typecheck/build and capture after evidence at all three viewports**

Run: `npm run test --workspace @legal-workbench/web -- FeishuScopesPage.test.tsx SetupPage.test.tsx`

Run: `npm run typecheck && npm run build`

### Task 9: Reliability, migration round-trip, security audit, and documentation

**Files:**
- Create: `apps/backend/tests/test_feishu_personal_reliability.py`
- Modify: `apps/backend/tests/test_postgres_redis_flush_recovery.py`
- Modify: `docs/design/SYSTEM_DESIGN.md`
- Modify: `docs/design/DATA_MODEL.md`
- Modify: `docs/design/API_CONTRACTS.md`
- Modify: `docs/design/DEPLOYMENT.md`
- Modify: `docs/CODEX_HANDOFF.md`
- Modify: `README.md`

**Interfaces:**
- Produces: explicit acceptance matrix for sleep/wake, offline, 429, permission revoke, expired token, Redis flush, PostgreSQL restart, document permission change, and per-scope isolation.

- [ ] **Step 1: Write failing deterministic reliability tests**

```python
@pytest.mark.parametrize("failure", ["offline", "rate_limited", "permission_revoked"])
async def test_one_scope_failure_does_not_stop_other_scopes(sync_runner, failure):
    result = await sync_runner.run_once()
    assert result.successful_scopes == 1
    assert result.failed_scopes == 1
```

- [ ] **Step 2: Run targeted reliability tests and implement bounded backoff/error classification**

Run: `.venv/bin/python -m pytest apps/backend/tests/test_feishu_personal_reliability.py apps/backend/tests/test_postgres_redis_flush_recovery.py -q`

- [ ] **Step 3: Run Alembic upgrade/downgrade/upgrade against a dedicated test database**

```bash
LEGAL_WORKBENCH_DATABASE_URL="$LEGAL_WORKBENCH_TEST_DATABASE_URL" .venv/bin/alembic -c apps/backend/alembic.ini upgrade head
LEGAL_WORKBENCH_DATABASE_URL="$LEGAL_WORKBENCH_TEST_DATABASE_URL" .venv/bin/alembic -c apps/backend/alembic.ini downgrade 20260803_0012
LEGAL_WORKBENCH_DATABASE_URL="$LEGAL_WORKBENCH_TEST_DATABASE_URL" .venv/bin/alembic -c apps/backend/alembic.ini upgrade head
```

- [ ] **Step 4: Run full verification and inspect diff for secret strings or alternate send paths**

Run: `.venv/bin/python -m ruff check apps/backend/src apps/backend/tests`

Run: `.venv/bin/python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src`

Run: `.venv/bin/python -m pytest apps/backend/tests`

Run: `npm run typecheck`

Run: `npm run build`

Run: `git diff --check && rg -n "user_access_token|refresh_token" apps/backend/src apps/web/src`

Expected: checks exit 0; token terms appear only in OAuth/secret-reference code and never in API response models, audit payloads, logs, Codex runtime input, or frontend persistence.
