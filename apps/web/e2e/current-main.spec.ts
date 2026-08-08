import { expect, test, type Page } from '@playwright/test';

async function installUnavailableApi(page: Page): Promise<string[]> {
  const requests: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    requests.push(`${request.method()} ${pathname}`);
    if (pathname === '/api/v1/auth/session') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ actorId: 'e2e-legal-reviewer', identitySource: 'e2e-session' }),
      });
      return;
    }
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        error: {
          code: 'SERVICE_UNAVAILABLE',
          message: 'Dependency is unavailable.',
          details: {},
          correlationId: 'e2e-current-main',
        },
      }),
    });
  });
  return requests;
}

test('current main shell keeps API failures explicit across primary routes', async ({ page }) => {
  const requests = await installUnavailableApi(page);

  await page.goto('/');
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('heading', { name: '今日工作台' })).toBeVisible();
  await expect(page.getByText('服务不可用', { exact: true })).toBeVisible();

  await page.getByRole('menuitem', { name: 'AI 收件箱' }).click();
  await expect(page).toHaveURL(/\/inbox$/);
  await expect(page.getByRole('heading', { name: 'AI 收件箱' })).toBeVisible();
  await expect(page.getByText('服务不可用', { exact: true })).toBeVisible();

  expect(requests).toContain('GET /api/v1/dashboard/today');
  expect(requests.some((request) => request.startsWith('GET /api/v1/feishu/messages'))).toBe(true);
});

test('current main exposes operational routes without falling back to legacy paths', async ({ page }) => {
  await installUnavailableApi(page);

  await page.goto('/setup');
  await expect(page.getByRole('heading', { name: '首次配置' })).toBeVisible();

  await page.goto('/system');
  await expect(page.getByRole('heading', { name: '系统状态' })).toBeVisible();
  await expect(page.getByText('服务不可用', { exact: true }).first()).toBeVisible();

  await page.goto('/security');
  await expect(page.getByRole('heading', { name: '数据边界' })).toBeVisible();
});
