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
  status:
    | 'received'
    | 'queued_for_analysis'
    | 'context_prepared'
    | 'agent_queued'
    | 'analysing'
    | 'candidate_created'
    | 'ignored'
    | 'analysis_failed'
    | 'dead_letter';
  unsupportedReason?: string;
  contextSnapshotId?: string;
  lastAgentRunId?: string;
  analysisAttempts: number;
  failureCode?: string;
  failureMessage?: string;
  version: number;
  createdAt: string;
}
```

唯一约束：

- `(tenant_id, event_id)`；
- `(tenant_id, message_id)`；消息正文变化进入不可变 `FeishuMessageVersion`，不覆盖历史审计。

`integration_connections` 持久化连接模式、状态、最近连接/断开/事件、错误、重连次数和最近补偿结果。`feishu_message_versions` 为每次创建、编辑或撤回追加修订。迁移 `20260803_0008` 将原 `feishu_attachments` 原地重命名为 `message_attachments` 并保留历史行，增加提取状态、Extractor版本、页数、字符数和稳定错误码；`document_versions`、`document_extractions`、`document_segments` 分别保存文件版本、每次解析结果和带页码/段落/偏移/哈希的正文片段，`storage_quota_reservations` 用 PostgreSQL 协调并发下载配额。降级恢复原附件表名和原有行。

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
  sourceType: string;
  sourceId: string;
  snapshotVersion: number;
  messageIds: string[];
  participantIds: string[];
  attachmentIds: string[];
  includedSegments: Array<Record<string, unknown>>;
  excludedSegments: Array<Record<string, unknown>>;
  threadMetadata: Record<string, unknown>;
  permissionSnapshot: Record<string, unknown>;
  content: Record<string, unknown>;
  builderVersion: string;
  selectionPolicyVersion: string;
  currentMessageVersion: number;
  attachmentVersionHash: string;
  truncated: boolean;
  truncationReason?: string;
  originalSize: number;
  includedSize: number;
  contentHash: string;
  createdAt: string;
}
```

快照一经创建不可修改。当前消息必选，父消息、根消息和同线程最近消息由确定性规则限量选取；只有人工授权且提取成功的附件片段可进入快照，并受片段数量、单段字符和总字符限制。纳入与排除的定位及原因均持久化。复用哈希同时包含消息/附件版本、授权/提取状态、片段引用、上下文排序、Builder 版本和选择策略版本；消息数、单条字符、总字符、附件数及附件片段的截断原因与原始/纳入大小均持久化。`(source_type, source_id, content_hash)` 唯一，并通过事务级 advisory lock 避免并发重复。

0004 迁移不会按旧版客户端提供的 `content_hash/source_ids` 合并历史审计行；每条旧快照以自身 UUID 回填 `source_id`，因此重复旧数据仍被完整保留。0003 Candidate 中可能存在的外部 `agent_run_id` 先保存到 `analysis_payload.legacyAgentRunId`，downgrade 时恢复。

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
  feishuMessageId: string;
  requiresManualReview: boolean;
  analysisPayload: Record<string, unknown>;
  confirmedBy?: string;
  confirmedAt?: string;
}
```

同一 `feishu_message_id` 对 `pending_confirmation/confirmed/linked` 建立部分唯一索引，防止重复有效 Candidate。消息研判结果无论置信度高低都不自动建立 Matter。

`candidate_revisions` 为每次合法分析追加 `revision/agent_run_id/analysis_payload/created_at/superseded_at/superseded_by`。当前 Candidate 可随待确认重分析推进版本，但旧 revision 不修改；已经人工处理的 Candidate 不被重新分析静默覆盖。

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
  priority: 'urgent' | 'high' | 'medium' | 'low';
  prioritySource: 'system' | 'agent_suggested' | 'legal_confirmed';
  targetDeadlineAt?: string;
  nextAction?: string;
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

迁移 `20260803_0009` 增加 Matter 的人工确认优先级、目标期限和下一步行动，并新增 `matter_update_proposals`。Proposal 保存创建时的 `base_matter_version`、固定结构的建议值、逐字段决定和法务最终值；状态为 `pending/approved/partially_approved/rejected/superseded`。任何批准都必须在同一事务中锁定 Proposal 和 Matter 并核对两个版本，迟到审核不能覆盖新 Matter 版本。

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
    | 'paused'
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
  pausedReason?: string;
  isBlocked: boolean;
  blockerReason?: string;
  blockerOwnerId?: string;
  plannedStartAt?: string;
  plannedCompleteAt?: string;
  completedAt?: string;
  cancelledAt?: string;
  cancelReason?: string;
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

详细协议见 `AGENT_PROTOCOL.md`。`AgentDefinition` 以 `(key, version)` 唯一。正式执行仅允许 `active` 版本；AgentRun 同时保留定义引用和完整 `promptSnapshot`，后续版本不能改写历史运行。

```ts
interface AgentDefinition {
  id: string;
  key: string;
  name: string;
  version: string;
  description: string;
  status: 'draft' | 'trial' | 'active' | 'paused' | 'retired';
  promptTemplate: string;
  inputSchema: Record<string, unknown>;
  outputSchema: Record<string, unknown>;
  allowedTools: string[];
  allowedKnowledgeScopes: string[];
  timeoutSeconds: number;
  maxRetries: number;
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
  matterId?: string;
  workItemId?: string;
  feishuMessageId?: string;
  agentDefinitionId: string;
  contextSnapshotId: string;
  status:
    | 'queued'
    | 'preparing'
    | 'running'
    | 'validating'
    | 'completed'
    | 'needs_more_information'
    | 'failed'
    | 'timed_out'
    | 'cancelled'
    | 'dead_letter';
  objective: string;
  inputPayload: Record<string, unknown>;
  outputPayload: Record<string, unknown>;
  rawStdout?: string;
  rawStderr?: string;
  promptSnapshot: string;
  workingDirectory: string;
  startedAt?: string;
  heartbeatAt?: string;
  finishedAt?: string;
  timeoutAt?: string;
  attemptNumber: number;
  maxAttempts: number;
  failureCode?: string;
  failureMessage?: string;
  runtimeVersion?: string;
  agentDefinitionVersion: string;
  promptVersion: string;
  validationErrors: string[];
  repairAttempted: boolean;
  tokenUsage?: Record<string, number>;
  workerId?: string;
  leaseExpiresAt?: string;
  correlationId: string;
  createdBy: string;
  version: number;
}
```

`agent_run_status_events` 对每次领域状态迁移只追加记录时间、前后状态、Correlation ID、尝试次数和失败摘要。`candidate_revisions` 对同一 Candidate 保存递增 revision、AgentRun、完整分析 Payload 与 superseded 关系；迁移 `20260801_0006` 可升降级。

### 2.12.1 AgentRunSource

`AgentRunSource` 只追加记录本次实际授权使用的来源：`feishu_message`、`context_snapshot`、`attachment`、`knowledge_document`、`historical_matter`、`approved_example`。消息研判记录快照、当前/父/线程消息、附件元数据，并为每个实际纳入的附件片段追加一条真实内容哈希和页码/段落定位来源；不保存或返回本地文件路径。

## 2.13 DraftArtifact

Agent 只能产出草稿，不直接生成正式外发记录。

```ts
interface DraftArtifact {
  id: string;
  agentRunId: string;
  artifactType: string;
  title: string;
  content: string;
  structuredPayload: Record<string, unknown>;
  version: number;
  status: 'draft' | 'superseded' | 'submitted' | 'approved' | 'rejected';
  createdAt: string;
}
```

本轮仅建立通用持久化边界，消息研判的业务产物直接进入 `MessageCandidate`。

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
        ├→ paused ─────┐
        ├→ waiting ────┼→ in_progress
        └→ blocked ────┘
任何非终态 → cancelled
done/cancelled → todo（reopen，必须填写原因）
```

进入 `waiting` 必须存在开放 `Dependency`；恢复 waiting 前必须先解决全部开放依赖；完成前不得存在开放依赖。暂停、等待、阻塞、取消和重新打开均记录原因，阻塞还必须记录责任人。负责人、计划完成时间和下一步行动的变更与状态迁移一样经过领域服务、版本检查、审计和 Outbox。

## 4.4 AgentRun

```text
queued → preparing → running → validating → completed
   └→ cancelled       │          ├→ needs_more_information
                      ├→ failed ───────┘
                      └→ timed_out
failed/timed_out → queued(重试) 或 dead_letter
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
3. `WorkItem.status = waiting` 时必须存在开放依赖；存在开放依赖时不得恢复或完成。
4. `AgentRun` 必须绑定不可变 `ContextSnapshot`。
5. `DraftArtifact` 不能直接成为 `Communication`。
6. `Communication` 必须绑定已批准的 `ReviewRecord`，且内容哈希一致。
7. 已失效知识文档不能作为正式依据；若被使用，AgentRun 校验失败。
8. 新文件版本到达后，基于旧文件的产物必须显示过期警告。
9. 审计事件只追加，不通过普通更新接口覆盖。
10. 规则候选未通过法务审批和回归评测不得启用。

## 6. PostgreSQL表与Python映射

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
agent_run_sources
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
outbox_dead_letters
integration_connections
feishu_message_versions
message_attachments
document_versions
document_extractions
document_segments
storage_quota_reservations
matter_update_proposals
agent_run_status_events
candidate_revisions
```

使用 `version` 字段进行乐观锁；异步事件采用事务 Outbox，避免数据库提交成功但队列消息丢失。


### 持久化约定

- API/Agent契约使用Pydantic；领域模型与SQLAlchemy映射分离；
- `raw_payload`、Agent原始输出等非稳定结构使用JSONB；
- 高频筛选字段使用明确列和组合索引，不把全部业务字段塞入JSONB；
- 知识片段包含`search_vector tsvector`、trigram索引和可空`embedding vector`；
- `audit_events`、`review_records`和`outbox_events`采用追加式写入；
- 所有用户可修改聚合包含`version`和`updated_at`。
