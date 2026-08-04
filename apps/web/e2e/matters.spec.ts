import { expect, test, type Page, type Route } from '@playwright/test';

const matters = [
  {
    id: 'matter-contract',
    matterNumber: 'LW-2026-CONTRACT',
    title: '直播合作合同审查',
    primaryCategory: 'contract',
    secondaryCategories: [],
    lifecycleStatus: 'open',
    workStatus: 'in_progress',
    ownerId: 'ou_contract_legal',
    collaboratorIds: [],
    requesterIds: ['ou_business'],
    entityIds: [],
    legalRisk: 'high',
    businessImpact: 'project',
    confidentiality: 'internal',
    summary: '审查直播合作合同中的退款安排。',
    objective: '确认合作和结算边界。',
    currentStage: 'review',
    version: 1,
    openedAt: '2026-08-04T09:00:00+08:00',
    resolvedAt: null,
    closedAt: null,
    reopenedAt: null,
  },
  {
    id: 'matter-employment',
    matterNumber: 'LW-2026-EMPLOYMENT',
    title: '员工手册修订',
    primaryCategory: 'employment',
    secondaryCategories: [],
    lifecycleStatus: 'open',
    workStatus: 'ready',
    ownerId: 'ou_employment_legal',
    collaboratorIds: [],
    requesterIds: ['ou_hr'],
    entityIds: [],
    legalRisk: 'medium',
    businessImpact: 'company',
    confidentiality: 'confidential',
    summary: '核对员工手册修订内容。',
    objective: '完成制度文本复核。',
    currentStage: 'intake',
    version: 2,
    openedAt: '2026-08-03T10:30:00+08:00',
    resolvedAt: null,
    closedAt: null,
    reopenedAt: null,
  },
  {
    id: 'matter-dispute',
    matterNumber: 'LW-2026-DISPUTE',
    title: '消费者争议应诉',
    primaryCategory: 'dispute',
    secondaryCategories: [],
    lifecycleStatus: 'open',
    workStatus: 'blocked',
    ownerId: 'ou_dispute_legal',
    collaboratorIds: [],
    requesterIds: ['ou_service'],
    entityIds: [],
    legalRisk: 'critical',
    businessImpact: 'company',
    confidentiality: 'restricted',
    summary: '处理消费者争议。',
    objective: '形成应诉方案。',
    currentStage: 'response',
    version: 1,
    openedAt: '2026-08-02T14:00:00+08:00',
    resolvedAt: null,
    closedAt: null,
    reopenedAt: null,
  },
  {
    id: 'matter-copy',
    matterNumber: 'LW-2026-COPY',
    title: '直播宣传文案复核',
    primaryCategory: 'copy_review',
    secondaryCategories: [],
    lifecycleStatus: 'open',
    workStatus: 'waiting',
    ownerId: 'ou_copy_legal',
    collaboratorIds: [],
    requesterIds: ['ou_marketing'],
    entityIds: [],
    legalRisk: 'low',
    businessImpact: 'department',
    confidentiality: 'internal',
    summary: '复核直播宣传文案。',
    objective: '确认宣传表述边界。',
    currentStage: 'review',
    version: 3,
    openedAt: '2026-08-01T08:45:00+08:00',
    resolvedAt: null,
    closedAt: null,
    reopenedAt: null,
  },
] as const;

const contractWorkItem = {
  id: 'work-contract',
  matterId: 'matter-contract',
  title: '核对退款与结算条款',
  status: 'in_progress',
  ownerId: 'ou_contract_legal',
  collaboratorIds: [],
  priority: 'high',
  prioritySource: 'legal_confirmed',
  aiSuggestedPriority: 'medium',
  priorityReasons: ['上线时间临近', '退款责任需业务确认'],
  overrideReason: null,
  estimatedMinutes: 90,
  nextAction: '与业务确认退款触发条件',
  waitingPartyId: 'ou_business',
  waitingReason: '等待确认结算口径',
  waitingSince: '2026-08-04T10:00:00+08:00',
  isBlocked: true,
  blockerReason: '等待财务确认退款预算',
  blockerOwnerId: 'ou_finance',
  plannedStartAt: '2026-08-04T09:30:00+08:00',
  plannedCompleteAt: '2026-08-05T18:00:00+08:00',
  completedAt: null,
  priorityConfirmedBy: 'ou_contract_legal',
  priorityConfirmedAt: '2026-08-04T09:20:00+08:00',
  sequenceOrder: 1,
  version: 7,
} as const;

const contractDeadline = {
  id: 'deadline-contract',
  matterId: 'matter-contract',
  workItemId: 'work-contract',
  deadlineType: 'legal',
  source: 'legal_confirmed',
  dueAt: '2026-08-06T18:00:00+08:00',
  timezone: 'Asia/Shanghai',
  isHard: true,
  status: 'active',
  sourceReference: '监管问询通知',
  confidence: null,
  reminderPolicy: { reminders: ['24h', '2h'] },
  confirmedBy: 'ou_contract_legal',
  confirmedAt: '2026-08-04T09:30:00+08:00',
  completedAt: null,
  version: 2,
} as const;

const contractDependency = {
  id: 'dependency-contract',
  workItemId: 'work-contract',
  dependsOnWorkItemId: null,
  dependencyType: 'material',
  status: 'active',
  externalPartyId: 'ou_business',
  description: '等待业务提供最终结算表',
  satisfiedAt: null,
  waivedBy: null,
  waivedAt: null,
  version: 1,
} as const;

const createdReviewPackage = {
  id: 'review-created',
  matterId: 'matter-contract',
  workItemId: 'work-contract',
  packageType: 'external_message',
  status: 'pending_review',
  title: '直播合作合同审查 - 外发回复审核',
  background: '审查直播合作合同中的退款安排。',
  confirmedFacts: [],
  unconfirmedFacts: [],
  reasoning: '基于当前已确认事实和公司处理口径形成回复，所有外发内容须经法务审核。',
  risks: [],
  alternatives: [],
  citations: [],
  proposedContent: '请业务补充最终结算表后再确认退款口径。',
  target: { receiveId: 'ou_business', receiveIdType: 'open_id', messageType: 'text' },
  createdBy: 'ou_contract_legal',
  submittedAt: '2026-08-04T11:00:00+08:00',
  approvedContentHash: null,
  version: 1,
} as const;

interface CapturedMutation {
  path: string;
  body: Record<string, unknown>;
  idempotencyKey: string | null;
  correlationId: string | null;
}

const unexpectedFixtureRequests = new WeakMap<Page, string[]>();

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers: { 'X-UI-Contract-Fixture': 'true' },
    body: JSON.stringify(body),
  });
}

function recordUnexpectedFixtureRequest(page: Page, route: Route) {
  const request = route.request();
  const url = new URL(request.url());
  const entry = `${request.method()} ${url.pathname}${url.search}`;
  const requests = unexpectedFixtureRequests.get(page) ?? [];
  requests.push(entry);
  unexpectedFixtureRequests.set(page, requests);
  return entry;
}

async function rejectUnexpectedFixtureRequest(page: Page, route: Route, status = 501) {
  const entry = recordUnexpectedFixtureRequest(page, route);
  await fulfillJson(route, { detail: `unexpected fixture request: ${entry}` }, status);
}

async function requireFixtureMethod(page: Page, route: Route, method: 'GET' | 'POST') {
  if (route.request().method() === method) return true;
  await rejectUnexpectedFixtureRequest(page, route, 405);
  return false;
}

function consumeUnexpectedFixtureRequests(page: Page) {
  return unexpectedFixtureRequests.get(page)?.splice(0) ?? [];
}

async function installMatterContract(page: Page, list: unknown = matters) {
  unexpectedFixtureRequests.set(page, []);
  await page.route('**/api/v1/**', (route) => rejectUnexpectedFixtureRequest(page, route));
  await page.route('**/api/v1/auth/session', async (route) => {
    if (!await requireFixtureMethod(page, route, 'GET')) return;
    await fulfillJson(route, { actorId: 'ou_contract_legal' });
  });
  await page.route(/\/api\/v1\/matters\?/, async (route) => {
    if (!await requireFixtureMethod(page, route, 'GET')) return;
    await fulfillJson(route, list);
  });
  for (const matter of matters) {
    await page.route(`**/api/v1/matters/${matter.id}`, async (route) => {
      if (!await requireFixtureMethod(page, route, 'GET')) return;
      await fulfillJson(route, matter);
    });
    await page.route(`**/api/v1/matters/${matter.id}/work-items`, async (route) => {
      if (!await requireFixtureMethod(page, route, 'GET')) return;
      await fulfillJson(route, []);
    });
  }
}

async function installMatterDetailContract(page: Page, options: {
  deadlineError?: boolean;
  dependencyError?: boolean;
  deadlineStatus?: 401 | 403 | 409 | 503;
  dependencyStatus?: 401 | 403 | 409 | 503;
  writeDelayMs?: number;
} = {}) {
  let deadlineStatus = options.deadlineStatus ?? (options.deadlineError ? 503 : undefined);
  let dependencyStatus = options.dependencyStatus ?? (options.dependencyError ? 503 : undefined);
  const mutations: CapturedMutation[] = [];

  await page.route('**/api/v1/matters/matter-contract/work-items', async (route) => {
    if (!await requireFixtureMethod(page, route, 'GET')) return;
    await fulfillJson(route, [contractWorkItem]);
  });
  await page.route('**/api/v1/work-items/work-contract/deadlines', async (route) => {
    if (route.request().method() === 'GET') {
      return deadlineStatus
        ? fulfillJson(route, { detail: `UI 合约夹具：期限读取失败 ${deadlineStatus}` }, deadlineStatus)
        : fulfillJson(route, [contractDeadline]);
    }
    if (!await requireFixtureMethod(page, route, 'POST')) return;
    mutations.push(await captureMutation(route));
    if (options.writeDelayMs) await new Promise((resolve) => setTimeout(resolve, options.writeDelayMs));
    return fulfillJson(route, { deadlineId: 'deadline-created' });
  });
  await page.route('**/api/v1/work-items/work-contract/dependencies', async (route) => {
    if (route.request().method() === 'GET') {
      return dependencyStatus
        ? fulfillJson(route, { detail: `UI 合约夹具：依赖读取失败 ${dependencyStatus}` }, dependencyStatus)
        : fulfillJson(route, [contractDependency]);
    }
    if (!await requireFixtureMethod(page, route, 'POST')) return;
    mutations.push(await captureMutation(route));
    if (options.writeDelayMs) await new Promise((resolve) => setTimeout(resolve, options.writeDelayMs));
    return fulfillJson(route, { dependencyId: 'dependency-created' });
  });
  await page.route('**/api/v1/work-items/work-contract/priority-confirmations', async (route) => {
    if (!await requireFixtureMethod(page, route, 'POST')) return;
    mutations.push(await captureMutation(route));
    if (options.writeDelayMs) await new Promise((resolve) => setTimeout(resolve, options.writeDelayMs));
    return fulfillJson(route, { workItemId: 'work-contract', confirmationId: 'priority-created', version: 8 });
  });
  await page.route('**/api/v1/reviews/packages', async (route) => {
    if (!await requireFixtureMethod(page, route, 'POST')) return;
    mutations.push(await captureMutation(route));
    if (options.writeDelayMs) await new Promise((resolve) => setTimeout(resolve, options.writeDelayMs));
    return fulfillJson(route, { reviewPackageId: 'review-created', version: 1 });
  });
  await page.route(/\/api\/v1\/reviews\/packages\?/, async (route) => {
    if (!await requireFixtureMethod(page, route, 'GET')) return;
    await fulfillJson(route, [createdReviewPackage]);
  });
  await page.route('**/api/v1/reviews/packages/review-created', async (route) => {
    if (!await requireFixtureMethod(page, route, 'GET')) return;
    await fulfillJson(route, createdReviewPackage);
  });
  await page.route('**/api/v1/reviews/packages/review-created/records', async (route) => {
    if (!await requireFixtureMethod(page, route, 'GET')) return;
    await fulfillJson(route, []);
  });

  return {
    mutations,
    recoverDeadlines: () => { deadlineStatus = undefined; },
    recoverDependencies: () => { dependencyStatus = undefined; },
  };
}

async function captureMutation(route: Route): Promise<CapturedMutation> {
  const request = route.request();
  return {
    path: new URL(request.url()).pathname,
    body: (request.postDataJSON() ?? {}) as Record<string, unknown>,
    idempotencyKey: request.headers()['idempotency-key'] ?? null,
    correlationId: request.headers()['x-correlation-id'] ?? null,
  };
}

async function chooseOption(page: Page, comboboxName: string, optionName: string) {
  await page.getByRole('combobox', { name: comboboxName }).click();
  await page.locator('.ant-select-dropdown:visible .ant-select-item-option-content').getByText(optionName, { exact: true }).click();
}

test.beforeEach(async ({ page }) => {
  await installMatterContract(page);
});

test.afterEach(async ({ page }) => {
  expect(unexpectedFixtureRequests.get(page) ?? [], 'unexpected fixture requests').toEqual([]);
});

test('matter fixtures fail closed for undeclared paths and wrong methods', async ({ page }) => {
  const contract = await installMatterDetailContract(page);
  await page.goto('/matters/matter-contract');

  const responses = await page.evaluate(async () => {
    const undeclared = await fetch('/api/v1/not-declared');
    const wrongMethod = await fetch('/api/v1/reviews/packages', { method: 'PUT' });
    return {
      undeclared: { status: undeclared.status, body: await undeclared.json() },
      wrongMethod: { status: wrongMethod.status, body: await wrongMethod.json() },
    };
  });

  expect(responses.undeclared).toEqual({
    status: 501,
    body: { detail: 'unexpected fixture request: GET /api/v1/not-declared' },
  });
  expect(responses.wrongMethod).toEqual({
    status: 405,
    body: { detail: 'unexpected fixture request: PUT /api/v1/reviews/packages' },
  });
  expect(contract.mutations).toHaveLength(0);
  expect(consumeUnexpectedFixtureRequests(page)).toEqual([
    'GET /api/v1/not-declared',
    'PUT /api/v1/reviews/packages',
  ]);
});

test('keyword search filters real matter fields and persists through refresh', async ({ page }) => {
  await page.goto('/matters');

  const search = page.getByRole('searchbox', { name: '搜索法务事项队列' });
  await search.fill('员工手册');

  await expect(page).toHaveURL('/matters?q=%E5%91%98%E5%B7%A5%E6%89%8B%E5%86%8C');
  await expect(page.getByRole('button', { name: '打开事项：员工手册修订' })).toBeVisible();
  await expect(page.getByRole('button', { name: '打开事项：直播合作合同审查' })).toHaveCount(0);

  await page.reload();
  await expect(search).toHaveValue('员工手册');
  await expect(page.getByRole('button', { name: '打开事项：员工手册修订' })).toBeVisible();
});

test('category risk status and owner filters each change the visible result', async ({ page }) => {
  await page.goto('/matters');

  await chooseOption(page, '事项分类', '合同审核');
  await expect(page).toHaveURL('/matters?category=contract');
  await expect(page.getByRole('button', { name: '打开事项：直播合作合同审查' })).toBeVisible();
  await expect(page.getByRole('button', { name: '打开事项：员工手册修订' })).toHaveCount(0);
  await page.getByRole('region', { name: '已启用筛选' }).getByRole('button', { name: '清除全部筛选' }).click();

  await chooseOption(page, '法律风险', '严重风险');
  await expect(page).toHaveURL('/matters?risk=critical');
  await expect(page.getByRole('button', { name: '打开事项：消费者争议应诉' })).toBeVisible();
  await expect(page.getByRole('button', { name: '打开事项：直播合作合同审查' })).toHaveCount(0);
  await page.getByRole('region', { name: '已启用筛选' }).getByRole('button', { name: '清除全部筛选' }).click();

  await chooseOption(page, '工作状态', '等待中');
  await expect(page).toHaveURL('/matters?status=waiting');
  await expect(page.getByRole('button', { name: '打开事项：直播宣传文案复核' })).toBeVisible();
  await expect(page.getByRole('button', { name: '打开事项：消费者争议应诉' })).toHaveCount(0);
  await page.getByRole('region', { name: '已启用筛选' }).getByRole('button', { name: '清除全部筛选' }).click();

  await chooseOption(page, '负责人', 'ou_employment_legal');
  await expect(page).toHaveURL('/matters?owner=ou_employment_legal');
  await expect(page.getByRole('button', { name: '打开事项：员工手册修订' })).toBeVisible();
  await expect(page.getByRole('button', { name: '打开事项：直播宣传文案复核' })).toHaveCount(0);
  await expect(page.getByText('共 1 项')).toBeVisible();
});

test('unknown query parameters survive filter changes clearing and browser back', async ({ page }) => {
  await page.goto('/matters?source=template');

  await chooseOption(page, '法律风险', '高风险');
  await expect(page).toHaveURL('/matters?source=template&risk=high');
  await page.getByRole('region', { name: '已启用筛选' }).getByRole('button', { name: '清除风险筛选' }).click();
  await expect(page).toHaveURL('/matters?source=template');

  await chooseOption(page, '事项分类', '合同审核');
  const activeFilters = page.getByRole('region', { name: '已启用筛选' });
  await activeFilters.getByRole('button', { name: '清除全部筛选' }).click();
  await expect(page).toHaveURL('/matters?source=template');
  await expect(activeFilters).toHaveCount(0);

  await chooseOption(page, '事项分类', '合同审核');
  await page.getByRole('button', { name: '打开事项：直播合作合同审查' }).click();
  await expect(page).toHaveURL('/matters/matter-contract');
  await page.goBack();
  await expect(page).toHaveURL('/matters?source=template&category=contract');
  await expect(page.getByRole('button', { name: '打开事项：直播合作合同审查' })).toBeVisible();
});

test('active filters can be removed one at a time or all at once', async ({ page }) => {
  await page.goto('/matters?category=contract&risk=high&status=in_progress&owner=ou_contract_legal');

  const activeFilters = page.getByRole('region', { name: '已启用筛选' });
  await expect(activeFilters).toContainText('分类：合同审核');
  await expect(activeFilters).toContainText('风险：高风险');
  await expect(activeFilters).toContainText('状态：处理中');
  await expect(activeFilters).toContainText('负责人：ou_contract_legal');

  await activeFilters.getByRole('button', { name: '清除分类筛选' }).click();
  await expect(page).toHaveURL('/matters?risk=high&status=in_progress&owner=ou_contract_legal');
  await expect(activeFilters).not.toContainText('分类：合同审核');

  await activeFilters.getByRole('button', { name: '清除全部筛选' }).click();
  await expect(page).toHaveURL('/matters');
  await expect(activeFilters).toHaveCount(0);
  await expect(page.getByText('共 4 项')).toBeVisible();
});

test('matter title opens detail and the explicit return restores the complete query', async ({ page }) => {
  await page.goto('/matters?category=contract&risk=high&status=in_progress&owner=ou_contract_legal');

  await page.getByRole('button', { name: '打开事项：直播合作合同审查' }).click();
  await expect(page).toHaveURL('/matters/matter-contract');
  await page.getByRole('button', { name: '返回事项中心' }).click();

  await expect(page).toHaveURL('/matters?category=contract&risk=high&status=in_progress&owner=ou_contract_legal');
  await expect(page.locator('.matter-filter-toolbar .ant-select-selection-item', { hasText: '合同审核' })).toBeVisible();
  await expect(page.getByRole('button', { name: '打开事项：直播合作合同审查' })).toBeVisible();
});

test('client sorting page and scroll position survive the matter detail round trip within the 100-item API window', async ({ page }) => {
  const pagedMatters = Array.from({ length: 14 }, (_, index) => ({
    ...matters[index % matters.length],
    id: `matter-page-${String(index + 1).padStart(2, '0')}`,
    matterNumber: `LW-2026-PAGE-${String(index + 1).padStart(2, '0')}`,
    title: `分页事项 ${String(index + 1).padStart(2, '0')}`,
    openedAt: `2026-07-${String(index + 1).padStart(2, '0')}T09:00:00+08:00`,
  }));
  const selectedMatter = pagedMatters[12];
  await page.unroute(/\/api\/v1\/matters\?/);
  await page.route(/\/api\/v1\/matters\?/, (route) => fulfillJson(route, pagedMatters));
  await page.route(`**/api/v1/matters/${selectedMatter.id}`, (route) => fulfillJson(route, selectedMatter));
  await page.route(`**/api/v1/matters/${selectedMatter.id}/work-items`, (route) => fulfillJson(route, []));
  await page.setViewportSize({ width: 1024, height: 400 });
  await page.goto('/matters?sort=title_asc&page=2');

  const sortControl = page.locator('.matter-filter-toolbar .ant-select').filter({
    has: page.getByRole('combobox', { name: '事项排序' }),
  });
  await expect(sortControl.locator('.ant-select-selection-item')).toHaveText('标题 A–Z');
  const visibleTitles = page.locator('.responsive-collection__compact:visible .matter-title-button');
  await expect(visibleTitles).toHaveCount(2);
  await expect(visibleTitles.nth(0)).toHaveText('分页事项 13');
  await expect(visibleTitles.nth(1)).toHaveText('分页事项 14');
  await expect(page.getByText('当前仅在服务返回的前 100 项内排序和分页')).toBeVisible();

  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  const priorScrollY = await page.evaluate(() => window.scrollY);
  expect(priorScrollY).toBeGreaterThan(0);
  await page.getByRole('button', { name: '打开事项：分页事项 13' }).click();
  await expect(page).toHaveURL(`/matters/${selectedMatter.id}`);
  await page.getByRole('button', { name: '返回事项中心' }).click();

  await expect(page).toHaveURL('/matters?sort=title_asc&page=2');
  await expect(visibleTitles.nth(0)).toHaveText('分页事项 13');
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThanOrEqual(priorScrollY - 20);
});

test('required viewports use desktop table compact records and mobile matter cards without overflow', async ({ page }) => {
  const cases = [
    { viewport: { width: 1440, height: 900 }, visible: '.responsive-collection__desktop' },
    { viewport: { width: 1024, height: 768 }, visible: '.responsive-collection__compact' },
    { viewport: { width: 390, height: 844 }, visible: '.responsive-collection__mobile' },
  ] as const;

  for (const { viewport, visible } of cases) {
    await page.setViewportSize(viewport);
    await page.goto('/matters');
    await expect(page.locator(`.matters-collection ${visible}`)).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/matters');
  await expect(page.getByRole('columnheader', { name: '打开' })).toHaveCount(0);
  await expect(page.locator('.responsive-collection__desktop').getByRole('button', { name: '打开事项：直播合作合同审查' })).toBeVisible();

  await page.setViewportSize({ width: 1024, height: 768 });
  await expect(page.locator('.matter-compact-record')).toHaveCount(4);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('article', { name: '事项：直播合作合同审查' })).toBeVisible();
  await expect(page.getByRole('article', { name: '事项：直播合作合同审查' })).toContainText('高风险');
  await expect(page.getByRole('article', { name: '事项：直播合作合同审查' })).toContainText('ou_contract_legal');
  await expect(page.getByText('法律期限')).toHaveCount(0);
  await expect(page.getByText('下一步')).toHaveCount(0);
  await expect(page.getByText('等待对象')).toHaveCount(0);
});

test('risk is communicated with text in every collection layout', async ({ page }) => {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1024, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/matters?risk=critical');
    const risk = page.locator('.matters-collection [data-status-kind="risk"]:visible');
    await expect(risk).toHaveText('严重风险');
    await expect(risk).toHaveAttribute('data-status-tone', 'critical');
  }
});

test('true empty filtered empty and API error remain distinct without fallback data', async ({ page }) => {
  await page.unroute(/\/api\/v1\/matters\?/);
  await page.route(/\/api\/v1\/matters\?/, (route) => fulfillJson(route, []));
  await page.goto('/matters');
  await expect(page.locator('.state-panel--empty')).toContainText('暂无法务事项');
  await expect(page.locator('.state-panel--filtered-empty')).toHaveCount(0);

  await page.unroute(/\/api\/v1\/matters\?/);
  await page.route(/\/api\/v1\/matters\?/, (route) => fulfillJson(route, matters));
  await page.goto('/matters?q=%E4%B8%8D%E5%AD%98%E5%9C%A8');
  const filteredEmpty = page.locator('.state-panel--filtered-empty');
  await expect(filteredEmpty).toContainText('没有符合筛选条件的事项');
  await expect(filteredEmpty.getByRole('button', { name: '清除全部筛选' })).toBeVisible();

  await page.unroute(/\/api\/v1\/matters\?/);
  await page.route(/\/api\/v1\/matters\?/, (route) => fulfillJson(route, { detail: 'service unavailable' }, 503));
  await page.goto('/matters');
  const error = page.locator('.state-panel--error');
  await expect(error).toContainText('法务事项加载失败');
  await expect(error.getByRole('button', { name: '重试' })).toBeVisible();
  await expect(page.getByRole('button', { name: '打开事项：直播合作合同审查' })).toHaveCount(0);
});

test('matter list distinguishes expired login, permission denial, and stale data without exposing matter summaries', async ({ browser }) => {
  for (const [status, variant, title] of [
    [401, 'permission', '登录状态已失效'],
    [403, 'permission', '无权访问法务事项'],
    [409, 'stale', '法务事项版本已变化'],
  ] as const) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await installMatterContract(page);
    await page.unroute(/\/api\/v1\/matters\?/);
    await page.route(/\/api\/v1\/matters\?/, (route) => fulfillJson(route, { detail: `UI 合约夹具：事项列表 ${status}` }, status));
    await page.goto('/matters');
    await expect(page.locator(`.state-panel--${variant}`)).toContainText(title);
    await expect(page.getByText('直播合作合同审查', { exact: true })).toHaveCount(0);
    await context.close();
  }
});

test('matter detail leads with decision context and keeps return navigation explicit', async ({ page }) => {
  await installMatterDetailContract(page);
  await page.goto('/matters/matter-contract');

  await expect(page.getByRole('heading', { name: '直播合作合同审查' })).toBeVisible();
  await expect(page.getByRole('button', { name: '返回事项中心' })).toBeVisible();
  const overview = page.getByRole('region', { name: '事项决策概览' });
  await expect(overview.locator('.matter-overview-item')).toHaveCount(5);
  await expect(overview.locator('.matter-overview-item').nth(0)).toContainText('法律风险高风险');
  await expect(overview.locator('.matter-overview-item').nth(1)).toContainText('工作状态处理中');
  await expect(overview.locator('.matter-overview-item').nth(2)).toContainText('负责人标识ou_contract_legal');
  await expect(overview.locator('.matter-overview-item').nth(3)).toContainText('处理目标确认合作和结算边界');
  await expect(overview.locator('.matter-overview-item').nth(4)).toContainText('当前阶段审核准备');
  await expect(page.getByText('in_progress', { exact: true }).locator(':visible')).toHaveCount(0);
  await expect(page.getByText('review', { exact: true }).locator(':visible')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '核对退款与结算条款' })).toBeVisible();
  await expect(page.getByRole('region', { name: '任务决策摘要' })).toContainText('负责人标识ou_contract_legal');
  await expect(page.getByText('法定期限')).toBeVisible();
  await expect(page.getByText('等待材料')).toBeVisible();
});

test('work item decision summary exposes waiting, blocker, deadline, and complete dependency context on mobile', async ({ page }) => {
  await installMatterDetailContract(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/matters/matter-contract');

  const summary = page.getByRole('region', { name: '任务决策摘要' });
  const overview = page.getByRole('region', { name: '事项决策概览' });
  await expect(summary.getByText('与业务确认退款触发条件', { exact: true })).toBeVisible();
  await expect(summary).toContainText('2026/8/5 18:00:00');
  await expect(summary).toContainText('ou_business');
  await expect(summary).toContainText('等待确认结算口径');
  await expect(summary).toContainText('等待财务确认退款预算');
  await expect(summary).toContainText('ou_finance');
  await expect(summary).toContainText('2026/8/6 18:00:00');

  const dependencyRegion = page.getByRole('region', { name: '依赖信息' });
  await expect(dependencyRegion).toContainText('ou_business');
  await expect(dependencyRegion).toContainText('等待业务提供最终结算表');
  await expect(overview.locator('.matter-overview-item').nth(0)).toBeInViewport();
  await expect(overview.locator('.matter-overview-item').nth(2)).toBeInViewport();
  await expect(summary.getByText('与业务确认退款触发条件', { exact: true })).toBeInViewport();
  await expect(summary.getByText('2026/8/5 18:00:00', { exact: true })).toBeInViewport();
  await expect(summary.getByText('ou_business', { exact: true })).toBeInViewport();
  await expect(summary.getByText('等待财务确认退款预算', { exact: true })).toBeInViewport();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('deadline and dependency resources distinguish permission and stale states without presenting missing data as success', async ({ browser }) => {
  for (const [status, deadlineTitle, dependencyTitle] of [
    [401, '登录状态已失效', '登录状态已失效'],
    [403, '无权访问期限信息', '无权访问依赖信息'],
    [409, '期限信息版本已变化', '依赖信息版本已变化'],
  ] as const) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await installMatterContract(page);
    await installMatterDetailContract(page, { deadlineStatus: status, dependencyStatus: status });
    await page.goto('/matters/matter-contract');

    const deadlineRegion = page.getByRole('region', { name: '期限信息' });
    const dependencyRegion = page.getByRole('region', { name: '依赖信息' });
    const hardDeadline = page.getByRole('region', { name: '任务决策摘要' }).locator('dl > div').filter({ hasText: '最近硬期限' });
    await expect(deadlineRegion).toContainText(deadlineTitle);
    await expect(dependencyRegion).toContainText(dependencyTitle);
    await expect(hardDeadline).toContainText(deadlineTitle);
    await expect(hardDeadline).not.toContainText('当前未记录');
    await expect(deadlineRegion).not.toContainText('法定期限');
    await expect(dependencyRegion).not.toContainText('等待业务提供最终结算表');
    await context.close();
  }
});

test('deadline and dependency failures stay local and recover independently', async ({ page }) => {
  const contract = await installMatterDetailContract(page, { deadlineError: true, dependencyError: true });
  await page.goto('/matters/matter-contract');

  const deadlineRegion = page.getByRole('region', { name: '期限信息' });
  await expect(deadlineRegion).toContainText('期限信息加载失败');
  await expect(deadlineRegion).not.toContainText('暂无期限');
  const dependencyRegion = page.getByRole('region', { name: '依赖信息' });
  await expect(dependencyRegion).toContainText('依赖信息加载失败');
  await expect(dependencyRegion).not.toContainText('暂无依赖');

  contract.recoverDeadlines();
  await deadlineRegion.getByRole('button', { name: '重试期限' }).click();
  await expect(deadlineRegion.getByText('法定期限')).toBeVisible();
  await expect(dependencyRegion).toContainText('依赖信息加载失败');

  contract.recoverDependencies();
  await dependencyRegion.getByRole('button', { name: '重试依赖' }).click();
  await expect(dependencyRegion.getByText('等待材料')).toBeVisible();
});

test('priority dialog protects dirty edits and submits one versioned confirmation', async ({ page }) => {
  const consoleMessages: string[] = [];
  page.on('console', (message) => consoleMessages.push(message.text()));
  const contract = await installMatterDetailContract(page, { writeDelayMs: 400 });
  await page.goto('/matters/matter-contract');
  await page.getByRole('button', { name: '确认优先级' }).click();

  const dialog = page.getByRole('dialog', { name: '确认优先级与完成时间' });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('combobox', { name: '确认优先级' }).press('ArrowDown');
  await page.locator('.ant-select-dropdown:visible .ant-select-item-option-content').getByText('紧急', { exact: true }).click();
  await dialog.getByLabel('排序理由').fill('监管回复在即');
  await dialog.getByRole('button', { name: /取\s*消/ }).click();
  const discard = page.getByRole('dialog', { name: '放弃未保存的修改？' });
  await expect(discard).toBeVisible();
  await discard.getByRole('button', { name: '继续编辑' }).click();
  await expect(dialog.getByLabel('排序理由')).toHaveValue('监管回复在即');

  const submit = dialog.getByRole('button', { name: '确认优先级' });
  await submit.click();
  await expect(submit).toBeDisabled();
  await submit.click({ force: true });
  await expect.poll(() => contract.mutations.filter((item) => item.path.endsWith('/priority-confirmations')).length).toBe(1);
  const mutation = contract.mutations.find((item) => item.path.endsWith('/priority-confirmations'))!;
  expect(mutation.body).toMatchObject({ workItemVersion: 7, confirmedPriority: 'urgent', reasons: ['监管回复在即'] });
  expect(mutation.idempotencyKey).toBeTruthy();
  expect(mutation.correlationId).toBeTruthy();
  expect(consoleMessages).not.toContainEqual(expect.stringContaining('Instance created by `useForm` is not connected'));
});

test('deadline and dependency dialogs keep validation reachable and preserve deterministic payloads', async ({ page }) => {
  const contract = await installMatterDetailContract(page, { writeDelayMs: 400 });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/matters/matter-contract');

  await page.getByRole('button', { name: '添加期限' }).click();
  const deadlineDialog = page.getByRole('dialog', { name: '创建期限' });
  await expect.poll(async () => (await deadlineDialog.boundingBox())?.width ?? 0).toBeGreaterThanOrEqual(350);
  await deadlineDialog.locator('.ant-picker').hover();
  await deadlineDialog.locator('.ant-picker-clear').click();
  await deadlineDialog.getByRole('button', { name: '创建期限' }).click();
  await expect(deadlineDialog.getByText('请选择到期时间')).toBeVisible();
  await expect(deadlineDialog.locator('.ant-modal-footer')).toBeInViewport();
  await deadlineDialog.getByRole('button', { name: /取\s*消/ }).click();
  await page.getByRole('dialog', { name: '放弃未保存的修改？' }).getByRole('button', { name: '放弃修改' }).click();

  await page.getByRole('button', { name: '添加依赖' }).click();
  const dependencyDialog = page.getByRole('dialog', { name: '创建任务依赖' });
  const dependencySubmit = dependencyDialog.getByRole('button', { name: '创建依赖' });
  await dependencySubmit.click();
  await expect(dependencyDialog.getByText('请填写前置任务 ID、等待对象或依赖说明中的至少一项')).toBeVisible();
  expect(contract.mutations.filter((item) => item.path.endsWith('/dependencies'))).toHaveLength(0);
  await dependencyDialog.getByLabel('等待对象').fill('ou_business');
  await dependencyDialog.getByLabel('依赖说明').fill('等待业务提供最终结算表');
  await dependencyDialog.getByRole('button', { name: /取\s*消/ }).click();
  const dependencyDiscard = page.getByRole('dialog', { name: '放弃未保存的修改？' });
  await expect(dependencyDiscard).toBeVisible();
  await dependencyDiscard.getByRole('button', { name: '继续编辑' }).click();
  await expect(dependencyDialog.getByLabel('等待对象')).toHaveValue('ou_business');
  await expect(dependencyDialog.getByLabel('依赖说明')).toHaveValue('等待业务提供最终结算表');
  await dependencySubmit.click();
  await expect(dependencySubmit).toBeDisabled();
  await dependencySubmit.click({ force: true });
  await expect.poll(() => contract.mutations.filter((item) => item.path.endsWith('/dependencies')).length).toBe(1);
  expect(contract.mutations.find((item) => item.path.endsWith('/dependencies'))?.body).toMatchObject({
    dependencyType: 'material',
    externalPartyId: 'ou_business',
    description: '等待业务提供最终结算表',
  });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('review package dialog keeps its footer and full modal chrome inside desktop and mobile viewports', async ({ page }) => {
  await installMatterDetailContract(page);

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/matters/matter-contract');
    await page.getByRole('button', { name: '创建审核包' }).click();

    const dialog = page.getByRole('dialog', { name: '创建外发审核包' });
    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
    await expect(dialog.locator('.ant-modal-footer')).toBeInViewport();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);

    await dialog.getByRole('button', { name: /取\s*消/ }).click();
    await expect(dialog).toBeHidden();
  }
});

test('review package dialog guards unsaved content validation and duplicate submit', async ({ page }) => {
  const contract = await installMatterDetailContract(page, { writeDelayMs: 400 });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/matters/matter-contract');
  await page.getByRole('button', { name: '创建审核包' }).click();

  const dialog = page.getByRole('dialog', { name: '创建外发审核包' });
  await expect.poll(async () => (await dialog.boundingBox())?.width ?? 0).toBeGreaterThanOrEqual(350);
  await dialog.getByLabel('拟发送内容').fill('请业务补充最终结算表后再确认退款口径。');
  await dialog.getByRole('button', { name: /取\s*消/ }).click();
  const discard = page.getByRole('dialog', { name: '放弃未保存的修改？' });
  await expect(discard).toBeVisible();
  await discard.getByRole('button', { name: '继续编辑' }).click();
  await expect(dialog.getByLabel('拟发送内容')).toHaveValue('请业务补充最终结算表后再确认退款口径。');

  const submit = dialog.getByRole('button', { name: '创建并提交审核' });
  await submit.click();
  await expect(dialog.getByText('请填写回复原消息 ID 或收件人 Open ID')).toBeVisible();
  await expect(dialog.locator('.ant-modal-footer')).toBeInViewport();
  await dialog.getByLabel('收件人 Open ID').fill('ou_business');
  await submit.click();
  await expect(submit).toBeDisabled();
  await submit.click({ force: true });
  await expect.poll(() => contract.mutations.filter((item) => item.path === '/api/v1/reviews/packages').length).toBe(1);
  const mutation = contract.mutations.find((item) => item.path === '/api/v1/reviews/packages')!;
  expect(mutation.body).toMatchObject({
    matterId: 'matter-contract',
    workItemId: 'work-contract',
    submitForReview: true,
    target: { receiveId: 'ou_business', receiveIdType: 'open_id', messageType: 'text' },
  });
  expect(mutation.idempotencyKey).toBeTruthy();
  await expect(page).toHaveURL('/reviews/review-created');
  const review = page.getByRole('dialog', { name: '审核包详情' });
  await expect(review).toBeVisible();
  await expect(review.getByRole('region', { name: '外发目标' })).toContainText('收件人（open_id）：ou_business');
  await review.getByRole('button', { name: '返回事项' }).click();
  await expect(page).toHaveURL('/matters/matter-contract');
  await expect(page.getByRole('heading', { name: '直播合作合同审查' })).toBeVisible();
});
