import { expect, test, type Page, type Route } from '@playwright/test';
import type { AgentRunRecord, ReviewPackage, ReviewRecord } from '../src/types/api';

// Deterministic UI-contract fixtures only. These do not prove live authentication,
// Codex execution, legal approval, Feishu delivery, or any external send result.
const pendingReview: ReviewPackage = {
  id: 'review-pending',
  matterId: 'matter-contract',
  workItemId: 'work-contract',
  packageType: 'external_communication',
  status: 'pending_review',
  title: '直播合作合同回复审核',
  background: '业务拟向合作方回复退款与结算安排。',
  confirmedFacts: [{ fact: '合同约定按月结算' }],
  unconfirmedFacts: [{ fact: '合作方可能接受分期退款' }],
  reasoning: '先确认退款触发条件，再对外说明处理方案。',
  risks: [{ risk: '未确认金额前承诺可能扩大责任' }],
  alternatives: [{ option: '先发送材料补充清单' }],
  citations: [{ source: '合作协议第 8 条' }],
  proposedContent: '建议回复：收到材料后两个工作日内复核退款安排。',
  target: { replyToMessageId: 'om-origin-pending', messageType: 'text' },
  createdBy: 'ui-contract-reviewer',
  submittedAt: '2026-08-04T10:00:00+08:00',
  approvedContentHash: null,
  version: 3,
};

const approvedReview: ReviewPackage = {
  ...pendingReview,
  id: 'review-approved',
  title: '已批准的合同回复',
  status: 'approved',
  submittedAt: '2026-08-04T09:00:00+08:00',
  approvedContentHash: 'sha256-approved-content',
  target: { receiveId: 'ou_partner', receiveIdType: 'open_id', messageType: 'text' },
  version: 4,
};

const unknownTargetReview: ReviewPackage = {
  ...pendingReview,
  id: 'review-unknown-target',
  title: '目标待核验的审核包',
  target: { destination: 'unrecognized', messageType: 'text' },
};

const reviewMatter = {
  id: 'matter-contract',
  matterNumber: 'LW-2026-CONTRACT',
  title: '直播合作合同审查',
  primaryCategory: 'contract',
  secondaryCategories: [],
  lifecycleStatus: 'open',
  workStatus: 'in_progress',
  ownerId: 'ui-contract-reviewer',
  collaboratorIds: [],
  requesterIds: [],
  entityIds: [],
  legalRisk: 'high',
  businessImpact: 'project',
  confidentiality: 'internal',
  summary: '审核包关联事项。',
  objective: '完成外发审核。',
  currentStage: 'review',
  version: 1,
  openedAt: '2026-08-04T08:00:00+08:00',
  resolvedAt: null,
  closedAt: null,
  reopenedAt: null,
};

const approvedRecord: ReviewRecord = {
  id: 'record-approved',
  reviewPackageId: approvedReview.id,
  reviewerId: 'ui-contract-reviewer',
  decision: 'approved_with_edits',
  comments: '已收窄退款承诺范围。',
  finalContent: '最终正文：收到完整材料后两个工作日内完成复核并另行反馈。',
  finalContentHash: 'sha256-approved-content',
  changeSummary: [{ field: '退款承诺', change: '改为材料齐备后复核' }],
  reusableAsExample: false,
  reviewedAt: '2026-08-04T09:30:00+08:00',
};

const olderApprovedRecord: ReviewRecord = {
  ...approvedRecord,
  id: 'record-approved-older',
  decision: 'rejected',
  comments: '旧审核意见：不应再作为当前决定展示。',
  finalContent: '旧审核正文：此内容已经被后续审核决定替代。',
  finalContentHash: 'sha256-old-content',
  reviewedAt: '2026-08-03T09:30:00+08:00',
};

function runFixture(id: string, status: AgentRunRecord['status']): AgentRunRecord {
  const completed = status === 'completed';
  return {
    id,
    agentKey: 'message_judgement',
    agentVersion: '1.0.0',
    feishuMessageId: completed ? 'om-completed' : 'om-failed',
    contextSnapshotId: completed ? 'snapshot-completed' : 'snapshot-failed',
    status,
    objective: '研判授权消息是否形成法务工作',
    inputPayload: { fixture: 'ui-contract-only' },
    outputPayload: completed ? {
      suggestedTitle: '直播宣传文案复核',
      evidence: 'x'.repeat(480),
      conclusion: '仅为 Agent 结构化输出，仍需法务人工确认',
    } : null,
    rawStdout: null,
    rawStderr: null,
    promptSnapshot: 'UI contract fixture prompt',
    workingDirectory: '/tmp/ui-contract-fixture',
    startedAt: '2026-08-04T09:01:00+08:00',
    heartbeatAt: '2026-08-04T09:01:05+08:00',
    finishedAt: completed ? '2026-08-04T09:01:10+08:00' : '2026-08-04T09:01:08+08:00',
    timeoutAt: '2026-08-04T09:06:00+08:00',
    attemptNumber: 1,
    maxAttempts: 3,
    failureCode: completed ? null : 'runtime_exit_nonzero',
    failureMessage: completed ? null : 'UI 合约夹具：受控运行失败',
    correlationId: `corr-${id}`,
    createdBy: 'ui-contract-fixture',
    createdAt: '2026-08-04T09:00:58+08:00',
    updatedAt: '2026-08-04T09:01:10+08:00',
    version: 2,
    sources: [{
      sourceType: 'feishu_message',
      sourceId: completed ? 'om-completed' : 'om-failed',
      sourceVersion: '1',
      sourceHash: `sha256-${id}`,
      displayName: '授权飞书消息',
      citationMetadata: { fixture: 'ui-contract-only' },
    }],
  };
}

const completedRun = runFixture('run-completed', 'completed');
const failedRun = runFixture('run-failed', 'failed');
const unexpectedRequests = new WeakMap<Page, string[]>();

type ContractOptions = {
  reviewWriteDelayMs?: number;
  reviewWriteError?: boolean;
  queueDelayMs?: number;
  reviewListStatus?: 401 | 403 | 409;
  agentListStatus?: 401 | 403 | 409;
};

type ContractState = {
  reviewWrites: Array<Record<string, unknown>>;
  queueWrites: number;
  unexpected: string[];
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers: { 'X-UI-Contract-Fixture': 'true' },
    body: JSON.stringify(body),
  });
}

async function rejectUnexpected(page: Page, route: Route) {
  const request = route.request();
  const url = new URL(request.url());
  const entry = `${request.method()} ${url.pathname}${url.search}`;
  unexpectedRequests.get(page)?.push(entry);
  await fulfillJson(route, { detail: `unexpected UI-contract fixture request: ${entry}` }, 501);
}

async function installContract(page: Page, options: ContractOptions = {}): Promise<ContractState> {
  const unexpected: string[] = [];
  unexpectedRequests.set(page, unexpected);
  const state: ContractState = { reviewWrites: [], queueWrites: 0, unexpected };
  let packages: ReviewPackage[] = [pendingReview, approvedReview, unknownTargetReview];

  await page.route('**/api/v1/**', (route) => rejectUnexpected(page, route));
  await page.route('**/api/v1/auth/session', (route) => {
    if (route.request().method() !== 'GET') return rejectUnexpected(page, route);
    return fulfillJson(route, { actorId: 'ui-contract-reviewer' });
  });
  await page.route(/\/api\/v1\/reviews\/packages\?/, (route) => {
    if (route.request().method() !== 'GET') return rejectUnexpected(page, route);
    if (options.reviewListStatus) return fulfillJson(route, { detail: `UI 合约夹具：审核列表 ${options.reviewListStatus}` }, options.reviewListStatus);
    return fulfillJson(route, packages);
  });

  for (const reviewPackage of [pendingReview, approvedReview, unknownTargetReview]) {
    await page.route(`**/api/v1/reviews/packages/${reviewPackage.id}`, (route) => {
      if (route.request().method() !== 'GET') return rejectUnexpected(page, route);
      return fulfillJson(route, packages.find((item) => item.id === reviewPackage.id) ?? reviewPackage);
    });
    await page.route(`**/api/v1/reviews/packages/${reviewPackage.id}/records`, async (route) => {
      if (route.request().method() === 'GET') {
        return fulfillJson(route, reviewPackage.id === approvedReview.id ? [approvedRecord, olderApprovedRecord] : []);
      }
      if (route.request().method() !== 'POST') return rejectUnexpected(page, route);
      state.reviewWrites.push(route.request().postDataJSON() as Record<string, unknown>);
      if (options.reviewWriteDelayMs) await new Promise((resolve) => setTimeout(resolve, options.reviewWriteDelayMs));
      if (options.reviewWriteError) return fulfillJson(route, { detail: 'UI 合约夹具：审核提交失败' }, 503);
      packages = packages.map((item) => item.id === reviewPackage.id ? { ...item, status: 'approved' } : item);
      return fulfillJson(route, { reviewPackageId: reviewPackage.id, reviewRecordId: 'record-created', status: 'approved' });
    });
    await page.route(`**/api/v1/reviews/packages/${reviewPackage.id}/communications`, async (route) => {
      if (route.request().method() !== 'POST') return rejectUnexpected(page, route);
      state.queueWrites += 1;
      if (options.queueDelayMs) await new Promise((resolve) => setTimeout(resolve, options.queueDelayMs));
      return fulfillJson(route, { communicationId: 'communication-queued', status: 'queued' });
    });
  }

  await page.route(/\/api\/v1\/agent-runs\?/, (route) => {
    if (route.request().method() !== 'GET') return rejectUnexpected(page, route);
    if (options.agentListStatus) return fulfillJson(route, { detail: `UI 合约夹具：执行记录 ${options.agentListStatus}` }, options.agentListStatus);
    return fulfillJson(route, [completedRun, failedRun]);
  });
  for (const run of [completedRun, failedRun]) {
    await page.route(`**/api/v1/agent-runs/${run.id}`, (route) => {
      if (route.request().method() !== 'GET') return rejectUnexpected(page, route);
      return fulfillJson(route, run);
    });
  }
  await page.route('**/api/v1/matters/matter-contract', (route) => fulfillJson(route, reviewMatter));
  await page.route('**/api/v1/matters/matter-contract/work-items', (route) => fulfillJson(route, []));
  return state;
}

test.afterEach(async ({ page }) => {
  expect(unexpectedRequests.get(page) ?? []).toEqual([]);
});

test('review queue is full-width and exposes a truthful approved-only communication gate', async ({ page }) => {
  await installContract(page);
  await page.goto('/reviews');

  await expect(page.getByRole('heading', { name: '审核中心' })).toBeVisible();
  const table = page.locator('.review-queue-table');
  await expect(table).toBeVisible();
  await expect(table.getByText('待审核（pending_review）', { exact: true }).first()).toBeVisible();
  await expect(table.getByText('已批准（approved）', { exact: true })).toBeVisible();
  await expect(table.getByRole('button', { name: '将直播合作合同回复审核进入外发队列' })).toBeDisabled();
  await expect(table.getByRole('button', { name: '将已批准的合同回复进入外发队列' })).toBeEnabled();
  await expect(table.getByRole('row').filter({ hasText: '直播合作合同回复审核' })).toContainText('回复原消息：om-origin-pending');
  await expect(table.getByRole('row').filter({ hasText: '已批准的合同回复' })).toContainText('收件人（open_id）：ou_partner');
  await expect(table.getByRole('row').filter({ hasText: '目标待核验的审核包' })).toContainText('无法识别目标');
  await expect(page.getByText('已发送', { exact: true })).toHaveCount(0);
});

test('review list distinguishes expired login, permission denial, and stale data without exposing queue summaries', async ({ browser }) => {
  for (const [status, variant, title] of [
    [401, 'permission', '登录状态已失效'],
    [403, 'permission', '无权访问审核数据'],
    [409, 'stale', '审核数据版本已变化'],
  ] as const) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await installContract(page, { reviewListStatus: status });
    await page.goto('/reviews');
    await expect(page.locator(`.state-panel--${variant}`)).toContainText(title);
    await expect(page.getByText(pendingReview.title, { exact: true })).toHaveCount(0);
    await context.close();
  }
});

test('review detail exposes the real target and unknown targets block approval', async ({ page }) => {
  await installContract(page);
  await page.goto('/reviews/review-pending');

  const replyDetail = page.getByRole('dialog', { name: '审核包详情' });
  await expect(replyDetail.getByRole('region', { name: '外发目标' })).toContainText('回复原消息：om-origin-pending');

  await page.goto('/reviews/review-approved');
  const receiveDetail = page.getByRole('dialog', { name: '审核包详情' });
  await expect(receiveDetail.getByRole('region', { name: '外发目标' })).toContainText('收件人（open_id）：ou_partner');

  await page.goto('/reviews/review-unknown-target');
  const unknownDetail = page.getByRole('dialog', { name: '审核包详情' });
  await expect(unknownDetail.getByRole('region', { name: '外发目标' })).toContainText('无法识别目标');
  await expect(unknownDetail.getByRole('region', { name: '外发目标' }).getByText('无法核验真实外发目标，不能批准')).toBeVisible();
  await expect(page.getByRole('button', { name: '提交审核决定' })).toBeDisabled();
});

test('review deep link restores the fixed reading order, decision, and final content', async ({ page }) => {
  await installContract(page);
  await page.goto('/reviews/review-approved');

  await expect(page).toHaveURL('/reviews/review-approved');
  const detail = page.getByRole('dialog', { name: '审核包详情' });
  await expect(detail).toBeVisible();
  await expect(detail.getByText('修改后通过（approved_with_edits）', { exact: true })).toBeVisible();
  await expect(detail.getByText(approvedRecord.finalContent!, { exact: true })).toBeVisible();
  await expect(detail.getByText(olderApprovedRecord.finalContent!, { exact: true })).toHaveCount(0);
  await expect(detail.locator('[data-review-section]').allTextContents()).resolves.toEqual([
    expect.stringContaining('背景'),
    expect.stringContaining('已确认事实'),
    expect.stringContaining('未确认事实'),
    expect.stringContaining('处理理由'),
    expect.stringContaining('风险'),
    expect.stringContaining('替代方案'),
    expect.stringContaining('引用依据'),
    expect.stringContaining('拟发送内容'),
  ]);
  await detail.getByRole('button', { name: '返回审核队列' }).click();
  await expect(page).toHaveURL('/reviews');
});

test('review list selection and browser back keep the detail URL bidirectional', async ({ page }) => {
  await installContract(page);
  await page.goto('/reviews');

  await page.locator('.review-queue-table').getByRole('button', { name: '查看审核包：直播合作合同回复审核' }).click();
  await expect(page).toHaveURL('/reviews/review-pending');
  await expect(page.getByRole('dialog', { name: '审核包详情' })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL('/reviews');
  await expect(page.getByRole('dialog', { name: '审核包详情' })).toHaveCount(0);
});

test('review submission blocks duplicates and keeps errors inside the approval gate', async ({ page }) => {
  const contract = await installContract(page, { reviewWriteDelayMs: 250, reviewWriteError: true });
  await page.goto('/reviews/review-pending');

  const submit = page.getByRole('button', { name: '提交审核决定' });
  await submit.dblclick();
  await expect(page.locator('.review-submit-error')).toContainText('UI 合约夹具：审核提交失败');
  await expect(page.getByRole('dialog', { name: '审核包详情' })).toBeVisible();
  expect(contract.reviewWrites).toHaveLength(1);
});

test('review drawer protects dirty edits and requires reasons for edited approval rejection and more information', async ({ page }) => {
  await installContract(page);
  await page.goto('/reviews/review-pending');

  const detail = page.getByRole('dialog', { name: '审核包详情' });
  await detail.getByLabel('最终正文').fill('人工修改后的最终正文');
  await detail.getByRole('button', { name: '返回审核队列' }).click();
  const discard = page.getByRole('dialog', { name: '放弃未保存的审核决定？' });
  await expect(discard).toBeVisible();
  await discard.getByRole('button', { name: '继续审核' }).click();
  await expect(detail.getByLabel('最终正文')).toHaveValue('人工修改后的最终正文');

  const decision = detail.getByRole('combobox', { name: '审核决定' });
  const decisionControl = detail.locator('label').filter({ hasText: '审核决定' }).locator('.ant-select-selector');
  const comments = detail.getByLabel('审核意见和修改原因');
  const submit = page.getByRole('button', { name: '提交审核决定' });
  for (const [label, warning] of [
    ['修改后通过', '修改后通过必须填写修改原因'],
    ['驳回', '驳回必须填写审核理由'],
    ['要求补充信息', '要求补充信息必须填写具体理由'],
  ] as const) {
    await decision.scrollIntoViewIfNeeded();
    await decisionControl.click();
    const option = page.locator('.ant-select-dropdown:visible').getByText(label, { exact: true });
    await option.scrollIntoViewIfNeeded();
    await option.click();
    await comments.fill('');
    await expect(detail.getByText(warning, { exact: true })).toBeVisible();
    await expect(submit).toBeDisabled();
    await comments.fill(`${label}的可审计理由`);
    await expect(submit).toBeEnabled();
  }
});

test('return to matter is immediate when clean and uses the same dirty guard when edited', async ({ page }) => {
  await installContract(page);
  await page.goto('/reviews/review-pending');

  const detail = page.getByRole('dialog', { name: '审核包详情' });
  await detail.getByRole('button', { name: '返回事项' }).click();
  await expect(page).toHaveURL('/matters/matter-contract');

  await page.goBack();
  await expect(detail).toBeVisible();
  await detail.getByLabel('最终正文').fill('尚未保存的人工修订');
  await detail.getByRole('button', { name: '返回事项' }).click();
  const discard = page.getByRole('dialog', { name: '放弃未保存的审核决定？' });
  await expect(discard).toBeVisible();
  await expect(page).toHaveURL('/reviews/review-pending');
  await discard.getByRole('button', { name: '继续审核' }).click();
  await expect(detail.getByLabel('最终正文')).toHaveValue('尚未保存的人工修订');

  await detail.getByRole('button', { name: '返回事项' }).click();
  await page.getByRole('dialog', { name: '放弃未保存的审核决定？' }).getByRole('button', { name: '放弃修改' }).click();
  await expect(page).toHaveURL('/matters/matter-contract');
});

test('approved communication is queued once and never presented as sent', async ({ page }) => {
  const contract = await installContract(page, { queueDelayMs: 250 });
  await page.goto('/reviews');

  const queueButton = page.locator('.review-queue-table').getByRole('button', { name: '将已批准的合同回复进入外发队列' });
  await queueButton.dblclick();
  await expect(page.getByText('已进入外发队列，不等于已发送', { exact: true })).toBeVisible();
  expect(contract.queueWrites).toBe(1);
  await expect(page.getByText('已发送', { exact: true })).toHaveCount(0);
});

test('mobile review queue uses ReviewCards and a full-width readable detail overlay', async ({ page }) => {
  await installContract(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/reviews');

  await expect(page.locator('.review-queue-table')).toBeHidden();
  const firstCard = page.locator('.review-mobile-card').first();
  await expect(firstCard.getByRole('heading')).toBeInViewport();
  await expect(firstCard.getByText('待审核（pending_review）', { exact: true })).toBeInViewport();
  await firstCard.getByRole('button', { name: '查看审核包：直播合作合同回复审核' }).click();
  const detail = page.getByRole('dialog', { name: '审核包详情' });
  await expect(detail).toBeVisible();
  await expect(detail).toHaveCSS('width', '390px');
  await expect(detail.getByText('拟发送内容', { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('AgentRun list uses Chinese status with technical code and truthful completion semantics', async ({ page }) => {
  await installContract(page);
  await page.goto('/system/agent-runs');

  await expect(page.getByRole('heading', { name: 'Agent 执行记录' })).toBeVisible();
  const table = page.locator('.agent-runs-table');
  await expect(table.getByText('运行完成（completed）', { exact: true })).toBeVisible();
  await expect(table.getByText('运行失败（failed）', { exact: true })).toBeVisible();
  await expect(page.getByText('运行完成不等于法律结论已确认', { exact: true })).toBeVisible();
});

test('AgentRun list distinguishes expired login, permission denial, and stale data without exposing run summaries', async ({ browser }) => {
  for (const [status, variant, title] of [
    [401, 'permission', '登录状态已失效'],
    [403, 'permission', '无权访问 Agent 执行数据'],
    [409, 'stale', 'Agent 执行数据版本已变化'],
  ] as const) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await installContract(page, { agentListStatus: status });
    await page.goto('/system/agent-runs');
    await expect(page.locator(`.state-panel--${variant}`)).toContainText(title.replace(' Agent', 'Agent'));
    await expect(page.getByText(completedRun.id, { exact: true })).toHaveCount(0);
    await context.close();
  }
});

test('AgentRun deep links and list selection keep the detail URL bidirectional', async ({ page }) => {
  const consoleMessages: string[] = [];
  page.on('console', (message) => consoleMessages.push(message.text()));
  await installContract(page);
  await page.goto('/system/agent-runs/run-completed');

  const detail = page.getByRole('dialog', { name: 'Agent 执行详情' });
  await expect(detail).toBeVisible();
  await expect(detail.getByText('run-completed', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '返回执行记录' }).click();
  await expect(page).toHaveURL('/system/agent-runs');

  await page.locator('.agent-runs-table').getByRole('button', { name: '查看执行记录：run-completed' }).click();
  await expect(page).toHaveURL('/system/agent-runs/run-completed');
  await page.goBack();
  await expect(page).toHaveURL('/system/agent-runs');
  await expect(page.getByRole('dialog', { name: 'Agent 执行详情' })).toHaveCount(0);
  expect(consoleMessages).not.toContainEqual(expect.stringContaining('[antd: Descriptions]'));
});

test('mobile AgentRun cards keep essential data visible and JSON scroll local', async ({ page }) => {
  await installContract(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/system/agent-runs');

  await expect(page.getByText('运行完成不等于法律结论已确认', { exact: true })).toBeVisible();
  await expect(page.locator('.agent-runs-table')).toBeHidden();
  const firstCard = page.locator('.run-mobile-card').first();
  await expect(firstCard.getByRole('heading')).toBeInViewport();
  await expect(firstCard.getByText('运行完成（completed）', { exact: true })).toBeInViewport();
  await expect(firstCard.getByText('尝试 1/3', { exact: true })).toBeInViewport();
  await firstCard.getByRole('button', { name: '查看执行记录：run-completed' }).click();

  const json = page.getByRole('region', { name: '结构化输出 JSON' });
  await expect(json).toBeVisible();
  expect(await json.evaluate((element) => element.scrollWidth > element.clientWidth)).toBeTruthy();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('read fixtures reject unexpected HTTP methods instead of masking writes', async ({ page }) => {
  const contract = await installContract(page);
  await page.goto('/system/about');
  const status = await page.evaluate(async () => (await fetch('/api/v1/auth/session', { method: 'POST' })).status);
  expect(status).toBe(501);
  expect(contract.unexpected).toEqual(['POST /api/v1/auth/session']);
  contract.unexpected.length = 0;
});
