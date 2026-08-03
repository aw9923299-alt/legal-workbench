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
  | 'paused'
  | 'waiting'
  | 'blocked'
  | 'pending_review'
  | 'done'
  | 'cancelled';

export type DashboardGroup =
  | 'today_must_handle'
  | 'overdue'
  | 'pending_candidates'
  | 'analysis_failed'
  | 'waiting_others'
  | 'upcoming_deadlines'
  | 'pending_outbound_review'
  | 'system_abnormal';

export interface DashboardItem {
  id: string;
  group: DashboardGroup;
  objectType: string;
  title: string;
  description: string;
  href: string;
  status: string;
  createdAt: string;
  dueAt: string | null;
  isHardDeadline: boolean;
  isOverdue: boolean;
  legalRisk: LegalRisk;
  confirmedPriority: Priority | null;
  aiSuggestedPriority: Priority | null;
  waitingSince: string | null;
  waitingSeconds: number;
  rankingReasons: string[];
}

export interface DashboardToday {
  generatedAt: string;
  todayMustHandle: DashboardItem[];
  overdue: DashboardItem[];
  pendingCandidates: DashboardItem[];
  analysisFailed: DashboardItem[];
  waitingOthers: DashboardItem[];
  upcomingDeadlines: DashboardItem[];
  pendingOutboundReview: DashboardItem[];
  systemAbnormal: DashboardItem[];
}

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
  feishuMessageId: string | null;
  requiresManualReview: boolean;
  analysisPayload: MessageJudgementResult | Record<string, never>;
  confirmedBy: string | null;
  confirmedAt: string | null;
  version: number;
}

export interface CategoryCandidate {
  category: 'contract' | 'copy_review' | 'employment' | 'dispute' | 'intellectual_property' | 'general';
  confidence: number;
  reason: string;
}

export interface DeadlineCandidate {
  rawText: string;
  resolvedAt: string | null;
  deadlineType: 'legal' | 'platform' | 'contractual' | 'business' | 'internal' | 'unknown';
  confidence: number;
}

export interface MessageJudgementResult {
  legalRelevance: 'relevant' | 'possibly_relevant' | 'irrelevant';
  messageRole: 'new_request' | 'existing_matter_update' | 'supplemental_material' | 'deadline_change' | 'decision_record' | 'completion_update' | 'information_only';
  actionability: 'create_candidate' | 'link_candidate' | 'update_only' | 'ignore';
  suggestedTitle: string;
  categoryCandidates: CategoryCandidate[];
  deadlineCandidates: DeadlineCandidate[];
  confirmedFacts: Array<{
    statement: string;
    sourceMessageId: string | null;
    attachmentCitation?: {
      attachmentId: string;
      fileName: string;
      pageNumber: number | null;
      paragraphNumber: number;
      contentHash: string;
    } | null;
  }>;
  inferredFacts: Array<{ statement: string; basis: string; confidence: number }>;
  missingInformation: string[];
  reasons: string[];
  confidence: number;
}

export type AgentRunStatus = 'queued' | 'preparing' | 'running' | 'validating' | 'completed' | 'needs_more_information' | 'failed' | 'timed_out' | 'cancelled' | 'dead_letter';

export type FeishuMessageStatus = 'received' | 'queued_for_analysis' | 'context_prepared' | 'agent_queued' | 'analysing' | 'candidate_created' | 'ignored' | 'analysis_failed' | 'dead_letter';

export interface AgentRunSource {
  sourceType: string;
  sourceId: string;
  sourceVersion: string | null;
  sourceHash: string;
  displayName: string;
  citationMetadata: Record<string, unknown>;
}

export interface AgentRunRecord {
  id: string;
  agentKey: string;
  agentVersion: string;
  feishuMessageId: string | null;
  contextSnapshotId: string;
  status: AgentRunStatus;
  objective: string;
  inputPayload: Record<string, unknown>;
  outputPayload: MessageJudgementResult | null;
  rawStdout: string | null;
  rawStderr: string | null;
  promptSnapshot: string;
  workingDirectory: string;
  startedAt: string | null;
  heartbeatAt: string | null;
  finishedAt: string | null;
  timeoutAt: string | null;
  attemptNumber: number;
  maxAttempts: number;
  failureCode: string | null;
  failureMessage: string | null;
  runtimeVersion: string | null;
  agentDefinitionVersion: string;
  promptVersion: string;
  validationErrors: string[];
  repairAttempted: boolean;
  tokenUsage: Record<string, number> | null;
  workerId: string | null;
  leaseExpiresAt: string | null;
  correlationId: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  version: number;
  sources: AgentRunSource[];
  statusEvents: Array<{
    id: string;
    fromStatus: AgentRunStatus | null;
    toStatus: AgentRunStatus;
    changedAt: string;
    correlationId: string;
    attemptNumber: number;
    failureCode: string | null;
    failureMessage: string | null;
  }>;
  candidateId: string | null;
}

export interface FeishuMessageSummary {
  id: string;
  messageId: string;
  tenantKey: string | null;
  chatId: string | null;
  threadId: string | null;
  parentMessageId: string | null;
  rootMessageId: string | null;
  senderId: string | null;
  senderType: string | null;
  messageType: string;
  plainText: string | null;
  sentAt: string | null;
  editedAt: string | null;
  recalledAt: string | null;
  status: FeishuMessageStatus;
  unsupportedReason: string | null;
  analysisAttempts: number;
  failureCode: string | null;
  failureMessage: string | null;
  agentRunId: string | null;
  agentStatus: AgentRunStatus | null;
  candidateId: string | null;
  candidateStatus: CandidateStatus | null;
  confidence: number | null;
  suggestedCategory: string | null;
  suggestedDeadline: string | null;
}

export interface CandidateRevision {
  id: string;
  candidateId: string;
  revision: number;
  agentRunId: string;
  analysisPayload: MessageJudgementResult;
  createdAt: string;
  supersededAt: string | null;
  supersededBy: string | null;
}

export interface FeishuMessageDetail extends FeishuMessageSummary {
  structuredContent: Record<string, unknown>;
  rawPayload: Record<string, unknown>;
  contextMessages: FeishuMessageSummary[];
  versions: Array<{
    id: string;
    revision: number;
    eventId: string;
    plainText: string;
    structuredContent: Record<string, unknown>;
    attachments: Array<Record<string, unknown>>;
    contentHash: string;
    editedAt: string | null;
    recalledAt: string | null;
    isRecalled: boolean;
    createdAt: string;
  }>;
  attachments: Array<{
    id: string;
    fileKey: string;
    fileName: string;
    mimeType: string | null;
    size: number | null;
    sha256: string | null;
    downloadStatus: string;
    downloadError: string | null;
    authorizedForAnalysis: boolean;
    extractionStatus: 'not_requested' | 'pending' | 'extracting' | 'succeeded' | 'body_unavailable' | 'failed';
    extractorVersion: string | null;
    pageCount: number | null;
    characterCount: number | null;
    extractionErrorCode: string | null;
  }>;
  candidateRevisions: CandidateRevision[];
}

export interface MessageAnalysis {
  message: {
    id: string;
    messageId: string;
    senderId: string | null;
    messageType: string;
    content: Record<string, unknown>;
    createTime: string | null;
  };
  messageStatus: string;
  contextSnapshot: {
    id: string;
    snapshotVersion: number;
    messageIds: string[];
    attachmentIds: string[];
    includedSegments: Array<Record<string, unknown>>;
    excludedSegments: Array<Record<string, unknown>>;
    participantIds: string[];
    contentHash: string;
    truncated: boolean;
    truncationReason: string | null;
    originalSize: number;
    includedSize: number;
    builderVersion: string;
    selectionPolicyVersion: string;
    createdAt: string;
  } | null;
  agentRun: AgentRunRecord | null;
  analysisResult: MessageJudgementResult | null;
  candidateId: string | null;
  failureCode: string | null;
  failureMessage: string | null;
  canRetry: boolean;
}

export interface ComponentHealth {
  status: 'normal' | 'degraded' | 'unavailable' | 'not_configured' | string;
  detail: string;
  updatedAt: string;
}

export interface SystemHealth {
  generatedAt: string;
  components: Record<string, ComponentHealth>;
  metrics: {
    outboxPending: number;
    agentQueued: number;
    failedRuns: number;
    agentDeadLetters: number;
    outboxDeadLetters: number;
    lastMessageAt: string | null;
    lastCompletedRunAt: string | null;
    lastReconcileAt: string | null;
    lastCandidateAt: string | null;
    lastAgentRunUpdateAt: string | null;
    lastOutboxFailureAt: string | null;
  } | null;
  codex: {
    enabled: boolean;
    status: string;
    executable: string | null;
    detectedVersion: string | null;
    expectedVersion: string | null;
    authentication: string;
    runtimeDirectoryWritable: boolean;
    detail: string;
  };
}

export interface FeishuConnection {
  integrationType: string;
  connectionMode: string;
  status: string;
  lastConnectedAt: string | null;
  lastDisconnectedAt: string | null;
  lastEventAt: string | null;
  lastErrorCode: string | null;
  lastErrorMessage: string | null;
  reconnectCount: number;
  lastReconcileAt: string | null;
  lastReconcileStatus: string | null;
  lastReconcileMessage: string | null;
  updatedAt: string;
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
  priority: Priority;
  prioritySource: PrioritySource;
  targetDeadlineAt: string | null;
  nextAction: string | null;
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

export type MatterUpdateProposalStatus =
  | 'pending'
  | 'approved'
  | 'partially_approved'
  | 'rejected'
  | 'superseded';

export type MatterUpdateProposalField =
  | 'title'
  | 'category'
  | 'priority'
  | 'deadline'
  | 'owner'
  | 'currentStatus'
  | 'nextAction'
  | 'newWorkItems';

export interface ProposedFieldValues {
  currentValue: unknown;
  messageExtractedValue: unknown;
  aiSuggestedValue: unknown;
}

export interface MatterUpdateProposal {
  id: string;
  candidateId: string;
  matterId: string;
  baseMatterVersion: number;
  proposedChanges: Partial<Record<MatterUpdateProposalField, ProposedFieldValues>>;
  finalChanges: Partial<Record<MatterUpdateProposalField, unknown>>;
  fieldDecisions: Array<{
    fieldName: MatterUpdateProposalField;
    decision: 'approve' | 'reject';
    finalValue: unknown;
  }>;
  reason: string;
  status: MatterUpdateProposalStatus;
  createdBy: string;
  reviewedBy: string | null;
  reviewedAt: string | null;
  rejectionReason: string | null;
  createdAt: string;
  version: number;
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
  pausedReason: string | null;
  isBlocked: boolean;
  blockerReason: string | null;
  blockerOwnerId: string | null;
  plannedStartAt: string | null;
  plannedCompleteAt: string | null;
  completedAt: string | null;
  cancelledAt: string | null;
  cancelReason: string | null;
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
  satisfiedBy: string | null;
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
