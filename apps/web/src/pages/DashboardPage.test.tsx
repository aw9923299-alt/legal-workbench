import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, legalApi } from '../services/api';
import type { DashboardToday } from '../types/api';
import DashboardPage from './DashboardPage';

const dashboard: DashboardToday = {
  generatedAt: '2026-08-03T09:00:00+08:00',
  todayMustHandle: [{
    id: 'work-1', group: 'today_must_handle', objectType: 'work_item', title: '真实硬期限任务',
    description: '准备答辩材料', href: '/matters/matter-1', status: 'in_progress',
    createdAt: '2026-08-01T09:00:00+08:00', dueAt: '2026-08-03T18:00:00+08:00',
    isHardDeadline: true, isOverdue: false, legalRisk: 'high', confirmedPriority: 'urgent',
    aiSuggestedPriority: 'low', waitingSince: null, waitingSeconds: 0,
    rankingReasons: ['今日到期', '硬期限', '法律风险: high', '人工确认优先级: urgent'],
  }],
  overdue: [],
  pendingCandidates: [],
  analysisFailed: [],
  waitingOthers: [],
  upcomingDeadlines: [],
  pendingOutboundReview: [],
  systemAbnormal: [],
};

describe('Daily legal dashboard', () => {
  afterEach(() => vi.restoreAllMocks());

  it('renders PostgreSQL queue items and their deterministic ranking reasons', async () => {
    vi.spyOn(legalApi, 'getDashboardToday').mockResolvedValue(dashboard);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <MemoryRouter>
        <QueryClientProvider client={client}><DashboardPage /></QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('真实硬期限任务')).toBeInTheDocument();
    expect(screen.getByText('硬期限')).toBeInTheDocument();
    expect(screen.getByText('人工确认优先级: urgent')).toBeInTheDocument();
    expect(screen.queryByText('头部主播解约与竞业限制风险评估')).not.toBeInTheDocument();
  });

  it('shows a retryable empty queue instead of fabricated work', async () => {
    vi.spyOn(legalApi, 'getDashboardToday').mockResolvedValue({
      ...dashboard,
      todayMustHandle: [],
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <MemoryRouter>
        <QueryClientProvider client={client}><DashboardPage /></QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('当前队列为空')).toBeInTheDocument();
  });

  it('shows the correlation ID and recovers when the user retries', async () => {
    const request = vi.spyOn(legalApi, 'getDashboardToday')
      .mockRejectedValueOnce(new ApiError('加载工作队列失败', 500, 'dashboard_failed', 'corr-dashboard'))
      .mockResolvedValueOnce(dashboard);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <MemoryRouter>
        <QueryClientProvider client={client}><DashboardPage /></QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('加载工作队列失败')).toBeInTheDocument();
    expect(screen.getByText('Correlation ID：corr-dashboard')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));

    expect(await screen.findByText('真实硬期限任务')).toBeInTheDocument();
    expect(request).toHaveBeenCalledTimes(2);
  });
});
