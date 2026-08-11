import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { legalApi } from '../services/api';
import type {
  FeishuMessageDetail,
  LegalMatter,
  MessageAnalysis,
  MessageCandidate,
} from '../types/api';
import MessageDetailPage from './MessageDetailPage';

const messageId = '11111111-1111-4111-8111-111111111111';
const candidateId = '22222222-2222-4222-8222-222222222222';
const matterId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const snapshotId = '44444444-4444-4444-8444-444444444444';
const runId = '33333333-3333-4333-8333-333333333333';

const analysisResult = {
  legalRelevance: 'relevant' as const,
  messageRole: 'existing_matter_update' as const,
  actionability: 'link_candidate' as const,
  suggestedTitle: '补充合同材料',
  categoryCandidates: [{ category: 'contract' as const, confidence: 0.9, reason: '合同材料' }],
  deadlineCandidates: [],
  confirmedFacts: [{ statement: '业务补充合同', sourceMessageId: 'om_reply' }],
  inferredFacts: [],
  missingInformation: [],
  reasons: ['属于已有事项的新进展'],
  confidence: 0.92,
};

const run = {
  id: runId,
  agentKey: 'message_judgement',
  agentVersion: '2.2.0',
  feishuMessageId: messageId,
  contextSnapshotId: snapshotId,
  status: 'completed' as const,
  objective: 'triage',
  inputPayload: {},
  outputPayload: analysisResult,
  rawStdout: '',
  rawStderr: '',
  promptSnapshot: '',
  workingDirectory: '[runtime]/run',
  startedAt: '2026-08-11T10:00:00Z',
  heartbeatAt: null,
  finishedAt: '2026-08-11T10:00:01Z',
  timeoutAt: null,
  attemptNumber: 1,
  maxAttempts: 3,
  failureCode: null,
  failureMessage: null,
  runtimeVersion: '0.146.0',
  agentDefinitionVersion: '2.2.0',
  promptVersion: '2.2.0',
  validationErrors: [],
  repairAttempted: false,
  tokenUsage: null,
  workerId: 'worker-1',
  leaseExpiresAt: null,
  correlationId: 'corr-continuity',
  createdBy: 'system',
  createdAt: '2026-08-11T10:00:00Z',
  updatedAt: '2026-08-11T10:00:01Z',
  version: 1,
  sources: [],
  statusEvents: [],
  candidateId,
  matterId: null,
  workItemId: null,
  executionPlanId: null,
  planStepId: null,
  parentRunId: null,
  retryOfRunId: null,
  dependencyRunIds: [],
  runRole: 'standalone' as const,
};

const matter = {
  id: matterId,
  matterNumber: 'LW-20260811-AABBCCDD',
  title: '历史合同审核',
  primaryCategory: 'contract' as const,
  secondaryCategories: [],
  lifecycleStatus: 'open' as const,
  workStatus: 'ready' as const,
  ownerId: 'local-legal-user',
  collaboratorIds: [],
  requesterIds: [],
  entityIds: [],
  legalRisk: 'medium' as const,
  businessImpact: 'general' as const,
  priority: 'medium' as const,
  prioritySource: 'system' as const,
  targetDeadlineAt: null,
  nextAction: null,
  confidentiality: 'internal' as const,
  summary: null,
  objective: null,
  currentStage: null,
  openedAt: '2026-08-10T10:00:00Z',
  resolvedAt: null,
  closedAt: null,
  reopenedAt: null,
  version: 1,
} satisfies LegalMatter;

describe('Message detail Matter continuity', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows deterministic Matter recommendations and preselects the strongest one', async () => {
    vi.spyOn(legalApi, 'getMessage').mockResolvedValue({
      id: messageId,
      messageId: 'om_reply',
      tenantKey: 'tenant',
      chatId: 'chat-1',
      threadId: 'thread-1',
      parentMessageId: 'om_outbound',
      rootMessageId: 'om_root',
      senderId: 'ou_business',
      senderType: 'user',
      messageType: 'text',
      plainText: '这是刚才合同的补充材料',
      sentAt: '2026-08-11T10:00:00Z',
      editedAt: null,
      recalledAt: null,
      status: 'candidate_created',
      unsupportedReason: null,
      analysisAttempts: 1,
      failureCode: null,
      failureMessage: null,
      agentRunId: runId,
      agentStatus: 'completed',
      candidateId,
      candidateStatus: 'pending_confirmation',
      confidence: 0.92,
      suggestedCategory: 'contract',
      suggestedDeadline: null,
      structuredContent: {},
      rawPayload: {},
      contextMessages: [],
      versions: [],
      attachments: [],
      candidateRevisions: [],
    } satisfies FeishuMessageDetail);
    vi.spyOn(legalApi, 'getMessageAnalysis').mockResolvedValue({
      message: {
        id: messageId,
        messageId: 'om_reply',
        senderId: 'ou_business',
        messageType: 'text',
        content: {},
        createTime: '2026-08-11T10:00:00Z',
      },
      messageStatus: 'candidate_created',
      contextSnapshot: null,
      agentRun: run,
      analysisResult,
      candidateId,
      failureCode: null,
      failureMessage: null,
      canRetry: true,
    } satisfies MessageAnalysis);
    vi.spyOn(legalApi, 'getCandidate').mockResolvedValue({
      id: candidateId,
      contextSnapshotId: snapshotId,
      status: 'pending_confirmation',
      legalRelevance: 'relevant',
      messageRole: 'existing_matter_update',
      recommendedAction: 'link_existing',
      confidence: 0.92,
      titleProposal: '补充合同材料',
      categoryProposals: [],
      deadlineProposals: [],
      relatedMatterProposals: [{
        matterId,
        matterNumber: matter.matterNumber,
        title: matter.title,
        confidence: 1,
        signals: ['reply_to_communication'],
        evidenceRefs: ['communication:cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'message:om_outbound'],
      }],
      evidenceRefs: ['om_reply'],
      agentRunId: runId,
      feishuMessageId: messageId,
      requiresManualReview: true,
      analysisPayload: analysisResult,
      confirmedBy: null,
      confirmedAt: null,
      version: 1,
    } satisfies MessageCandidate);
    vi.spyOn(legalApi, 'listMatters').mockResolvedValue([matter]);

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={[`/inbox/${messageId}`]}>
        <QueryClientProvider client={client}>
          <Routes><Route path="/inbox/:messageId" element={<MessageDetailPage />} /></Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('可能关联事项')).toBeInTheDocument();
    expect(screen.getByText(/LW-20260811-AABBCCDD · 历史合同审核/)).toBeInTheDocument();
    expect(screen.getByText(/回复自已发送沟通/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /关联已有 Matter/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('LW-20260811-AABBCCDD · 历史合同审核')).toBeInTheDocument();
  });
});
