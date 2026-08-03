import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import SystemStatusPage from './SystemStatusPage';
import { legalApi } from '../services/api';

describe('System status page', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows disk, backup, recovery and dead-letter facts from the status API', async () => {
    vi.spyOn(legalApi, 'getSystemHealth').mockResolvedValue({
      generatedAt: '2026-08-03T08:30:00Z',
      components: {
        fastapi: { status: 'normal', detail: 'ready', updatedAt: '2026-08-03T08:30:00Z' },
        postgresql: { status: 'normal', detail: 'ready', updatedAt: '2026-08-03T08:30:00Z' },
        redis: { status: 'normal', detail: 'ready', updatedAt: '2026-08-03T08:30:00Z' },
        celery_worker: { status: 'normal', detail: 'ready', updatedAt: '2026-08-03T08:30:00Z' },
        celery_scheduler: { status: 'normal', detail: 'ready', updatedAt: '2026-08-03T08:30:00Z' },
        disk: { status: 'normal', detail: 'ready', updatedAt: '2026-08-03T08:30:00Z' },
        backup: { status: 'normal', detail: 'ready', updatedAt: '2026-08-03T08:30:00Z' },
      },
      metrics: {
        outboxPending: 1,
        agentQueued: 2,
        pendingRecovery: 3,
        failedRuns: 4,
        agentDeadLetters: 5,
        outboxDeadLetters: 6,
        lastMessageAt: '2026-08-03T08:00:00Z',
        lastCompletedRunAt: '2026-08-03T08:05:00Z',
        lastReconcileAt: null,
        lastCandidateAt: null,
        lastAgentRunUpdateAt: null,
        lastOutboxFailureAt: null,
        diskFreeBytes: 10 * 1024 * 1024 * 1024,
        diskTotalBytes: 20 * 1024 * 1024 * 1024,
        attachmentBytesUsed: 256 * 1024 * 1024,
        attachmentQuotaBytes: 5 * 1024 * 1024 * 1024,
        lastBackupAt: '2026-08-03T01:00:00Z',
        lastBackupStatus: 'succeeded',
        lastWakeCheckAt: '2026-08-03T08:20:00Z',
      },
      codex: {
        enabled: false,
        status: 'unauthenticated',
        executable: '/opt/codex',
        detectedVersion: '0.146.0',
        expectedVersion: '0.146.0',
        authentication: 'not_provided',
        runtimeDirectoryWritable: true,
        detail: 'Worker authentication is absent.',
      },
    });
    vi.spyOn(legalApi, 'getFeishuStatus').mockResolvedValue({
      integrationType: 'feishu',
      connectionMode: 'long_connection',
      status: 'disabled',
      lastConnectedAt: null,
      lastDisconnectedAt: null,
      lastEventAt: null,
      lastErrorCode: 'REAL_FEISHU_PHASE_DEFERRED',
      lastErrorMessage: 'not executed',
      reconnectCount: 0,
      lastReconcileAt: null,
      lastReconcileStatus: 'not_executed',
      lastReconcileMessage: 'deferred',
      updatedAt: '2026-08-03T08:30:00Z',
    });
    vi.spyOn(legalApi, 'listOutboxDeadLetters').mockResolvedValue([]);
    vi.spyOn(legalApi, 'listAgentRuns').mockResolvedValue([]);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}><SystemStatusPage /></QueryClientProvider>,
    );

    expect(await screen.findByText('待恢复任务')).toBeInTheDocument();
    expect(screen.getByText('10.0 GB')).toBeInTheDocument();
    expect(screen.getByText(/256.0 MB \/ 5.0 GB/)).toBeInTheDocument();
    expect(screen.getByText(/succeeded/)).toBeInTheDocument();
  });

  it('does not present zero recovery work when PostgreSQL metrics are unavailable', async () => {
    vi.spyOn(legalApi, 'getSystemHealth').mockResolvedValue({
      generatedAt: '2026-08-03T08:30:00Z',
      components: {
        postgresql: { status: 'unavailable', detail: 'unreachable', updatedAt: '2026-08-03T08:30:00Z' },
      },
      metrics: null,
      codex: {
        enabled: false,
        status: 'unauthenticated',
        executable: null,
        detectedVersion: null,
        expectedVersion: '0.146.0',
        authentication: 'not_provided',
        runtimeDirectoryWritable: false,
        detail: 'unavailable',
      },
    });
    vi.spyOn(legalApi, 'getFeishuStatus').mockResolvedValue({
      integrationType: 'feishu',
      connectionMode: 'long_connection',
      status: 'disabled',
      lastConnectedAt: null,
      lastDisconnectedAt: null,
      lastEventAt: null,
      lastErrorCode: 'REAL_FEISHU_PHASE_DEFERRED',
      lastErrorMessage: 'not executed',
      reconnectCount: 0,
      lastReconcileAt: null,
      lastReconcileStatus: 'not_executed',
      lastReconcileMessage: 'deferred',
      updatedAt: '2026-08-03T08:30:00Z',
    });
    vi.spyOn(legalApi, 'listOutboxDeadLetters').mockResolvedValue([]);
    vi.spyOn(legalApi, 'listAgentRuns').mockResolvedValue([]);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}><SystemStatusPage /></QueryClientProvider>,
    );

    const label = await screen.findByText('待恢复任务');
    const card = label.closest('.ant-card');
    expect(card).not.toBeNull();
    expect(within(card as HTMLElement).getByText('未知')).toBeInTheDocument();
  });
});
