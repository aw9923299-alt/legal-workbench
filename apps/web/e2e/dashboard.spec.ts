import { expect, test } from '@playwright/test';

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'compact desktop', width: 1024, height: 768 },
  { name: 'mobile', width: 390, height: 844 },
];

test('default dashboard keeps its context and action queue within every required viewport', async ({ page }) => {
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.goto('/');

    await expect(page.getByRole('heading', { name: '今日工作台' })).toBeInViewport();
    await expect(page.getByRole('heading', { name: '下一步工作队列' })).toBeInViewport();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
  }
});

test('mobile navigation exposes the confirmation action', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');

  await page.getByRole('button', { name: '打开导航' }).click();
  const navigation = page.getByRole('navigation', { name: '主导航' });
  await expect(navigation).toBeVisible();
  await expect(navigation.getByRole('button', { name: '处理待确认消息' })).toBeVisible();
});

test('dashboard does not present demonstration data as verified live service status', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByText('飞书同步正常', { exact: true })).toHaveCount(0);
  await expect(page.getByText('本地服务已连接', { exact: true })).toHaveCount(0);
  await expect(page.getByText('在线', { exact: true })).toHaveCount(0);
});

test('dashboard marks AI advice for human checking and exposes keyboard focus from Tab navigation', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/today');

  const aiStatus = page.getByText('AI 建议 · 需人工核对', { exact: true });
  await expect(aiStatus).toHaveAttribute('data-status-kind', 'ai');
  await expect(aiStatus).toHaveAttribute('data-status-tone', 'ai');

  await page.keyboard.press('Tab');
  const keyboardFocus = page.locator(':focus-visible');
  await expect(keyboardFocus).toHaveCount(1);
  await expect(keyboardFocus).toHaveCSS('outline-width', '2px');
  await expect(keyboardFocus).toHaveCSS('outline-style', 'solid');
});

test('focus queue badge and visible task members use the same priority rule', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  await expect(page.getByRole('tab', { name: /应立即处理 4/ })).toBeVisible();
  await expect(page.locator('.task-table-desktop .ant-table-tbody > tr')).toHaveCount(4);
  await expect(page.getByText('本周', { exact: true })).toHaveCount(0);
});

test('compact viewport keeps the complete task decision and entry action reachable', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto('/');

  const firstTask = page.locator('.task-compact-card').first();
  await expect(page.locator('.task-table-desktop')).toBeHidden();
  await expect(firstTask.getByRole('heading')).toBeInViewport();
  await expect(firstTask.getByText('严重风险', { exact: true })).toBeInViewport();
  await expect(firstTask.getByText('期限', { exact: true })).toBeInViewport();
  await expect(firstTask.getByText('负责人', { exact: true })).toBeInViewport();
  await expect(firstTask.getByText('下一步', { exact: true })).toBeInViewport();
  await expect(firstTask.getByRole('button', { name: '进入事项中心' })).toBeInViewport();
});

test('tablet breakpoint keeps the first task decision and entry action reachable without overflow', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 768 });
  await page.goto('/today');

  const firstTask = page.locator('.task-compact-card:visible, .task-mobile-card:visible').first();
  await expect(firstTask.getByRole('heading')).toBeInViewport();
  await expect(firstTask.getByText('严重风险', { exact: true })).toBeInViewport();
  await expect(firstTask.getByText('负责人', { exact: true })).toBeInViewport();
  await expect(firstTask.getByText('下一步', { exact: true })).toBeInViewport();
  await expect(firstTask.getByRole('button', { name: '进入事项中心' })).toBeInViewport();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(768);
});

test('1000px uses the mobile task renderer with the complete decision reachable', async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 768 });
  await page.goto('/today');

  const collection = page.locator('.responsive-collection').first();
  const firstTask = collection.locator('.task-mobile-card').first();
  await expect(collection.locator('.responsive-collection__mobile')).toBeVisible();
  await expect(collection.locator('.responsive-collection__compact')).toBeHidden();
  await expect(firstTask.getByRole('heading')).toBeInViewport();
  await expect(firstTask.getByText('严重风险', { exact: true })).toBeInViewport();
  await expect(firstTask.getByText('负责人', { exact: true })).toBeInViewport();
  await expect(firstTask.getByText('下一步', { exact: true })).toBeInViewport();
  await expect(firstTask.getByRole('button', { name: '进入事项中心' })).toBeInViewport();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1000);
});

test('1001px uses the compact task renderer with the complete decision reachable', async ({ page }) => {
  await page.setViewportSize({ width: 1001, height: 768 });
  await page.goto('/today');

  const collection = page.locator('.responsive-collection').first();
  const firstTask = collection.locator('.task-compact-card').first();
  await expect(collection.locator('.responsive-collection__compact')).toBeVisible();
  await expect(collection.locator('.responsive-collection__mobile')).toBeHidden();
  await expect(firstTask.getByRole('heading')).toBeInViewport();
  await expect(firstTask.getByText('严重风险', { exact: true })).toBeInViewport();
  await expect(firstTask.getByText('负责人', { exact: true })).toBeInViewport();
  await expect(firstTask.getByText('下一步', { exact: true })).toBeInViewport();
  await expect(firstTask.getByRole('button', { name: '进入事项中心' })).toBeInViewport();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1001);
});

test('mobile first task exposes its title and risk within the initial viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');

  const firstTask = page.locator('.task-mobile-card').first();
  await expect(firstTask.getByRole('heading')).toBeInViewport();
  await expect(firstTask.getByText('严重风险', { exact: true })).toBeInViewport();
});

test('task collection uses its compact and mobile renderers without page overflow', async ({ page }) => {
  for (const viewport of [
    { width: 1024, height: 768, renderer: '.responsive-collection__compact' },
    { width: 390, height: 844, renderer: '.responsive-collection__mobile' },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/today');

    const collection = page.locator('.responsive-collection').first();
    await expect(collection).toBeVisible();
    await expect(collection.locator(viewport.renderer)).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
  }
});

test('mobile controls provide 44px touch targets', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');

  const menuButton = page.getByRole('button', { name: '打开导航' });
  await expect(menuButton).toHaveJSProperty('offsetHeight', 44);
  await expect(menuButton).toHaveJSProperty('offsetWidth', 44);
  await menuButton.click();

  const navigation = page.getByRole('navigation', { name: '主导航' });
  await expect(navigation.getByRole('menuitem', { name: /今日工作台/ })).toHaveJSProperty('offsetHeight', 44);
  await expect(navigation.getByRole('button', { name: '处理待确认消息' })).toHaveJSProperty('offsetHeight', 44);
  await expect(page.locator('.task-mobile-card').first().getByRole('button', { name: '进入事项中心' })).toHaveJSProperty('offsetHeight', 44);
});

test('dashboard keeps readable metadata, a 24px title, and no Card deprecation warning', async ({ page }) => {
  const consoleMessages: string[] = [];
  page.on('console', (message) => consoleMessages.push(message.text()));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  await expect(page.getByRole('heading', { name: '今日工作台' })).toHaveCSS('font-size', '24px');
  await expect(page.locator('.metric-hint').first()).toHaveCSS('color', 'rgb(101, 112, 131)');
  await expect(page.locator('.task-id').first()).toHaveCSS('color', 'rgb(101, 112, 131)');
  expect(consoleMessages).not.toContainEqual(expect.stringContaining('[antd: Card] bordered is deprecated'));
});

test('dashboard primary action and demonstration messages enter the confirmation workflow', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/today');

  await page.getByRole('button', { name: '处理待确认消息' }).click();
  await expect(page).toHaveURL('/inbox');

  await page.goBack();
  await page.locator('button.inbox-mini-item').first().click();
  await expect(page).toHaveURL('/inbox');
});

test('dashboard keeps its action queue ahead of secondary metrics and human-checkable AI advice', async ({ page }) => {
  await page.goto('/today');

  const queue = page.getByRole('heading', { name: '下一步工作队列' });
  const metrics = page.locator('.metric-strip');
  const advice = page.getByRole('heading', { name: 'AI 建议（演示）' });
  await expect(queue).toBeVisible();
  await expect(advice).toBeVisible();
  const positions = await page.evaluate(() => {
    const queue = document.querySelector('.work-queue-card');
    const metrics = document.querySelector('.metric-strip');
    const advice = document.querySelector('.assistant-panel');
    if (!queue || !metrics || !advice) return undefined;
    return [queue.compareDocumentPosition(metrics), advice.compareDocumentPosition(queue)];
  });
  expect((positions?.[0] ?? 0) & 4).toBeTruthy();
  expect((positions?.[1] ?? 0) & 2).toBeTruthy();
  await expect(metrics).toContainText('演示快照口径');
});
