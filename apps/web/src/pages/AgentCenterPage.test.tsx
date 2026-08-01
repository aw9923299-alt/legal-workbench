import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { legalApi } from '../services/api';
import type { AgentRunRecord } from '../types/api';
import AgentCenterPage from './AgentCenterPage';

function run(status: AgentRunRecord['status']): AgentRunRecord {
  return {
    id: '11111111-1111-4111-8111-111111111111', agentKey: 'message_triage', agentVersion: '2.0.0',
    feishuMessageId: null, contextSnapshotId: '22222222-2222-4222-8222-222222222222', status,
    objective: 'triage', inputPayload: {}, outputPayload: null, rawStdout: null, rawStderr: null,
    promptSnapshot: '', workingDirectory: '[runtime]/run', startedAt: '2026-08-01T10:00:00Z',
    heartbeatAt: null, finishedAt: status === 'completed' ? '2026-08-01T10:00:02Z' : null,
    timeoutAt: null, attemptNumber: 1, maxAttempts: 3, failureCode: null, failureMessage: null,
    runtimeVersion: '0.146.0', agentDefinitionVersion: '2.0.0', promptVersion: '2.0.0',
    validationErrors: [], repairAttempted: false, tokenUsage: null, workerId: 'worker-1', leaseExpiresAt: null,
    correlationId: 'corr-run', createdBy: 'system', createdAt: '2026-08-01T10:00:00Z',
    updatedAt: '2026-08-01T10:00:00Z', version: 1, sources: [], statusEvents: [], candidateId: null,
  };
}

describe('Agent run center', () => {
  afterEach(() => vi.restoreAllMocks());

  it('refreshes a running row to its completed durable state', async () => {
    vi.spyOn(legalApi, 'listAgentRuns').mockResolvedValueOnce([run('running')]).mockResolvedValueOnce([run('completed')]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<MemoryRouter><QueryClientProvider client={client}><AgentCenterPage /></QueryClientProvider></MemoryRouter>);
    expect(await screen.findByText('running')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /刷新/ }));
    expect(await screen.findByText('completed')).toBeInTheDocument();
  });
});
