import type {
  Communication,
  Deadline,
  LegalMatter,
  MessageCandidate,
  Priority,
  PriorityConfirmation,
  ReviewDecision,
  ReviewPackage,
  ReviewRecord,
  WorkItem,
  WorkItemDependency,
} from '../types/api';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api/v1';
const DEFAULT_ACTOR_ID = 'local-legal-user';

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

function createIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `request-${Date.now()}-${Math.random()}`;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  options: { write?: boolean; actorId?: string } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body) headers.set('Content-Type', 'application/json');
  if (options.write) {
    headers.set('X-Actor-ID', options.actorId ?? DEFAULT_ACTOR_ID);
    headers.set('Idempotency-Key', createIdempotencyKey());
    headers.set('X-Correlation-ID', createIdempotencyKey());
  }
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
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
    plannedCompleteAt?: string;
  }>;
}

export const legalApi = {
  listCandidates(status = 'pending_confirmation'): Promise<MessageCandidate[]> {
    return request(`/inbox/candidates?status=${encodeURIComponent(status)}&limit=100`);
  },

  confirmCandidate(candidateId: string, input: ConfirmCandidateInput): Promise<{
    matterId: string;
    matterNumber: string;
    workItemIds: string[];
    idempotentReplay: boolean;
  }> {
    return request(`/inbox/candidates/${candidateId}/confirm-create`, {
      method: 'POST',
      body: JSON.stringify(input),
    }, { write: true });
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
