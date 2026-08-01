# API、事件与接口契约

## 1. 总体原则

- 前端只通过 FastAPI application API 访问领域能力；
- 外部系统结构在适配层转换，不进入页面和领域模型；
- 写接口必须支持幂等和乐观锁；
- 异步处理通过 Outbox + Worker；
- 所有外发统一经过审核门禁；
- OpenAPI作为前后端契约；后端使用Pydantic校验，前端客户端由OpenAPI生成或显式映射。

建议 API 前缀：`/api/v1`。

## 2. 通用响应

```ts
interface ApiResponse<T> {
  data: T;
  meta?: Record<string, unknown>;
  requestId: string;
}

interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  requestId: string;
}
```

写请求头：

```text
Idempotency-Key: <uuid>
If-Match: <entity-version>
```

## 3. 飞书接入接口

## 3.1 Webhook/长连接事件入口

内部接口：

```ts
interface FeishuInboundEvent {
  tenantKey: string;
  eventId: string;
  eventType: string;
  receivedAt: string;
  payload: unknown;
}
```

处理结果：

```ts
interface IngestResult {
  status: 'accepted' | 'duplicate' | 'rejected';
  messageIds: string[];
  outboxEventIds: string[];
}
```

事件接收只做校验、落库和投递，不在连接线程内运行 Codex。

## 3.2 同步状态

```http
GET /api/v1/integrations/feishu/status
POST /api/v1/integrations/feishu/pause
POST /api/v1/integrations/feishu/resume
POST /api/v1/integrations/feishu/reconcile
```

状态返回：

```ts
interface FeishuIntegrationStatus {
  connected: boolean;
  paused: boolean;
  lastEventAt?: string;
  lastProcessedAt?: string;
  lagSeconds?: number;
  lastCursor?: string;
  uncoveredWindow?: { from: string; to: string; reason: string };
  recentErrors: IntegrationError[];
}
```

## 4. 消息候选接口

```http
POST   /api/v1/inbox/candidates
GET    /api/v1/inbox/candidates
GET    /api/v1/inbox/candidates/:id
POST   /api/v1/inbox/candidates/:id/confirm-create
POST   /api/v1/inbox/candidates/:id/confirm-link
POST   /api/v1/inbox/candidates/:id/confirm-update
POST   /api/v1/inbox/candidates/:id/information-only
POST   /api/v1/inbox/candidates/:id/ignore
POST   /api/v1/inbox/candidates/:id/reanalyze
POST   /api/v1/inbox/candidates/batch
```

创建Candidate、`confirm-create`和新增WorkItem必须携带：

```http
X-Actor-ID: <legal-user-id>
Idempotency-Key: <unique-request-key>
```

相同幂等键和相同请求体返回原始结果；相同键用于不同请求体返回`409`。幂等检查通过PostgreSQL事务级advisory lock串行化，避免并发请求同时越过首次查询。

创建事项请求：

```ts
interface ConfirmCreateMatterRequest {
  candidateVersion: number;
  title: string;
  primaryCategory: string;
  secondaryCategories: string[];
  ownerId: string;
  legalRisk: string;
  businessImpact: string;
  priorityDecision?: PriorityDecisionInput;
  initialWorkItems: CreateWorkItemInput[];
  fieldOverrides: FieldOverride[];
}
```

重复请求必须返回同一个事项 ID。

## 5. 事项接口

```http
GET    /api/v1/matters
POST   /api/v1/matters
GET    /api/v1/matters/:matterId
PATCH  /api/v1/matters/:matterId
POST   /api/v1/matters/:matterId/resolve
POST   /api/v1/matters/:matterId/close
POST   /api/v1/matters/:matterId/reopen
GET    /api/v1/matters/:matterId/timeline
GET    /api/v1/matters/:matterId/sources
GET    /api/v1/matters/:matterId/artifacts
```

重新开启请求必须包含原因和触发来源。

## 6. WorkItem 接口

```http
POST   /api/v1/matters/:matterId/work-items
PATCH  /api/v1/work-items/:workItemId
POST   /api/v1/work-items/:workItemId/start
POST   /api/v1/work-items/:workItemId/wait
POST   /api/v1/work-items/:workItemId/block
POST   /api/v1/work-items/:workItemId/submit-review
POST   /api/v1/work-items/:workItemId/complete
POST   /api/v1/work-items/:workItemId/cancel
```

新增WorkItem同样必须携带`X-Actor-ID`和`Idempotency-Key`。系统对Matter行加锁，保证并发新增时`sequenceOrder`稳定，并将业务写入、审计、Outbox和幂等记录在同一事务提交。

等待请求：

```ts
interface StartWaitingRequest {
  dependencyType: 'material' | 'response' | 'decision' | 'approval' | 'external_event';
  waitingForId?: string;
  description: string;
  expectedAt?: string;
  nextReminderAt?: string;
}
```

## 7. 优先级确认接口

```http
GET  /api/v1/priority/proposals
POST /api/v1/work-items/:workItemId/priority/confirm
POST /api/v1/work-items/:workItemId/priority/recalculate
```

```ts
interface PriorityDecisionInput {
  acceptedProposalId?: string;
  priority: 'urgent' | 'high' | 'medium' | 'low';
  plannedCompleteAt?: string;
  reason?: string;
}
```

高优先级、模糊期限或与现有计划冲突时，API 不允许省略人工确认。

## 8. Agent 接口

```http
GET    /api/v1/agents
GET    /api/v1/agents/:agentId
POST   /api/v1/matters/:matterId/execution-plans
POST   /api/v1/execution-plans/:planId/approve
POST   /api/v1/execution-plans/:planId/start
POST   /api/v1/agent-runs/:runId/retry
POST   /api/v1/agent-runs/:runId/cancel
GET    /api/v1/agent-runs/:runId
GET    /api/v1/agent-runs/:runId/logs
GET    /api/v1/agent-runs/:runId/artifacts
```

创建执行计划：

```ts
interface CreateExecutionPlanRequest {
  workItemId?: string;
  objective: string;
  requestedArtifactTypes: string[];
  permittedFileIds: string[];
  permittedKnowledgeScopes: string[];
  planProposalRunId?: string;
}
```

后端必须验证资源均属于该事项或当前用户明确授权。

## 9. 审核接口

```http
GET  /api/v1/reviews
GET  /api/v1/reviews/:reviewPackageId
POST /api/v1/reviews/:reviewPackageId/approve
POST /api/v1/reviews/:reviewPackageId/approve-with-edits
POST /api/v1/reviews/:reviewPackageId/reject
POST /api/v1/reviews/:reviewPackageId/request-information
POST /api/v1/reviews/:reviewPackageId/defer
POST /api/v1/reviews/:reviewPackageId/internal-only
```

修改后通过：

```ts
interface ApproveWithEditsRequest {
  packageVersionHash: string;
  editedOutboundContent?: string;
  editedArtifact?: Record<string, unknown>;
  reasonCodes: string[];
  comment?: string;
  isExceptionalCase: boolean;
  allowAsLearningExample: boolean;
  allowRuleCandidate: boolean;
}
```

服务端重新计算批准版本哈希，并生成不可变 `ReviewRecord`。

## 10. 外发接口

```http
POST /api/v1/reviews/:reviewPackageId/send
GET  /api/v1/communications/:communicationId
POST /api/v1/communications/:communicationId/reconcile
POST /api/v1/communications/:communicationId/retry
```

发送请求只接受审核包 ID，不接受任意正文：

```ts
interface SendApprovedCommunicationRequest {
  reviewRecordId: string;
  packageVersionHash: string;
  idempotencyKey: string;
}
```

发送门禁校验：

1. ReviewRecord 为通过或修改后通过；
2. ReviewRecord 属于该 ReviewPackage；
3. 批准版本哈希与当前待发版本一致；
4. 原会话仍可访问；
5. 发送对象和回复位置未被修改；
6. 不存在更新的高优先级事实或撤销标记；
7. 同一幂等键没有成功发送记录。

## 11. 知识库接口

```http
GET    /api/v1/knowledge/directories
POST   /api/v1/knowledge/directories
POST   /api/v1/knowledge/directories/:id/rescan
GET    /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents/:id
PATCH  /api/v1/knowledge/documents/:id
POST   /api/v1/knowledge/documents/:id/approve
POST   /api/v1/knowledge/documents/:id/expire
POST   /api/v1/knowledge/documents/:id/reindex
GET    /api/v1/knowledge/search-audit
```

检索内部接口：

```ts
interface KnowledgeSearchRequest {
  query: string;
  domains: string[];
  applicableEntityIds: string[];
  matterCategories: string[];
  asOf: string;
  maxConfidentiality: string;
  topK: number;
}

interface KnowledgeSearchResult {
  documentId: string;
  chunkId: string;
  title: string;
  locator: string;
  text: string;
  keywordScore: number;
  vectorScore?: number;
  metadataScore: number;
  effectiveStatus: string;
  citationId: string;
}
```

Agent只能通过该接口检索，不直接查询PostgreSQL表或扫描本地目录。向量召回未启用时`vectorScore`为空。

## 12. 学习和规则接口

```http
GET  /api/v1/learning/records
GET  /api/v1/rules/candidates
POST /api/v1/rules/candidates/:id/approve-trial
POST /api/v1/rules/candidates/:id/reject
POST /api/v1/rules/candidates/:id/activate
POST /api/v1/rules/candidates/:id/rollback
GET  /api/v1/evaluations
POST /api/v1/evaluations/run
```

规则启用前必须关联通过的评测运行。

## 13. 日报和复盘接口

```http
GET  /api/v1/reports/daily?date=YYYY-MM-DD
POST /api/v1/reports/daily/:date/generate
GET  /api/v1/matters/:matterId/retrospective
POST /api/v1/matters/:matterId/retrospective/generate
GET  /api/v1/reports/weekly
```

日报生成分两步：

1. 系统生成结构化事实底稿；
2. Codex Agent基于底稿生成归纳文本。

## 14. 领域事件

```text
FeishuEventReceived
FeishuMessagePersisted
FileAssetDownloaded
ContextSnapshotCreated
MessageAnalysisRequested
MessageCandidateCreated
MessageCandidateConfirmed
MatterCreated
MatterUpdated
MatterReopened
WorkItemCreated
PriorityConfirmationRequired
PriorityConfirmed
AgentPlanCreated
AgentPlanApproved
AgentRunRequested
AgentRunStarted
AgentRunCompleted
AgentRunFailed
AgentConflictDetected
ReviewPackageCreated
ReviewDecisionRecorded
CommunicationSendRequested
CommunicationSent
CommunicationSendUnknown
KnowledgeDocumentIndexed
KnowledgeDocumentExpired
LearningRecordCreated
RuleCandidateCreated
DailyReportRequested
```

所有事件包含：

```ts
interface DomainEventEnvelope<T> {
  eventId: string;
  eventType: string;
  aggregateType: string;
  aggregateId: string;
  aggregateVersion: number;
  occurredAt: string;
  actor: { type: 'user' | 'system' | 'agent' | 'integration'; id: string };
  correlationId: string;
  causationId?: string;
  payload: T;
}
```

## 15. 错误码建议

| 错误码 | 含义 |
|---|---|
| `CANDIDATE_ALREADY_PROCESSED` | 候选已处理 |
| `ENTITY_VERSION_CONFLICT` | 乐观锁冲突 |
| `PRIORITY_CONFIRMATION_REQUIRED` | 需要法务确认优先级 |
| `AGENT_OUTPUT_INVALID` | Agent 输出不符合 Schema |
| `AGENT_ACCESS_DENIED` | Agent 请求未授权数据或工具 |
| `KNOWLEDGE_SOURCE_EXPIRED` | 使用了失效资料 |
| `REVIEW_REQUIRED` | 操作缺少审核记录 |
| `REVIEW_VERSION_MISMATCH` | 审核版本与发送版本不一致 |
| `COMMUNICATION_RESULT_UNKNOWN` | 发送结果不确定 |
| `FEISHU_SCOPE_REVOKED` | 飞书权限已撤销 |
| `FILE_VERSION_SUPERSEDED` | 文件版本已被替代 |
| `LEGAL_HOLD_ACTIVE` | 数据处于保全状态 |

## 16. SSE 事件

前端可订阅：

```http
GET /api/v1/events/stream
```

事件包括：

- 新消息候选；
- Agent 状态更新；
- 新审核项；
- 发送结果；
- 飞书连接告警；
- 知识索引完成；
- 任务期限临近。

SSE 只发送对象 ID 和最小摘要，前端再按权限查询详情。
