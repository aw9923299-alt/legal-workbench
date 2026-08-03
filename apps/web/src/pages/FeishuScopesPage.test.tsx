import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import FeishuScopesPage from './FeishuScopesPage';
import { legalApi } from '../services/api';
import type { FeishuScope } from '../types/api';

const scope: FeishuScope = {
  id: 'scope-1',
  provider: 'feishu',
  externalScopeId: 'oc_synthetic_scope',
  displayName: '合成测试群',
  status: 'unapproved',
  syncMode: 'disabled',
  lastMessageAt: null,
  lastErrorCode: null,
  lastErrorMessage: null,
  lastCompensatedAt: null,
  lastCompensationStatus: null,
  approvedBy: null,
  approvedAt: null,
  version: 1,
  createdAt: '2026-08-03T00:00:00Z',
  updatedAt: '2026-08-03T00:00:00Z',
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}><FeishuScopesPage /></QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('Feishu scopes page', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows unapproved chats as disabled and applies an allow decision with version', async () => {
    vi.spyOn(legalApi, 'listFeishuScopes').mockResolvedValue([scope]);
    const change = vi.spyOn(legalApi, 'changeFeishuScope').mockResolvedValue({
      ...scope,
      status: 'allowed',
      syncMode: 'mentions_only',
      version: 2,
    });

    renderPage();

    expect(await screen.findByText('合成测试群')).toBeInTheDocument();
    expect(screen.getByText('未批准')).toBeInTheDocument();
    expect(screen.getByText('不同步')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /仅 @机器人$/ }));

    await waitFor(() => expect(change).toHaveBeenCalledWith(
      'scope-1',
      1,
      { action: 'allow', syncMode: 'mentions_only' },
      expect.any(Object),
    ));
  });

  it('records compensation as deferred and never reports it as synchronized', async () => {
    vi.spyOn(legalApi, 'listFeishuScopes').mockResolvedValue([{ ...scope, status: 'allowed', syncMode: 'all_messages' }]);
    vi.spyOn(legalApi, 'compensateFeishuScope').mockResolvedValue({
      scope: { ...scope, status: 'allowed', syncMode: 'all_messages', version: 2, lastCompensationStatus: 'not_executed' },
      state: 'not_executed',
      errorCode: 'REAL_FEISHU_PHASE_DEFERRED',
      message: '真实飞书补偿同步按当前实施阶段延后。',
      correlationId: 'corr-deferred',
      idempotentReplay: false,
    });

    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /记录补偿请求$/ }));

    expect(await screen.findByText(/REAL_FEISHU_PHASE_DEFERRED/)).toBeInTheDocument();
    expect(screen.getByText(/Correlation ID：corr-deferred/)).toBeInTheDocument();
    expect(screen.queryByText('补偿同步成功')).not.toBeInTheDocument();
  });
});
