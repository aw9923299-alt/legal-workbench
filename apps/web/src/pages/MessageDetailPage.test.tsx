import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { legalApi } from '../services/api';
import type { FeishuMessageDetail, MessageAnalysis, MessageCandidate } from '../types/api';
import MessageDetailPage from './MessageDetailPage';

const messageId = '11111111-1111-4111-8111-111111111111';
const candidateId = '22222222-2222-4222-8222-222222222222';
const analysisResult = {
  legalRelevance: 'relevant' as const, messageRole: 'new_request' as const, actionability: 'create_candidate' as const,
  suggestedTitle: '审核合作合同', categoryCandidates: [{ category: 'contract' as const, confidence: 0.9, reason: '明确请求' }],
  deadlineCandidates: [], confirmedFacts: [{ statement: '原文明确要求审核', sourceMessageId: 'om_1' }],
  inferredFacts: [{ statement: '可能存在时间压力', basis: '使用尽快', confidence: 0.6 }],
  missingInformation: ['合同附件'], reasons: ['需要法务行动'], confidence: 0.82,
};
const run = {
  id: '33333333-3333-4333-8333-333333333333', agentKey: 'message_triage', agentVersion: '2.0.0',
  feishuMessageId: messageId, contextSnapshotId: '44444444-4444-4444-8444-444444444444', status: 'completed' as const,
  objective: 'triage', inputPayload: {}, outputPayload: analysisResult, rawStdout: '', rawStderr: '', promptSnapshot: '',
  workingDirectory: '[runtime]/run', startedAt: '2026-08-01T10:00:00Z', heartbeatAt: null,
  finishedAt: '2026-08-01T10:00:01Z', timeoutAt: null, attemptNumber: 1, maxAttempts: 3,
  failureCode: null, failureMessage: null, runtimeVersion: '0.146.0', agentDefinitionVersion: '2.0.0',
  promptVersion: '2.0.0', validationErrors: [], repairAttempted: false, tokenUsage: null, workerId: 'worker-1',
  leaseExpiresAt: null, correlationId: 'corr-detail', createdBy: 'system', createdAt: '2026-08-01T10:00:00Z',
  updatedAt: '2026-08-01T10:00:01Z', version: 1, sources: [], statusEvents: [], candidateId,
};

describe('Message detail workflow', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows source evidence, AI inference and human confirmation actions separately', async () => {
    vi.spyOn(legalApi, 'getMessage').mockResolvedValue({
      id: messageId, messageId: 'om_1', tenantKey: 'tenant', chatId: 'chat-1', threadId: null,
      parentMessageId: null, rootMessageId: null, senderId: 'ou_business', senderType: 'user', messageType: 'text',
      plainText: '请法务尽快审核合作合同', sentAt: '2026-08-01T10:00:00Z', editedAt: null, recalledAt: null,
      status: 'candidate_created', unsupportedReason: null, analysisAttempts: 1, failureCode: null, failureMessage: null,
      agentRunId: run.id, agentStatus: 'completed', candidateId, candidateStatus: 'pending_confirmation', confidence: 0.82,
      suggestedCategory: 'contract', suggestedDeadline: null, structuredContent: {}, rawPayload: { event: 'redacted-test' },
      contextMessages: [], versions: [], attachments: [], candidateRevisions: [],
    } satisfies FeishuMessageDetail);
    vi.spyOn(legalApi, 'getMessageAnalysis').mockResolvedValue({
      message: { id: messageId, messageId: 'om_1', senderId: 'ou_business', messageType: 'text', content: {}, createTime: '2026-08-01T10:00:00Z' },
      messageStatus: 'candidate_created', contextSnapshot: null, agentRun: run, analysisResult, candidateId,
      failureCode: null, failureMessage: null, canRetry: true,
    } satisfies MessageAnalysis);
    vi.spyOn(legalApi, 'getCandidate').mockResolvedValue({
      id: candidateId, contextSnapshotId: run.contextSnapshotId, status: 'pending_confirmation', legalRelevance: 'relevant',
      messageRole: 'new_request', recommendedAction: 'create_matter', confidence: 0.82, titleProposal: '审核合作合同',
      categoryProposals: [], deadlineProposals: [], relatedMatterProposals: [], evidenceRefs: ['om_1'], agentRunId: run.id,
      feishuMessageId: messageId, requiresManualReview: true, analysisPayload: analysisResult, confirmedBy: null, confirmedAt: null, version: 1,
    } satisfies MessageCandidate);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<MemoryRouter initialEntries={[`/inbox/${messageId}`]}><QueryClientProvider client={client}><Routes><Route path="/inbox/:messageId" element={<MessageDetailPage />} /></Routes></QueryClientProvider></MemoryRouter>);
    expect(await screen.findByText('请法务尽快审核合作合同')).toBeInTheDocument();
    expect(await screen.findByText('原文明确要求审核')).toBeInTheDocument();
    expect(await screen.findByText('可能存在时间压力')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '创建新 Matter' })).toBeInTheDocument();
    expect(screen.getByText(/AI 建议不会覆盖/)).toBeInTheDocument();
  });
});
