import { expect, test, type Page } from '@playwright/test';

const prohibitedUnverifiedFacts = ['正常', '在线', '同步成功', '42 个群聊'];
const unexpectedRequests = new WeakMap<Page, string[]>();

test.beforeEach(async ({ page }) => {
  unexpectedRequests.set(page, []);
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const entry = `${request.method()} ${url.pathname}${url.search}`;
    unexpectedRequests.get(page)?.push(entry);
    await route.fulfill({
      status: 501,
      contentType: 'application/json',
      body: JSON.stringify({ detail: `unexpected data-boundary request: ${entry}` }),
    });
  });
});

test.afterEach(async ({ page }) => {
  expect(unexpectedRequests.get(page) ?? []).toEqual([]);
});

test('data boundaries page separates coded safeguards from unavailable operational state', async ({ page }) => {
  await page.goto('/system/data-boundaries');

  const main = page.locator('.data-boundaries-page');
  await expect(main.getByRole('heading', { name: '数据边界' })).toBeVisible();
  await expect(main.getByText('未接入运行状态接口', { exact: true })).toBeVisible();
  await expect(main.getByRole('heading', { name: '已在界面与代码中落实的边界' })).toBeVisible();
  await expect(main.getByRole('heading', { name: '尚需后端支持' })).toBeVisible();
  await expect(main.getByText('进入外发队列不等于已发送', { exact: true })).toBeVisible();
  await expect(main.getByText('Agent 运行完成不等于法律结论已确认', { exact: true })).toBeVisible();

  for (const value of prohibitedUnverifiedFacts) {
    await expect(main.getByText(value, { exact: true })).toHaveCount(0);
  }
  await expect(main.locator('.ant-switch')).toHaveCount(0);
  await expect(main.getByRole('button')).toHaveCount(0);
});

test('data boundaries page does not invent audit rows or service health', async ({ page }) => {
  await page.goto('/system/data-boundaries');

  const main = page.locator('.data-boundaries-page');
  await expect(main.getByText('当前连接、授权范围、同步健康度和审计事件数量均不可从本页面验证。', { exact: true })).toBeVisible();
  await expect(main.getByRole('table')).toHaveCount(0);
  await expect(main.getByText('操作审计日志', { exact: true })).toHaveCount(0);
  await expect(main.locator('.ant-tag-green')).toHaveCount(0);
});

test('390px uses readable definition and gap cards without page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/system/data-boundaries');

  const main = page.locator('.data-boundaries-page');
  await expect(main.getByText('当前连接、授权范围、同步健康度和审计事件数量均不可从本页面验证。', { exact: true })).toBeVisible();
  await expect(main.locator('.boundary-capability-card').first()).toBeInViewport();
  await expect(main.locator('.boundary-gap-list')).toBeVisible();
  await expect(main.getByRole('table')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('network guard records and rejects undeclared status access', async ({ page }) => {
  await page.goto('/system/data-boundaries');
  const status = await page.evaluate(async () => (await fetch('/api/v1/system/health')).status);
  expect(status).toBe(501);
  expect(unexpectedRequests.get(page)).toEqual(['GET /api/v1/system/health']);
  unexpectedRequests.set(page, []);
});
