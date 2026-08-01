import type {
  Communication,
  AgentRunRecord,
  Deadline,
  LegalMatter,
  MessageCandidate,
  MessageAnalysis,
  Priority,
  PriorityConfirmation,
  ReviewDecision,
  ReviewPackage,
  ReviewRecord,
  WorkItem,
  WorkItemDependency,
} from '../types/api';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api/v1';

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
    const payload = (await response.json().catch(() => ({}))) as {
      error?: { message?: string; code?: string; correlationId?: string };
      detail?: string;
    };
    throw new ApiError(
      payload.error?.message ?? payload.detail ?? `请求失败（${response.status}）`,
      response.status,
      payload.error?.code,
      payload.error?.correlationId,
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
  listCandidates(status = 'pending_confirmation'): Promise<MessageCandidate[]> {
    return request(`/inbox/candidates?status=${encodeURIComponent(status)}&limit=100`);
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

  listAgentRuns(): Promise<AgentRunRecord[]> {
    return request('/agent-runs?limit=100', {}, { authenticated: true });
  },

  getAgentRun(runId: string): Promise<AgentRunRecord> {
    return request(`/agent-runs/${runId}`, {}, { authenticated: true });
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
    dependencyType: string;
    dependsOnWorkItemId?: string;
    externalPartyId?: string;
    description?: string;
  }): Promise<{ dependencyId: string }> {
    return request(`/work-items/${workItemId}/dependencies`, {
      method: 'POST',
      body: JSON.stringify(input),
    }, { write: true });
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
