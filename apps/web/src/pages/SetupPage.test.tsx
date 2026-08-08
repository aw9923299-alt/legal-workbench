import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { legalApi } from '../services/api';
import type { SetupComponent, SetupStatus } from '../types/api';
import SetupPage from './SetupPage';

const deferred: SetupComponent = {
  state: 'not_executed',
  message: '真实飞书阶段尚未执行。',
  correlationId: 'corr-setup-status',
  errorCode: 'REAL_FEISHU_PHASE_DEFERRED',
};

const ready: SetupComponent = {
  state: 'ready',
  message: '已就绪。',
  correlationId: 'corr-setup-status',
  errorCode: null,
};

const status: SetupStatus = {
  generatedAt: '2026-08-03T10:00:00Z',
  correlationId: 'corr-setup-status',
  overallState: 'not_executed',
  basicServices: { api: 'ready', postgresql: 'ready', redis: 'ready', worker: 'ready', scheduler: 'ready' },
  feishu: {
    credentials: {
      configured: true,
      appIdMasked: 'cli••••123',
      secretMasked: '••••cret',
      lastValidationStatus: null,
      lastErrorCode: null,
    },
    permissions: deferred,
    scopes: { ...ready, message: '已记录 1 个群聊范围。' },
    connection: deferred,
    testMessage: deferred,
    manualUnreadAcceptance: deferred,
    eventSource: 'long_connection',
    receiveDirectMessages: true,
    groupMentionsOnly: true,
    configuredGroupAllMessages: true,
    allowedScopeCount: 1,
    excludedScopeCount: 0,
  },
  codex: {
    cli: ready,
    version: ready,
    authentication: {
      ...deferred,
      state: 'unauthenticated',
      message: 'Worker 尚未认证。',
      errorCode: 'CODEX_UNAUTHENTICATED',
    },
    smokeTest: {
      ...deferred,
      message: '尚未执行真实 Codex 冒烟。',
      errorCode: 'CODEX_SMOKE_TEST_NOT_EXECUTED',
    },
    expectedVersion: '0.146.0',
    detectedVersion: '0.146.0',
  },
  steps: [
    ['basic_services', '基础服务', ready],
    ['feishu_credentials', '飞书凭证', deferred],
    ['feishu_permissions', '飞书权限', deferred],
    ['feishu_scopes', '群聊范围', ready],
    ['feishu_connection', '长连接', deferred],
    ['codex_version', 'Codex 版本', ready],
    ['codex_authentication', 'Codex 认证', deferred],
    ['test_message', '测试消息', deferred],
    ['completion', '完成状态', deferred],
  ].map(([key, title, component], index) => ({
    number: index + 1,
    key: String(key),
    title: String(title),
    component: component as SetupComponent,
  })),
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}><SetupPage /></QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('Setup page', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('renders all nine persisted steps and exact deferred evidence', async () => {
    vi.spyOn(legalApi, 'getSetupStatus').mockResolvedValue(status);

    renderPage();

    expect(await screen.findByText('1. 基础服务')).toBeInTheDocument();
    expect(screen.getByText('9. 完成状态')).toBeInTheDocument();
    expect(screen.getAllByText(/REAL_FEISHU_PHASE_DEFERRED/).length).toBeGreaterThan(0);
    expect(screen.getByText('cli••••123')).toBeInTheDocument();
    expect(screen.getByText('••••cret')).toBeInTheDocument();
    expect(screen.getByText(/不会自动声称该项通过/)).toBeInTheDocument();
  });

  it('clears the write-only secret and never presents deferred Feishu as success', async () => {
    vi.spyOn(legalApi, 'getSetupStatus').mockResolvedValue(status);
    const validate = vi.spyOn(legalApi, 'validateFeishuSetup').mockResolvedValue({
      state: 'not_executed',
      message: '本阶段不执行真实飞书验证。',
      correlationId: 'corr-feishu-deferred',
      errorCode: 'REAL_FEISHU_PHASE_DEFERRED',
    });

    renderPage();
    const secret = await screen.findByLabelText('Feishu App Secret（仅写入）');
    fireEvent.change(secret, { target: { value: 'must-clear-secret' } });
    fireEvent.click(screen.getByRole('button', { name: /验证凭证/ }));

    await waitFor(() => expect(validate).toHaveBeenCalledWith({
      appId: undefined,
      appSecret: 'must-clear-secret',
    }));
    await waitFor(() => expect(secret).toHaveValue(''));
    expect(await screen.findByText(/本阶段不执行真实飞书验证/)).toBeInTheDocument();
    expect(screen.getByText('Correlation ID：corr-feishu-deferred')).toBeInTheDocument();
    expect(screen.queryByText(/连接成功/)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('must-clear-secret')).not.toBeInTheDocument();
  });

  it('queues Codex validation through the backend worker API', async () => {
    vi.spyOn(legalApi, 'getSetupStatus').mockResolvedValue(status);
    const validate = vi.spyOn(legalApi, 'validateCodexSetup').mockResolvedValue({
      checkRunId: 'check-1',
      state: 'pending',
      message: 'Codex 检查已提交给隔离 Worker。',
      correlationId: 'corr-codex-check',
      idempotentReplay: false,
    });

    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: '验证 Codex' }));

    await waitFor(() => expect(validate).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Codex 检查已提交给隔离 Worker/)).toBeInTheDocument();
    expect(screen.getByText('Correlation ID：corr-codex-check')).toBeInTheDocument();
  });
});
