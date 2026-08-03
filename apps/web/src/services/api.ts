import type {
  Communication,
  AgentRunRecord,
  CandidateStatus,
  CandidateRevision,
  DashboardToday,
  Deadline,
  LegalMatter,
  MatterUpdateProposal,
  MatterUpdateProposalField,
  MessageCandidate,
  MessageAnalysis,
  FeishuConnection,
  FeishuMessageDetail,
  FeishuMessageStatus,
  FeishuMessageSummary,
  Priority,
  PriorityConfirmation,
  ReviewDecision,
  ReviewPackage,
  ReviewRecord,
  WorkItem,
  WorkItemDependency,
  WorkItemStatus,
  SystemHealth,
} from '../types/api';

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api/v1';
export const apiEventStreamUrl = `${API_BASE_URL}/events/stream`;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
    public readonly correlationId?: string,
  ) {
    super(message);
  }
}

interface ApiErrorDetails {
  message: string;
  code?: string;
  correlationId?: string;
}

export function formatApiErrorPayload(payload: unknown, status: number): ApiErrorDetails {
  if (!payload || typeof payload !== 'object') return { message: `请求失败（${status}）` };
  const value = payload as Record<string, unknown>;
  const error = value.error && typeof value.error === 'object'
    ? value.error as Record<string, unknown>
    : undefined;
  if (error) {
    return {
      message: typeof error.message === 'string' ? error.message : `请求失败（${status}）`,
      code: typeof error.code === 'string' ? error.code : undefined,
      correlationId: typeof error.correlationId === 'string' ? error.correlationId : undefined,
    };
  }
  if (typeof value.detail === 'string') return { message: value.detail };
  if (Array.isArray(value.detail)) {
    const messages = value.detail.map((item) => {
      if (!item || typeof item !== 'object') return String(item);
      const detail = item as Record<string, unknown>;
      const location = Array.isArray(detail.loc) ? detail.loc.join('.') : 'request';
      const message = typeof detail.msg === 'string' ? detail.msg : 'Invalid value';
      return `${location}：${message}`;
    });
    return { message: messages.join('；') };
  }
  if (value.detail && typeof value.detail === 'object') {
    return { message: JSON.stringify(value.detail) };
  }
  return { message: `请求失败（${status}）` };
}

export function isDefinitiveMutationFailure(error: unknown): boolean {
  return error instanceof ApiError
    && error.status >= 400
    && error.status < 500
    && error.status !== 408
    && error.status !== 429;
}

function createRequestKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `request-${Date.now()}-${Math.random()}`;
}

export interface MutationContext {
  idempotencyKey: string;
  correlationId: string;
}

export function createMutationContext(): MutationContext {
  return { idempotencyKey: createRequestKey(), correlationId: createRequestKey() };
}

const mutationStoragePrefix = 'legal-workbench:mutation:';
const memoryMutationContexts = new Map<string, string>();

function readMutationValue(key: string): string | null {
  try {
    return globalThis.sessionStorage?.getItem(key) ?? memoryMutationContexts.get(key) ?? null;
  } catch {
    return memoryMutationContexts.get(key) ?? null;
  }
}

function writeMutationValue(key: string, value: string): void {
  memoryMutationContexts.set(key, value);
  try {
    globalThis.sessionStorage?.setItem(key, value);
  } catch {
    // In-memory continuity still covers this tab when storage is unavailable.
  }
}

export function getOrCreateMutationContext(
  actionKey: string,
  requestPayload: unknown,
): MutationContext {
  const storageKey = `${mutationStoragePrefix}${actionKey}`;
  const fingerprint = JSON.stringify(requestPayload);
  const raw = readMutationValue(storageKey);
  if (raw) {
    try {
      const stored = JSON.parse(raw) as { fingerprint: string; context: MutationContext };
      if (stored.fingerprint === fingerprint) return stored.context;
    } catch {
      // Replace malformed local state with a fresh bounded context.
    }
  }
  const context = createMutationContext();
  writeMutationValue(storageKey, JSON.stringify({ fingerprint, context }));
  return context;
}

export function clearMutationContext(actionKey: string): void {
  const storageKey = `${mutationStoragePrefix}${actionKey}`;
  memoryMutationContexts.delete(storageKey);
  try {
    globalThis.sessionStorage?.removeItem(storageKey);
  } catch {
    // The in-memory copy is already cleared.
  }
}

let localSessionPromise: Promise<void> | undefined;

async function ensureLocalSession(): Promise<void> {
  if (!localSessionPromise) {
    localSessionPromise = fetch(`${API_BASE_URL}/auth/session`, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
      .then(async (response) => {
        if (response.ok) return;
        if (response.status !== 401) throw new ApiError('无法验证认证会话', response.status);
        const created = await fetch(`${API_BASE_URL}/auth/local-session`, {
          method: 'POST',
          credentials: 'include',
          headers: { Accept: 'application/json' },
        });
        if (!created.ok) throw new ApiError('无法初始化本地认证会话', created.status);
      })
      .catch((error: unknown) => {
        localSessionPromise = undefined;
        throw error;
      });
  }
  return localSessionPromise;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  options: { write?: boolean; authenticated?: boolean; mutation?: MutationContext } = {},
): Promise<T> {
  await ensureLocalSession();
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body) headers.set('Content-Type', 'application/json');
  if (options.write) {
    const mutation = options.mutation ?? createMutationContext();
    headers.set('Idempotency-Key', mutation.idempotencyKey);
    headers.set('X-Correlation-ID', mutation.correlationId);
  }
  const requestInit = { ...init, credentials: 'include' as const, headers };
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, requestInit);
  } catch (error) {
    if (!(error instanceof TypeError) || !options.write) throw error;
    response = await fetch(`${API_BASE_URL}${path}`, requestInit);
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => ({}));
    const formatted = formatApiErrorPayload(payload, response.status);
    throw new ApiError(
      formatted.message,
      response.status,
      formatted.code,
      formatted.correlationId,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export interface ConfirmCandidateInput {
  candidateVersion: number;
  title: string;
  primaryCategory: string;
  secondaryCategories: string[];
  ownerId: string;
  requesterIds: string[];
  legalRisk: string;
  businessImpact: string;
  confidentiality: string;
  summary?: string;
  objective?: string;
  initialWorkItems: Array<{
    title: string;
    ownerId: string;
    priority: Priority;
    prioritySource: 'legal_confirmed';
    nextAction: string;
    priorityReasons: string[];
    estimatedMinutes?: number;
    plannedCompleteAt?: string;
  }>;
}

export const legalApi = {
  getDashboardToday(): Promise<DashboardToday> {
    return request('/dashboard/today');
  },

  listMessages(filters: {
    statuses?: FeishuMessageStatus[];
    search?: string;
    category?: string;
    chatId?: string;
    from?: string;
    to?: string;
    limit?: number;
  } = {}): Promise<FeishuMessageSummary[]> {
    const query = new URLSearchParams();
    filters.statuses?.forEach((value) => query.append('status', value));
    if (filters.search) query.set('search', filters.search);
    if (filters.category) query.set('category', filters.category);
    if (filters.chatId) query.set('chatId', filters.chatId);
    if (filters.from) query.set('from', filters.from);
    if (filters.to) query.set('to', filters.to);
    query.set('limit', String(filters.limit ?? 200));
    return request(`/feishu/messages?${query.toString()}`);
  },

  getMessage(messageId: string): Promise<FeishuMessageDetail> {
    return request(`/feishu/messages/${messageId}`);
  },

  setAttachmentAnalysisAuthorization(
    messageId: string,
    attachmentId: string,
    authorized: boolean,
    mutation?: MutationContext,
  ): Promise<FeishuMessageDetail['attachments'][number] & { idempotentReplay: boolean }> {
    return request(
      `/feishu/messages/${messageId}/attachments/${attachmentId}/analysis-authorization`,
      { method: 'POST', body: JSON.stringify({ authorized }) },
      { write: true, mutation },
    );
  },

  listCandidates(status = 'pending_confirmation'): Promise<MessageCandidate[]> {
    return request(`/inbox/candidates?status=${encodeURIComponent(status)}&limit=100`);
  },

  getCandidate(candidateId: string): Promise<MessageCandidate> {
    return request(`/inbox/candidates/${candidateId}`);
  },

  listCandidateRevisions(candidateId: string): Promise<CandidateRevision[]> {
    return request(`/inbox/candidates/${candidateId}/revisions`);
  },

  resolveCandidate(candidateId: string, input: {
    candidateVersion: number;
    action: 'link_existing' | 'update_existing' | 'information_only' | 'ignore';
    matterId?: string;
  }, mutation?: MutationContext): Promise<{
    candidateId: string;
    status: CandidateStatus;
    matterId: string | null;
    version: number;
    idempotentReplay: boolean;
  }> {
    return request(`/inbox/candidates/${candidateId}/resolve`, {
      method: 'POST', body: JSON.stringify(input),
    }, { write: true, mutation });
  },

  createMatterUpdateProposal(candidateId: string, input: {
    candidateVersion: number;
    matterId: string;
    proposedChanges: Record<string, {
      currentValue: unknown;
      messageExtractedValue: unknown;
      aiSuggestedValue: unknown;
    }>;
    reason: string;
  }, mutation?: MutationContext): Promise<{
    proposalId: string;
    candidateId: string;
    matterId: string;
    status: 'pending';
    version: number;
    idempotentReplay: boolean;
  }> {
    return request(`/inbox/candidates/${candidateId}/matter-update-proposals`, {
      method: 'POST', body: JSON.stringify(input),
    }, { write: true, mutation });
  },

  getMatterUpdateProposal(proposalId: string): Promise<MatterUpdateProposal> {
    return request(`/matter-update-proposals/${proposalId}`);
  },

  reviewMatterUpdateProposal(proposalId: string, input: {
    proposalVersion: number;
    matterVersion: number;
    decisions: Array<{
      fieldName: MatterUpdateProposalField;
      decision: 'approve' | 'reject';
      finalValue: unknown;
    }>;
    rejectionReason?: string;
  }, mutation?: MutationContext): Promise<{
    proposalId: string;
    matterId: string;
    status: 'approved' | 'partially_approved' | 'rejected';
    proposalVersion: number;
    matterVersion: number;
    workItemIds: string[];
    deadlineId: string | null;
    idempotentReplay: boolean;
  }> {
    return request(`/matter-update-proposals/${proposalId}/review`, {
      method: 'POST', body: JSON.stringify(input),
    }, { write: true, mutation });
  },

  confirmCandidate(candidateId: string, input: ConfirmCandidateInput, mutation?: MutationContext): Promise<{
    matterId: string;
    matterNumber: string;
    workItemIds: string[];
    idempotentReplay: boolean;
  }> {
    return request(`/inbox/candidates/${candidateId}/confirm-create`, {
      method: 'POST',
      body: JSON.stringify(input),
    }, { write: true, mutation });
  },

  getMessageAnalysis(messageId: string): Promise<MessageAnalysis> {
    return request(`/feishu/messages/${messageId}/analysis`, {}, { authenticated: true });
  },

  retryMessageAnalysis(messageId: string, mutation?: MutationContext): Promise<{
    messageId: string;
    messageStatus: string;
    idempotentReplay: boolean;
  }> {
    return request(`/feishu/messages/${messageId}/retry-analysis`, {
      method: 'POST',
    }, { write: true, mutation });
  },

  analyseMessage(messageId: string, mutation?: MutationContext): Promise<{
    messageId: string;
    messageStatus: string;
    idempotentReplay: boolean;
  }> {
    return request(`/feishu/messages/${messageId}/analyse`, {
      method: 'POST',
    }, { write: true, mutation });
  },

  listAgentRuns(status?: AgentRunRecord['status']): Promise<AgentRunRecord[]> {
    const query = new URLSearchParams({ limit: '100' });
    if (status) query.set('status', status);
    return request(`/agent-runs?${query.toString()}`, {}, { authenticated: true });
  },

  getAgentRun(runId: string): Promise<AgentRunRecord> {
    return request(`/agent-runs/${runId}`, {}, { authenticated: true });
  },

  retryAgentRun(runId: string, mutation?: MutationContext): Promise<{
    messageId: string; messageStatus: string; idempotentReplay: boolean;
  }> {
    return request(`/agent-runs/${runId}/retry`, { method: 'POST' }, { write: true, mutation });
  },

  cancelAgentRun(runId: string, mutation?: MutationContext): Promise<{
    runId: string; status: string; idempotentReplay: boolean;
  }> {
    return request(`/agent-runs/${runId}/cancel`, { method: 'POST' }, { write: true, mutation });
  },

  getSystemHealth(): Promise<SystemHealth> {
    return request('/system/health');
  },

  getFeishuStatus(): Promise<FeishuConnection> {
    return request('/integrations/feishu/status');
  },

  reconnectFeishu(mutation?: MutationContext): Promise<{ accepted: boolean }> {
    return request('/integrations/feishu/reconnect', { method: 'POST' }, { write: true, mutation });
  },

  reconcileFeishu(windowMinutes: number, mutation?: MutationContext): Promise<{
    status: string; windowMinutes: number; ingested: number; duplicates: number; message: string;
  }> {
    return request('/integrations/feishu/reconcile', {
      method: 'POST', body: JSON.stringify({ windowMinutes }),
    }, { write: true, mutation });
  },

  recoverPendingJobs(mutation?: MutationContext): Promise<{
    missingRunsRequeued: number; staleRunsRequeued: number; deadLettered: number; idempotentReplay: boolean;
  }> {
    return request('/system/recover-pending-jobs', { method: 'POST' }, { write: true, mutation });
  },

  listOutboxDeadLetters(): Promise<Array<{
    id: string;
    originalEventId: string;
    eventType: string;
    aggregateType: string;
    aggregateId: string;
    correlationId: string;
    attempts: number;
    lastError: string;
    failedAt: string;
    requeuedAt: string | null;
    requeuedEventId: string | null;
  }>> {
    return request('/system/outbox/dead-letters?limit=100');
  },

  requeueOutboxDeadLetter(deadLetterId: string, mutation?: MutationContext): Promise<{
    deadLetterId: string;
    outboxEventId: string;
    idempotentReplay: boolean;
  }> {
    return request(`/system/outbox/dead-letters/${deadLetterId}/requeue`, {
      method: 'POST',
    }, { write: true, mutation });
  },

  listMatters(): Promise<LegalMatter[]> {
    return request('/matters?limit=100');
  },

  getMatter(matterId: string): Promise<LegalMatter> {
    return request(`/matters/${matterId}`);
  },

  listWorkItems(matterId: string): Promise<WorkItem[]> {
    return request(`/matters/${matterId}/work-items`);
  },

  getWorkItem(workItemId: string): Promise<WorkItem> {
    return request(`/work-items/${workItemId}`);
  },

  applyWorkItemAction(workItemId: string, action: 'start' | 'pause' | 'wait' | 'block' | 'resume' | 'complete' | 'cancel' | 'reopen', version: number, input: {
    reason?: string;
    waitingPartyId?: string;
    blockerOwnerId?: string;
  }, mutation?: MutationContext): Promise<{ workItemId: string; status: WorkItemStatus; version: number; idempotentReplay: boolean }> {
    return request(`/work-items/${workItemId}/${action}`, {
      method: 'POST',
      headers: { 'If-Match': String(version) },
      body: JSON.stringify(input),
    }, { write: true, mutation });
  },

  changeWorkItemOwner(workItemId: string, version: number, input: { ownerId: string; reason?: string }, mutation?: MutationContext): Promise<{ workItemId: string; status: WorkItemStatus; version: number; idempotentReplay: boolean }> {
    return request(`/work-items/${workItemId}/owner`, {
      method: 'PATCH', headers: { 'If-Match': String(version) }, body: JSON.stringify(input),
    }, { write: true, mutation });
  },

  changeWorkItemDeadline(workItemId: string, version: number, input: { deadline: string; reason?: string }, mutation?: MutationContext): Promise<{ workItemId: string; status: WorkItemStatus; version: number; idempotentReplay: boolean }> {
    return request(`/work-items/${workItemId}/deadline`, {
      method: 'PATCH', headers: { 'If-Match': String(version) }, body: JSON.stringify(input),
    }, { write: true, mutation });
  },

  changeWorkItemNextAction(workItemId: string, version: number, input: { nextAction: string; reason?: string }, mutation?: MutationContext): Promise<{ workItemId: string; status: WorkItemStatus; version: number; idempotentReplay: boolean }> {
    return request(`/work-items/${workItemId}/next-action`, {
      method: 'PATCH', headers: { 'If-Match': String(version) }, body: JSON.stringify(input),
    }, { write: true, mutation });
  },

  confirmPriority(workItemId: string, input: {
    workItemVersion: number;
    confirmedPriority: Priority;
    confirmedCompleteAt?: string;
    reasons: string[];
    overrideReason?: string;
  }): Promise<{ workItemId: string; confirmationId: string; version: number }> {
    return request(`/work-items/${workItemId}/priority-confirmations`, {
      method: 'POST',
      body: JSON.stringify(input),
    }, { write: true });
  },

  listPriorityConfirmations(workItemId: string): Promise<PriorityConfirmation[]> {
    return request(`/work-items/${workItemId}/priority-confirmations`);
  },

  createDeadline(workItemId: string, input: {
    deadlineType: string;
    source: 'legal_confirmed';
    dueAt: string;
    timezone: string;
    isHard: boolean;
    sourceReference?: string;
    reminderPolicy: Record<string, unknown>;
  }): Promise<{ deadlineId: string }> {
    return request(`/work-items/${workItemId}/deadlines`, {
      method: 'POST',
      body: JSON.stringify(input),
    }, { write: true });
  },

  listDeadlines(workItemId: string): Promise<Deadline[]> {
    return request(`/work-items/${workItemId}/deadlines`);
  },

  createDependency(workItemId: string, input: {
    workItemVersion: number;
    dependencyType: string;
    dependsOnWorkItemId?: string;
    externalPartyId?: string;
    description?: string;
  }, mutation?: MutationContext): Promise<{ dependencyId: string; workItemVersion: number }> {
    const { workItemVersion, ...body } = input;
    return request(`/work-items/${workItemId}/dependencies`, {
      method: 'POST',
      headers: { 'If-Match': String(workItemVersion) },
      body: JSON.stringify(body),
    }, { write: true, mutation });
  },

  resolveDependency(workItemId: string, dependencyId: string, workItemVersion: number, dependencyVersion: number, reason?: string, mutation?: MutationContext): Promise<{
    workItemId: string; dependencyId: string; workItemVersion: number; dependencyVersion: number; status: string; idempotentReplay: boolean;
  }> {
    return request(`/work-items/${workItemId}/dependencies/${dependencyId}/resolve`, {
      method: 'POST',
      headers: { 'If-Match': String(workItemVersion) },
      body: JSON.stringify({ dependencyVersion, reason }),
    }, { write: true, mutation });
  },

  listDependencies(workItemId: string): Promise<WorkItemDependency[]> {
    return request(`/work-items/${workItemId}/dependencies`);
  },

  createReviewPackage(input: {
    matterId: string;
    workItemId?: string;
    packageType: string;
    title: string;
    background: string;
    confirmedFacts: Array<Record<string, unknown>>;
    unconfirmedFacts: Array<Record<string, unknown>>;
    reasoning: string;
    risks: Array<Record<string, unknown>>;
    alternatives: Array<Record<string, unknown>>;
    citations: Array<Record<string, unknown>>;
    proposedContent: string;
    target: Record<string, unknown>;
    submitForReview: boolean;
  }): Promise<{ reviewPackageId: string; version: number }> {
    return request('/reviews/packages', {
      method: 'POST',
      body: JSON.stringify(input),
    }, { write: true });
  },

  listReviewPackages(status?: string): Promise<ReviewPackage[]> {
    const query = status ? `?status=${encodeURIComponent(status)}&limit=100` : '?limit=100';
    return request(`/reviews/packages${query}`);
  },

  getReviewPackage(packageId: string): Promise<ReviewPackage> {
    return request(`/reviews/packages/${packageId}`);
  },

  reviewPackage(packageId: string, input: {
    packageVersion: number;
    decision: ReviewDecision;
    comments?: string;
    finalContent?: string;
    reusableAsExample: boolean;
  }): Promise<{ reviewPackageId: string; reviewRecordId: string; status: string }> {
    return request(`/reviews/packages/${packageId}/records`, {
      method: 'POST',
      body: JSON.stringify({ ...input, changeSummary: [] }),
    }, { write: true });
  },

  listReviewRecords(packageId: string): Promise<ReviewRecord[]> {
    return request(`/reviews/packages/${packageId}/records`);
  },

  queueCommunication(packageId: string): Promise<{ communicationId: string; status: string }> {
    return request(`/reviews/packages/${packageId}/communications`, {
      method: 'POST',
    }, { write: true });
  },

  listCommunications(): Promise<Communication[]> {
    return request('/reviews/communications?limit=100');
  },
};
