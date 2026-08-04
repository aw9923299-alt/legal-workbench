import { expect, test, type Page, type Route } from '@playwright/test';

const matter = {
  id: 'matter-navigation',
  matterNumber: 'LW-2026-NAV',
  title: '导航恢复测试事项',
  primaryCategory: 'contract',
  secondaryCategories: [],
  lifecycleStatus: 'open',
  workStatus: 'in_progress',
  ownerId: 'ui-contract-reviewer',
  collaboratorIds: [],
  requesterIds: ['ui-contract-requester'],
  entityIds: [],
  legalRisk: 'high',
  businessImpact: 'project',
  confidentiality: 'internal',
  summary: '仅用于验证安全的前端导航合约。',
  objective: '刷新后仍恢复同一事项。',
  currentStage: 'review',
  version: 1,
  openedAt: '2026-08-04T09:00:00+08:00',
  resolvedAt: null,
  closedAt: null,
  reopenedAt: null,
};

const unrelatedMatter = {
  ...matter,
  id: 'matter-unrelated',
  matterNumber: 'LW-2026-OTHER',
  title: '员工手册版本确认',
  ownerId: 'ui-contract-other-reviewer',
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers: { 'X-UI-Contract-Fixture': 'true' },
    body: JSON.stringify(body),
  });
}

async function installNavigationContract(page: Page) {
  // Navigation tests use deterministic UI-contract fixtures only. They do not prove a
  // live Feishu, Codex, authentication, matter, review, or AgentRun integration.
  await page.route('**/api/v1/**', (route) => fulfillJson(route, []));
  await page.route('**/api/v1/auth/session', (route) => fulfillJson(route, { actorId: 'ui-contract-reviewer' }));
  await page.route(/\/api\/v1\/matters\?/, (route) => fulfillJson(route, [matter, unrelatedMatter]));
  await page.route('**/api/v1/matters/matter-navigation', (route) => fulfillJson(route, matter));
  await page.route('**/api/v1/matters/matter-navigation/work-items', (route) => fulfillJson(route, []));
}

function matterTitleButton(page: Page, title: string) {
  return page.getByRole('button', { name: `打开事项：${title}` });
}

test.beforeEach(async ({ page }) => {
  await installNavigationContract(page);
});

test('root maps to today and every navigation item produces a real path', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByText('工作', { exact: true })).toBeVisible();
  await expect(page.getByText('资料与模板', { exact: true })).toBeVisible();
  await expect(page.getByText('系统与审计', { exact: true })).toBeVisible();

  const destinations = [
    ['待确认消息', '/inbox'],
    ['法务事项', '/matters'],
    ['审核中心', '/reviews'],
    ['事项模板', '/templates'],
    ['合同与文件', '/files'],
    ['Agent 执行记录', '/system/agent-runs'],
    ['数据边界', '/system/data-boundaries'],
    ['系统信息', '/system/about'],
    ['今日工作台', '/today'],
  ] as const;

  for (const [name, path] of destinations) {
    await page.getByRole('menuitem', { name }).click();
    await expect(page).toHaveURL(new RegExp(`${path.replaceAll('/', '\\/')}$`));
  }
});

test('global matter search enters the real matters URL', async ({ page }) => {
  await page.goto('/today');

  const search = page.getByRole('searchbox', { name: '搜索法务事项' });
  await search.fill('导航');
  await search.press('Enter');

  await expect(page).toHaveURL('/matters?q=%E5%AF%BC%E8%88%AA');
  const matterFilter = page.getByPlaceholder('搜索事项编号、标题或负责人');
  await expect(matterFilter).toHaveValue('导航');
  await expect(matterTitleButton(page, '导航恢复测试事项')).toBeVisible();
  await expect(matterTitleButton(page, '员工手册版本确认')).toHaveCount(0);

  await page.reload();

  await expect(matterFilter).toHaveValue('导航');
  await expect(matterTitleButton(page, '导航恢复测试事项')).toBeVisible();
  await expect(matterTitleButton(page, '员工手册版本确认')).toHaveCount(0);
});

test('desktop and mobile shell label demo data without a connection status marker', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/today');

  await expect(page.locator('.sync-dot')).toHaveCount(0);
  await expect(page.getByText('本地演示 · 不代表连接或同步状态', { exact: true })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '打开导航' }).click();
  await expect(page.getByText('本地演示 · 不代表连接或同步状态', { exact: true })).toBeVisible();
});

test('1024 collapsed navigation hides group-name fragments and keeps group separation', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto('/today');

  const sider = page.locator('.app-sider');
  await expect(sider).toHaveClass(/ant-layout-sider-collapsed/);
  await expect(sider.locator('.ant-menu-item-group-title')).toHaveCount(3);
  await expect(sider.locator('.ant-menu-item-group-title').filter({ hasText: '资料与模板' })).toBeHidden();
  await expect(sider.locator('.ant-menu-item-group-title').filter({ hasText: '系统与审计' })).toBeHidden();
  await expect(sider.locator('.ant-menu-item-group').nth(1)).toHaveCSS('border-top-style', 'solid');
});

test('mobile shell uses the human-review inbox name after navigation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/today');

  await page.getByRole('button', { name: '打开导航' }).click();
  await page.getByRole('navigation', { name: '主导航' }).getByRole('menuitem', { name: '待确认消息' }).click();

  await expect(page.locator('.mobile-page-name')).toHaveText('待确认消息');
});

test('browser back restores the complete matters query', async ({ page }) => {
  await page.goto('/matters?q=%E5%AF%BC%E8%88%AA&risk=high&status=in_progress');
  const matterFilter = page.getByPlaceholder('搜索事项编号、标题或负责人');
  await expect(matterFilter).toHaveValue('导航');
  await expect(matterTitleButton(page, '员工手册版本确认')).toHaveCount(0);
  await page.getByRole('menuitem', { name: '事项模板' }).click();
  await expect(page).toHaveURL(/\/templates$/);

  await page.goBack();

  await expect(page).toHaveURL('/matters?q=%E5%AF%BC%E8%88%AA&risk=high&status=in_progress');
  await expect(page.getByRole('heading', { name: '法务事项中心' })).toBeVisible();
  await expect(matterFilter).toHaveValue('导航');
  await expect(matterTitleButton(page, '导航恢复测试事项')).toBeVisible();
  await expect(matterTitleButton(page, '员工手册版本确认')).toHaveCount(0);
});

test('refreshing a matter detail keeps the same matter route and content', async ({ page }) => {
  await page.goto('/matters/matter-navigation');

  await expect(page.getByRole('heading', { name: matter.title })).toBeVisible();
  await page.reload();

  await expect(page).toHaveURL(/\/matters\/matter-navigation$/);
  await expect(page.getByRole('heading', { name: matter.title })).toBeVisible();
});

test('the application shell has no page-level overflow at required viewports', async ({ page }) => {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1024, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/today');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
  }
});

test('shared status tags expose their risk semantics and keyboard focus remains visible', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/today');

  const riskTag = page.getByText('严重风险', { exact: true }).first();
  await expect(riskTag).toHaveAttribute('data-status-kind', 'risk');
  await expect(riskTag).toHaveAttribute('data-status-tone', 'critical');

  await page.keyboard.press('Tab');
  const keyboardFocus = page.locator(':focus-visible');
  await expect(keyboardFocus).toHaveCount(1);
  await expect(keyboardFocus).toHaveCSS('outline-width', '2px');
  await expect(keyboardFocus).toHaveCSS('outline-style', 'solid');
});

test('dashboard uses the shared header and a demo data boundary without claiming live service data', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/today');

  await expect(page.locator('.page-header')).toContainText('今日工作台');
  await expect(page.locator('[data-boundary-variant="demo"]')).toContainText('演示数据 / 非实时业务事实');
  await expect(page.locator('.page-header').getByRole('button', { name: '处理待确认消息' })).toHaveJSProperty('offsetHeight', 44);
});

test('template directory exposes only category-filter navigation while unsupported configuration stays disabled', async ({ page }) => {
  const consoleMessages: string[] = [];
  page.on('console', (message) => consoleMessages.push(message.text()));

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/templates');
  await expect(page.getByRole('heading', { name: '事项模板（演示）' })).toBeVisible();
  await expect(page.locator('[data-boundary-variant="demo"]')).toContainText('安全演示数据');
  await expect(page.getByRole('button', { name: '新建事项类型（后端未接入）' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '配置合同审核模板（后端未接入）' })).toBeDisabled();
  const firstMeta = page.locator('.template-directory .ant-list-item-meta').first();
  expect((await firstMeta.boundingBox())?.width).toBeGreaterThan(250);
  expect((await firstMeta.getByText('合同审核', { exact: true }).boundingBox())?.height).toBeLessThan(40);
  await page.getByRole('button', { name: '查看合同审核事项' }).click();
  await expect(page).toHaveURL('/matters?category=contract');
  expect(consoleMessages).not.toContainEqual(expect.stringContaining('[antd: Card] bordered is deprecated'));
  expect(consoleMessages).not.toContainEqual(expect.stringContaining('validateDOMNesting'));
});

test('mobile unavailable alternatives wrap inside the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/files');

  const alternative = page.getByRole('button', { name: '当前可在法务事项中查看已确认的事项和行动任务' });
  const box = await alternative.boundingBox();
  expect(box?.x).toBeGreaterThanOrEqual(16);
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(374);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('unavailable and unknown routes use shared states with safe next steps', async ({ page }) => {
  await page.goto('/files');
  const filesState = page.locator('.unavailable-state--files');
  await expect(filesState).toContainText('合同与文件尚未接入');
  await expect(filesState).toContainText('目的：集中管理合同与附件');
  await expect(filesState).toContainText('当前限制：文件内容尚未存储或检索');
  await expect(filesState).toContainText('当前可在法务事项中查看已确认的事项和行动任务');
  await expect(filesState).toContainText('后端缺口：文件存储与检索接口');

  await page.goto('/system/about');
  const aboutState = page.locator('.unavailable-state--about');
  await expect(aboutState).toContainText('系统信息尚未接入');
  await expect(aboutState).toContainText('目的：核验本地运行环境与版本边界');
  await expect(aboutState).toContainText('当前限制：没有可核验的版本、连接或运行状态接口');
  await expect(aboutState).toContainText('当前可查看数据边界与已实现能力');

  await page.goto('/not-a-real-route');
  const notFoundState = page.locator('.state-panel--unavailable');
  await expect(notFoundState).toContainText('页面不存在');
  await expect(notFoundState.getByRole('button', { name: '返回今日工作台' })).toBeVisible();
});
