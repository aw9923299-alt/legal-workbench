export type CandidateStatus =
  | 'pending_analysis'
  | 'pending_confirmation'
  | 'confirmed'
  | 'linked'
  | 'information_only'
  | 'ignored'
  | 'rejected';

export type MatterCategory =
  | 'contract'
  | 'copy_review'
  | 'employment'
  | 'dispute'
  | 'intellectual_property'
  | 'platform_rules'
  | 'general_consultation';

export type LegalRisk = 'critical' | 'high' | 'medium' | 'low' | 'pending';
export type BusinessImpact = 'company' | 'department' | 'project' | 'general';
export type Priority = 'urgent' | 'high' | 'medium' | 'low';
export type PrioritySource = 'system' | 'agent_suggested' | 'legal_confirmed';
export type WorkItemStatus =
  | 'todo'
  | 'in_progress'
  | 'waiting'
  | 'blocked'
  | 'pending_review'
  | 'done'
  | 'cancelled';

export interface MessageCandidate {
  id: string;
  contextSnapshotId: string;
  status: CandidateStatus;
  legalRelevance: 'relevant' | 'possibly_relevant' | 'not_relevant' | 'unknown';
  messageRole: string;
  recommendedAction: string;
  confidence: number;
  titleProposal: string | null;
  categoryProposals: Array<Record<string, unknown>>;
  deadlineProposals: Array<Record<string, unknown>>;
  relatedMatterProposals: Array<Record<string, unknown>>;
  evidenceRefs: string[];
  agentRunId: string | null;
  confirmedBy: string | null;
  confirmedAt: string | null;
  version: number;
}

export interface LegalMatter {
  id: string;
  matterNumber: string;
  title: string;
  primaryCategory: MatterCategory;
  secondaryCategories: MatterCategory[];
  lifecycleStatus: 'open' | 'resolved' | 'closed' | 'reopened' | 'cancelled';
  workStatus: 'ready' | 'in_progress' | 'waiting' | 'blocked' | 'done';
  ownerId: string;
  collaboratorIds: string[];
  requesterIds: string[];
  entityIds: string[];
  legalRisk: LegalRisk;
  businessImpact: BusinessImpact;
  confidentiality: 'internal' | 'confidential' | 'restricted';
  summary: string | null;
  objective: string | null;
  currentStage: string | null;
  version: number;
  openedAt: string;
  resolvedAt: string | null;
  closedAt: string | null;
  reopenedAt: string | null;
}

export interface WorkItem {
  id: string;
  matterId: string;
  title: string;
  status: WorkItemStatus;
  ownerId: string;
  collaboratorIds: string[];
  priority: Priority;
  prioritySource: PrioritySource;
  aiSuggestedPriority: Priority | null;
  priorityReasons: string[];
  overrideReason: string | null;
  estimatedMinutes: number | null;
  nextAction: string;
  waitingPartyId: string | null;
  waitingReason: string | null;
  waitingSince: string | null;
  isBlocked: boolean;
  blockerReason: string | null;
  blockerOwnerId: string | null;
  plannedStartAt: string | null;
  plannedCompleteAt: string | null;
  completedAt: string | null;
  priorityConfirmedBy: string | null;
  priorityConfirmedAt: string | null;
  sequenceOrder: number;
  version: number;
}

export interface PriorityConfirmation {
  id: string;
  workItemId: string;
  proposedPriority: Priority;
  confirmedPriority: Priority;
  proposedCompleteAt: string | null;
  confirmedCompleteAt: string | null;
  reasons: string[];
  overrideReason: string | null;
  confirmedBy: string;
  confirmedAt: string;
  status: 'pending' | 'confirmed' | 'superseded';
  version: number;
}

export interface Deadline {
  id: string;
  matterId: string | null;
  workItemId: string | null;
  deadlineType: 'legal' | 'platform' | 'contractual' | 'business' | 'internal' | 'reminder';
  source: string;
  dueAt: string;
  timezone: string;
  isHard: boolean;
  status: 'active' | 'satisfied' | 'missed' | 'cancelled' | 'superseded';
  sourceReference: string | null;
  confidence: number | null;
  reminderPolicy: Record<string, unknown>;
  confirmedBy: string | null;
  confirmedAt: string | null;
  completedAt: string | null;
  version: number;
}

export interface WorkItemDependency {
  id: string;
  workItemId: string;
  dependsOnWorkItemId: string | null;
  dependencyType: 'finish_to_start' | 'start_to_start' | 'external_input' | 'approval' | 'material';
  status: 'active' | 'satisfied' | 'waived' | 'cancelled';
  externalPartyId: string | null;
  description: string | null;
  satisfiedAt: string | null;
  waivedBy: string | null;
  waivedAt: string | null;
  version: number;
}

export type ReviewDecision =
  | 'approved'
  | 'approved_with_edits'
  | 'rejected'
  | 'needs_information';

export interface ReviewPackage {
  id: string;
  matterId: string;
  workItemId: string | null;
  packageType: string;
  status: 'draft' | 'pending_review' | 'approved' | 'rejected' | 'needs_information' | 'superseded';
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
  createdBy: string;
  submittedAt: string | null;
  approvedContentHash: string | null;
  version: number;
}

export interface ReviewRecord {
  id: string;
  reviewPackageId: string;
  reviewerId: string;
  decision: ReviewDecision;
  comments: string | null;
  finalContent: string | null;
  finalContentHash: string | null;
  changeSummary: Array<Record<string, unknown>>;
  reusableAsExample: boolean;
  reviewedAt: string;
}

export interface Communication {
  id: string;
  matterId: string;
  workItemId: string | null;
  reviewPackageId: string;
  reviewRecordId: string;
  channel: 'feishu';
  target: Record<string, unknown>;
  content: string;
  contentHash: string;
  status: 'draft' | 'pending_review' | 'approved' | 'queued' | 'sending' | 'sent' | 'unknown' | 'failed' | 'dead_letter';
  requestedBy: string;
  correlationId: string;
  externalMessageId: string | null;
  attempts: number;
  lastError: string | null;
  queuedAt: string | null;
  sentAt: string | null;
  version: number;
}

export interface ApiErrorPayload {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
    correlationId?: string;
  };
  detail?: string;
}
