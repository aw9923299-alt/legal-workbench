# 核心数据模型与状态机

## 1. 建模原则

1. 原始来源、AI 建议、人工确认和正式对外内容分层存储。
2. 消息与事项是多对多关系；一条消息可拆成多个候选，一个事项可聚合多条消息。
3. 事项、行动任务、Agent 运行、审核和发送分别拥有独立状态机。
4. 人工确认值不能被后续 Agent 静默覆盖。
5. 所有重要值保留来源、证据、版本、操作者和时间。
6. 事实、推断、法律结论、建议和表达草稿不得混存为一个文本字段。

## 2. 核心实体

## 2.1 FeishuMessage

保存原始飞书消息及同步状态。业务字段不可直接覆盖原始载荷。

```ts
interface FeishuMessage {
  id: string;
  tenantId: string;
  eventId: string;
  messageId: string;
  chatId: string;
  chatType: 'bot_dm' | 'group' | 'forwarded_dm';
  threadId?: string;
  parentMessageId?: string;
  senderId: string;
  senderType: 'user' | 'bot' | 'app';
  sentAt: string;
  editedAt?: string;
  recalledAt?: string;
  messageType: string;
  plainText?: string;
  rawPayloadEncrypted: string;
  contentHash: string;
  syncStatus: 'received' | 'processed' | 'ignored' | 'failed';
  createdAt: string;
}
```

唯一约束：

- `(tenant_id, event_id)`；
- `(tenant_id, message_id, content_hash)`。

## 2.2 FileAsset

统一表示飞书附件和本地公司资料。

```ts
interface FileAsset {
  id: string;
  source: 'feishu' | 'local_directory' | 'generated';
  sourceToken?: string;
  sourcePath?: string;
  fileName: string;
  mediaType: string;
  size: number;
  sha256: string;
  versionGroupId?: string;
  versionNumber?: number;
  supersedesFileId?: string;
  parseStatus: 'pending' | 'parsing' | 'ready' | 'failed' | 'unsupported';
  permissionStatus: 'available' | 'revoked' | 'deleted';
  confidentiality: 'internal' | 'confidential' | 'restricted';
  createdAt: string;
}
```

## 2.3 ContextSnapshot

记录一次 Agent 分析的完整输入边界。

```ts
interface ContextSnapshot {
  id: string;
  triggerMessageId: string;
  messageIds: string[];
  fileIds: string[];
  relevantMatterIds: string[];
  participantIds: string[];
  permissionSnapshot: Record<string, unknown>;
  generatedAt: string;
  contentHash: string;
}
```

快照一经创建不可修改。需要补充上下文时创建新版本。

## 2.4 MessageCandidate

表示系统对一条或一组消息的候选处理建议。

```ts
interface MessageCandidate {
  id: string;
  contextSnapshotId: string;
  status:
    | 'pending_analysis'
    | 'pending_confirmation'
    | 'confirmed'
    | 'linked'
    | 'information_only'
    | 'ignored'
    | 'rejected';
  legalRelevance: 'relevant' | 'possibly_relevant' | 'not_relevant' | 'unknown';
  messageRole:
    | 'new_request'
    | 'progress_update'
    | 'material_update'
    | 'decision'
    | 'deadline_change'
    | 'closure_signal'
    | 'information';
  recommendedAction:
    | 'create_matter'
    | 'link_matter'
    | 'update_matter'
    | 'add_material'
    | 'reopen_matter'
    | 'information_only'
    | 'ignore'
    | 'needs_confirmation';
  titleProposal?: ProposedValue<string>;
  categoryProposals: ProposedValue<string>[];
  deadlineProposals: DeadlineProposal[];
  relatedMatterProposals: MatterLinkProposal[];
  evidenceRefs: string[];
  confidence: number;
  agentRunId: string;
  confirmedBy?: string;
  confirmedAt?: string;
}
```

## 2.5 LegalMatter

完整、持续存在的法务事项。

```ts
interface LegalMatter {
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
  legalRisk: 'critical' | 'high' | 'medium' | 'low' | 'pending';
  businessImpact: 'company' | 'department' | 'project' | 'general';
  confidentiality: 'internal' | 'confidential' | 'restricted';
  summary?: string;
  objective?: string;
  currentStage?: string;
  version: number;
  openedAt: string;
  resolvedAt?: string;
  closedAt?: string;
  reopenedAt?: string;
}
```

`workStatus` 是事项整体工作态势，不替代 `WorkItem` 状态。

## 2.6 MatterSourceLink

消息、文件与事项的多对多关系。

```ts
interface MatterSourceLink {
  id: string;
  matterId: string;
  sourceType: 'message' | 'file' | 'notice' | 'manual_note';
  sourceId: string;
  relationType:
    | 'originates'
    | 'updates'
    | 'supports'
    | 'contradicts'
    | 'references'
    | 'supersedes';
  confidence?: number;
  confirmedBy?: string;
  createdAt: string;
}
```

## 2.7 WorkItem

事项下的具体行动。

```ts
interface WorkItem {
  id: string;
  matterId: string;
  title: string;
  status:
    | 'todo'
    | 'in_progress'
    | 'waiting'
    | 'blocked'
    | 'pending_review'
    | 'done'
    | 'cancelled';
  ownerId: string;
  collaboratorIds: string[];
  priority: 'urgent' | 'high' | 'medium' | 'low';
  prioritySource: 'system' | 'agent_suggested' | 'legal_confirmed';
  aiSuggestedPriority?: 'urgent' | 'high' | 'medium' | 'low';
  priorityReasons: string[];
  overrideReason?: string;
  estimatedMinutes?: number;
  nextAction: string;
  waitingPartyId?: string;
  waitingReason?: string;
  waitingSince?: string;
  isBlocked: boolean;
  blockerReason?: string;
  blockerOwnerId?: string;
  plannedStartAt?: string;
  plannedCompleteAt?: string;
  completedAt?: string;
  version: number;
}
```

“等待材料、等待业务、等待外部、待审批”由 `Dependency/Approval` 关系表达，不再作为彼此排斥的唯一状态。

## 2.8 Deadline

一个事项或任务可拥有多个期限。

```ts
interface Deadline {
  id: string;
  matterId: string;
  workItemId?: string;
  type:
    | 'legal'
    | 'court'
    | 'platform'
    | 'contract'
    | 'business_requested'
    | 'internal_sla'
    | 'reminder';
  dueAt: string;
  timezone: string;
  isHardDeadline: boolean;
  sourceRef?: string;
  sourceText?: string;
  confidence?: number;
  status: 'proposed' | 'confirmed' | 'superseded' | 'completed' | 'missed';
  confirmedBy?: string;
}
```

## 2.9 Dependency

```ts
interface Dependency {
  id: string;
  matterId: string;
  workItemId?: string;
  type: 'material' | 'response' | 'decision' | 'approval' | 'external_event';
  waitingForId?: string;
  description: string;
  status: 'open' | 'satisfied' | 'waived' | 'expired';
  expectedAt?: string;
  nextReminderAt?: string;
  escalationRuleId?: string;
}
```

## 2.10 AgentDefinition

详细协议见 `AGENT_PROTOCOL.md`。

```ts
interface AgentDefinition {
  id: string;
  name: string;
  role: 'core' | 'professional' | 'support';
  version: string;
  promptVersion: string;
  inputSchemaVersion: string;
  outputSchemaVersion: string;
  allowedTools: string[];
  allowedKnowledgeScopes: string[];
  timeoutSeconds: number;
  maxRetries: number;
  status: 'draft' | 'trial' | 'active' | 'paused' | 'retired';
  requiresHumanReview: boolean;
}
```

## 2.11 AgentExecutionPlan

```ts
interface AgentExecutionPlan {
  id: string;
  matterId: string;
  workItemId?: string;
  status: 'draft' | 'pending_confirmation' | 'approved' | 'running' | 'paused' | 'completed' | 'failed';
  planVersion: number;
  steps: AgentPlanStep[];
  generatedByRunId: string;
  approvedBy?: string;
}

interface AgentPlanStep {
  id: string;
  agentId: string;
  objective: string;
  dependencyStepIds: string[];
  condition?: string;
  executionMode: 'sequential' | 'parallel';
  expectedArtifactTypes: string[];
}
```

## 2.12 AgentRun

```ts
interface AgentRun {
  id: string;
  planId?: string;
  planStepId?: string;
  matterId: string;
  workItemId?: string;
  agentDefinitionId: string;
  agentVersion: string;
  promptVersion: string;
  contextSnapshotId: string;
  status:
    | 'queued'
    | 'running'
    | 'needs_more_information'
    | 'conflict_detected'
    | 'succeeded'
    | 'failed'
    | 'cancelled'
    | 'dead_letter';
  idempotencyKey: string;
  inputHash: string;
  outputHash?: string;
  retryCount: number;
  startedAt?: string;
  finishedAt?: string;
  failureCode?: string;
  failureMessage?: string;
}
```

## 2.13 DraftArtifact

Agent 只能产出草稿，不直接生成正式外发记录。

```ts
interface DraftArtifact {
  id: string;
  matterId: string;
  workItemId?: string;
  agentRunId: string;
  type:
    | 'analysis'
    | 'contract_review'
    | 'copy_review'
    | 'material_list'
    | 'reply_draft'
    | 'report_draft'
    | 'retrospective_draft';
  version: number;
  status: 'draft' | 'superseded' | 'submitted_for_review' | 'approved' | 'rejected';
  content: Record<string, unknown>;
  citationIds: string[];
  createdAt: string;
}
```

## 2.14 ReviewPackage

```ts
interface ReviewPackage {
  id: string;
  matterId: string;
  workItemId?: string;
  type: 'priority_confirmation' | 'agent_result' | 'external_communication' | 'rule_candidate';
  status: 'draft' | 'pending' | 'approved' | 'rejected' | 'changes_requested' | 'cancelled';
  sourceArtifactIds: string[];
  background: string;
  confirmedFacts: FactRef[];
  unconfirmedFacts: FactRef[];
  conclusions: ConclusionRef[];
  conflicts: ConflictRef[];
  recommendation: string;
  rationale: string[];
  risks: RiskRef[];
  alternatives: Alternative[];
  citations: CitationRef[];
  outboundDraft?: OutboundDraft;
  versionHash: string;
  createdAt: string;
}
```

## 2.15 ReviewRecord

```ts
interface ReviewRecord {
  id: string;
  reviewPackageId: string;
  reviewerId: string;
  decision:
    | 'approved'
    | 'approved_with_edits'
    | 'rejected'
    | 'needs_more_information'
    | 'deferred'
    | 'internal_only';
  approvedVersionHash?: string;
  editedContent?: Record<string, unknown>;
  reasonCodes: ReviewReasonCode[];
  comment?: string;
  isExceptionalCase: boolean;
  allowAsLearningExample: boolean;
  allowRuleCandidate: boolean;
  createdAt: string;
}
```

## 2.16 Communication

```ts
interface Communication {
  id: string;
  matterId: string;
  workItemId?: string;
  reviewRecordId: string;
  channel: 'feishu_dm' | 'feishu_group' | 'feishu_thread';
  chatId: string;
  replyToMessageId?: string;
  recipientIds: string[];
  contentHash: string;
  approvedVersionHash: string;
  status: 'pending_send' | 'sending' | 'sent' | 'send_unknown' | 'failed' | 'superseded';
  idempotencyKey: string;
  providerMessageId?: string;
  sentAt?: string;
  failureCode?: string;
}
```

## 2.17 KnowledgeDocument / KnowledgeChunk

```ts
interface KnowledgeDocument {
  id: string;
  fileAssetId: string;
  domain: 'official_policy' | 'template' | 'historical_matter' | 'approved_reply' | 'working_draft';
  title: string;
  applicableEntityIds: string[];
  legalCategories: MatterCategory[];
  status: 'draft' | 'approved' | 'effective' | 'expired' | 'revoked';
  effectiveAt?: string;
  expiresAt?: string;
  approvedBy?: string;
  confidentiality: 'internal' | 'confidential' | 'restricted';
  indexVersion: number;
}

interface KnowledgeChunk {
  id: string;
  documentId: string;
  sequence: number;
  text: string;
  textHash: string;
  headingPath: string[];
  metadata: Record<string, string | number | boolean>;
  embeddingId?: string;
  indexStatus: 'pending' | 'indexed' | 'failed' | 'deleted';
}
```

## 2.18 LearningRecord / RuleCandidate

```ts
interface LearningRecord {
  id: string;
  reviewRecordId: string;
  matterCategory: MatterCategory;
  audienceType: string;
  riskLevel: string;
  contentChanges: ChangeItem[];
  styleChanges: ChangeItem[];
  legalChanges: ChangeItem[];
  isExceptionalCase: boolean;
  eligibleForRetrieval: boolean;
}

interface RuleCandidate {
  id: string;
  type: 'legal_check' | 'communication_style' | 'routing' | 'knowledge_gap';
  scope: Record<string, string[]>;
  proposal: string;
  evidenceLearningRecordIds: string[];
  status: 'proposed' | 'approved_for_trial' | 'active' | 'rejected' | 'rolled_back';
  approvedBy?: string;
  evaluationRunId?: string;
}
```

## 3. 值来源模型

推荐对重要字段使用来源元数据：

```ts
interface ProposedValue<T> {
  value: T;
  source: 'system' | 'codex' | 'human' | 'feishu';
  status: 'proposed' | 'confirmed' | 'rejected' | 'superseded';
  confidence?: number;
  evidenceRefs: string[];
  generatedBy?: string;
  updatedBy: string;
  updatedAt: string;
}
```

数据库不必把所有字段序列化为该结构，可使用字段元数据表，但必须保留等价能力。

## 4. 独立状态机

## 4.1 MessageCandidate

```text
pending_analysis
  → pending_confirmation
  → confirmed / linked / information_only / ignored / rejected
```

## 4.2 LegalMatter

```text
open → resolved → closed
  ↑       │
  └─ reopened
open/resolved → cancelled
```

`closed` 表示结案和归档检查已完成；`resolved` 表示当前问题已解决但仍可能等待后续观察或归档。

## 4.3 WorkItem

```text
todo → in_progress → pending_review → done
        ├→ waiting ───────────┤
        └→ blocked ───────────┤
任何未完成状态 → cancelled
```

进入 `waiting` 必须存在开放 `Dependency`；进入 `pending_review` 必须存在待审 `ReviewPackage`。

## 4.4 AgentRun

```text
queued → running → succeeded
                 ├→ needs_more_information
                 ├→ conflict_detected
                 ├→ failed → queued(重试)
                 └→ cancelled
失败超过阈值 → dead_letter
```

## 4.5 ReviewPackage

```text
draft → pending → approved
                ├→ changes_requested → pending
                ├→ rejected
                └→ cancelled
```

## 4.6 Communication

```text
pending_send → sending → sent
                       ├→ send_unknown
                       └→ failed → pending_send(确认后重试)
```

## 5. 关键不变量

1. 没有 `MessageCandidate` 确认记录，不创建来源为 AI 识别的正式事项。
2. 人工确认字段不能被 Codex 直接覆盖，只能产生新提案。
3. `WorkItem.status = waiting` 时必须存在开放依赖和下一次处理时间。
4. `AgentRun` 必须绑定不可变 `ContextSnapshot`。
5. `DraftArtifact` 不能直接成为 `Communication`。
6. `Communication` 必须绑定已批准的 `ReviewRecord`，且内容哈希一致。
7. 已失效知识文档不能作为正式依据；若被使用，AgentRun 校验失败。
8. 新文件版本到达后，基于旧文件的产物必须显示过期警告。
9. 审计事件只追加，不通过普通更新接口覆盖。
10. 规则候选未通过法务审批和回归评测不得启用。

## 6. PostgreSQL 表建议

首期建议表：

```text
feishu_messages
file_assets
context_snapshots
message_candidates
legal_matters
matter_source_links
work_items
deadlines
dependencies
agent_definitions
agent_execution_plans
agent_plan_steps
agent_runs
draft_artifacts
review_packages
review_records
communications
knowledge_documents
knowledge_chunks
learning_records
rule_candidates
audit_events
outbox_events
```

使用 `version` 字段进行乐观锁；异步事件采用事务 Outbox，避免数据库提交成功但队列消息丢失。
