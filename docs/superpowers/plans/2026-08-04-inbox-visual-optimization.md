# AI Inbox Visual Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`; execute this plan task-by-task and keep every production change behind a previously observed failing test.

**Goal:** Turn the current AI Inbox into an evidence-first, responsive human-confirmation workspace without adding unimplemented backend actions or weakening review gates.

**Architecture:** Keep the existing React stateful navigation and FastAPI client. Replace the all-expanded Candidate cards with a master-detail Inbox page that fetches analysis only for the selected Candidate, renders source evidence before AI inference, and opens a responsive confirmation Drawer only when the existing `confirm-create` contract is safe to use. Use Playwright route fixtures solely for UI-contract tests and browser QA.

**Tech Stack:** React 18, TypeScript, Vite, Ant Design 5, Playwright.

## Global Constraints

- Reuse Ant Design and the existing Legal Workbench tokens; add no UI framework.
- Do not modify backend state machines, sending, review gates, authentication, idempotency, or version checks.
- Only `create_matter` may enter the live confirmation flow; link/update/information-only/ignore/defer/merge remain disabled and explicitly labelled unavailable.
- Source evidence, AI suggestion, human input, and deterministic state must remain visually distinct.
- Validate exactly 1440×900, 1024×768, and 390×844 with no page-level horizontal overflow.
- Do not stage, commit, or overwrite unrelated working-tree changes.

---

### Task 1: Playwright Inbox Contract and Fixtures

**Files:**
- Create: `apps/web/e2e/inbox.spec.ts`
- Keep: `playwright.config.ts`

**Interfaces:**
- Consumes: current dashboard main action, `GET /api/v1/inbox/candidates`, `GET /api/v1/feishu/messages/:id/analysis`.
- Produces: deterministic route fixtures for create, link, missing-attachment, running, empty, loading, error, and forbidden states.

- [ ] Write a failing test that clicks “处理待确认消息” and expects the “待确认消息” heading plus a two-item queue.
- [ ] Write a failing test that switches the queue and expects the selected source message text, context coverage, AI suggestion and missing-information sections to change.
- [ ] Write a failing test that expects a non-`create_matter` Candidate to have no enabled create action and to expose disabled ignore/defer/link controls without sending requests.
- [ ] Write a failing test that opens the confirmation surface for the create Candidate, edits title/owner/risk/impact/priority/next action, verifies the impact preview, then cancels without calling `confirm-create`.
- [ ] Write failing tests for empty, delayed loading, list error, 403, detail error, missing attachment and running-analysis states.
- [ ] Write a failing three-viewport test for horizontal overflow, mobile list-to-detail navigation, 44px controls and absence of Ant Design `bordered` warnings.
- [ ] Run `npx playwright test apps/web/e2e/inbox.spec.ts --reporter=line` and record failures caused by the current UI, not fixture or selector errors.

### Task 2: Evidence-First Master–Detail State

**Files:**
- Modify: `apps/web/src/pages/InboxPage.tsx`
- Modify only if required: `apps/web/src/types/api.ts`

**Interfaces:**
- Consumes: `legalApi.listCandidates()`, `legalApi.getMessageAnalysis(messageId)`.
- Produces: selected Candidate state, per-selected-detail loading/error state, safe message text extraction, and mobile list/detail state.

- [ ] Replace eager analysis fetches for every Candidate with one selected-Candidate detail request.
- [ ] Render a compact queue item with suggested title, source/time when loaded, localized action, missing-information count and status.
- [ ] Render source message sender ID, time, type and readable content before any AI output.
- [ ] Render ContextSnapshot counts, IDs, truncation and attachment coverage without claiming attachment parsing.
- [ ] Keep list loading, empty, error and forbidden states distinct; keep detail loading/error local and disable confirmation while evidence is unavailable.
- [ ] Run the focused Inbox tests and make only the queue/evidence/state tests green.

### Task 3: AI Semantics and Human Decision Gate

**Files:**
- Modify: `apps/web/src/pages/InboxPage.tsx`
- Modify: `apps/web/src/services/apiLabels.ts`

**Interfaces:**
- Consumes: Candidate recommended action, MessageJudgementResult and AgentRun status.
- Produces: localized AI section, explicit uncertainty/material gaps and a deterministic `canConfirmCreate` decision.

- [ ] Add Chinese labels for recommendation, message role and legal relevance enums.
- [ ] Rename Agent `confirmedFacts` display to “消息中明确陈述（待法务确认）”; keep inferred facts visibly labelled AI inference.
- [ ] Replace the circular confidence chart with low-weight text metadata.
- [ ] Disable formal confirmation when action is not `create_matter`, detail is unavailable, Candidate is not pending, or analysis is queued/preparing/running/validating.
- [ ] Show disabled ignore, defer, link/update and merge actions with “后端流程未接入，不会执行”.
- [ ] Ensure retry analysis freezes the current confirmation path until fresh detail is loaded.
- [ ] Run the focused gate tests until green.

### Task 4: Responsive Confirmation Drawer

**Files:**
- Modify: `apps/web/src/pages/InboxPage.tsx`
- Modify: `apps/web/src/styles/global.css`

**Interfaces:**
- Consumes: existing `ConfirmCandidateInput` and `legalApi.confirmCandidate`.
- Produces: responsive edit Drawer that retains source context and maps `plannedCompleteAt` to the first WorkItem.

- [ ] Replace the 760px Modal with a right Drawer on desktop/tablet and full-width Drawer on mobile.
- [ ] Keep source-message summary, Candidate version and AI-source labels visible above the form.
- [ ] Prefill only AI-backed title/category/background; require explicit owner, risk, impact, priority and next action input.
- [ ] Add planned completion time to the first WorkItem payload without claiming a standalone Deadline is created.
- [ ] Show an exact impact preview: one Matter and one WorkItem are created atomically; no message is sent and later outbound review is unchanged.
- [ ] Use `Card variant="borderless"`; remove all Inbox use of deprecated `bordered`.
- [ ] Run the form and console-warning tests until green.

### Task 5: Responsive Styling and Full Verification

**Files:**
- Modify: `apps/web/src/styles/global.css`
- Verify: `apps/web/e2e/dashboard.spec.ts`
- Verify: `apps/web/e2e/inbox.spec.ts`

**Interfaces:**
- Consumes: Inbox semantic class names from Tasks 2–4.
- Produces: 1440 desktop, 1024 compact desktop and 390 mobile layouts consistent with the dashboard.

- [ ] Implement approximately 300px/250px queue columns for 1440/1024 and a single-surface detail area.
- [ ] At 390, show the queue first, then a full-width detail view with a 44px back control and no clipped actions.
- [ ] Reuse `#315f8f`, `#17243a`, `#657083`, `#d8dee8`, 6px radius and 4/8/12/16/24 spacing.
- [ ] Run `npx playwright test apps/web/e2e/dashboard.spec.ts apps/web/e2e/inbox.spec.ts --reporter=line`.
- [ ] Run `npm run typecheck`, `npm run build`, and `git diff --check`.
- [ ] Report any unavailable lint/test scripts and the existing Vite chunk warning accurately; do not claim browser visual completion before independent Playwright MCP QA.
