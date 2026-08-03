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

## 2.1 认证与 Actor 边界

- 业务 API 从 HttpOnly Cookie Session 解析 Actor，应用服务接收的是后端 `RequestActor`，不直接读取浏览器声明的身份；
- `POST /api/v1/auth/local-session` 只在显式 `local` 或 `development` 环境签发本地单用户 Session；`test/staging/production` 均拒绝；
- `GET /api/v1/auth/session` 返回已验证 Actor 及 `identitySource`；
- `X-Actor-ID` 仅在 `LEGAL_WORKBENCH_ALLOW_DEVELOPMENT_ACTOR_HEADER=true` 且处于 `local/development` 时可用，审计来源标记为 `development_header`；
- 非本地环境必须配置至少 32 字符的非默认 Session Secret；生产环境缺少或无效 Session 返回 401，开发 Actor Header 配置会导致应用启动失败。

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
POST /api/v1/integrations/feishu/reconnect
POST /api/v1/integrations/feishu/reconcile
```

状态返回：

```ts
interface FeishuIntegrationStatus {
  connectionMode: 'long_connection' | 'webhook';
  status: 'disabled' | 'starting' | 'connected' | 'degraded' | 'disconnected' | 'failed';
  lastEventAt?: string;
  lastConnectedAt?: string;
  lastDisconnectedAt?: string;
  lastErrorCode?: string;
  lastErrorMessage?: string;
  reconnectCount: number;
  lastReconcileAt?: string;
  lastReconcileStatus?: 'completed' | 'partial' | 'local_only';
  lastReconcileMessage?: string;
}
```

`reconnect`、`reconcile` 需要认证 Actor、`Idempotency-Key` 和 Correlation ID，并写审计。补偿只覆盖配置群聊的指定时间窗；未配置时返回 `partial/local_only`。

## 3.3 消息研判与 AgentRun

```http
GET  /api/v1/feishu/messages?status=&search=&category=&chatId=&from=&to=
GET  /api/v1/feishu/messages/:messageId
GET  /api/v1/agent-runs?status=<status>&limit=<1..200>
GET  /api/v1/agent-runs/:runId
POST /api/v1/agent-runs/:runId/retry
POST /api/v1/agent-runs/:runId/cancel
POST /api/v1/feishu/messages/:messageId/analyse
POST /api/v1/feishu/messages/:messageId/retry-analysis
GET  /api/v1/feishu/messages/:messageId/analysis
POST /api/v1/feishu/messages/:messageId/attachments/:attachmentId/analysis-authorization
```

`analyse` 和 `retry-analysis` 必须携带 `Idempotency-Key`，首次接受返回 202，同一业务请求的幂等重放返回 200。人工重新分析创建新 AgentRun，历史运行不删除。

若待确认 Candidate 已存在，重新分析的合法相关结果原位更新其 AgentRun、建议和版本；若新结果为无关，则旧待确认 Candidate 转为 `rejected`，不可继续确认。已由人工确认或关联的 Candidate 不被重新分析覆盖。

`analysis` 返回：飞书消息来源与处理状态、ContextSnapshot 摘要、AgentRun 状态/版本/尝试/心跳/错误、研判 JSON、Candidate ID 与 `canRetry`。AgentRun 详情还返回实际授权来源列表、Prompt/Runtime/AgentDefinition 版本、状态历史、租约、校验错误、修复标志、可用时的 Token 用量和受限 stdout/stderr，用于审计。Candidate 详情返回递增分析 revision 与 superseded 关系。

附件授权接口要求认证 Actor、`Idempotency-Key` 和 Correlation ID，并只允许操作属于该消息且已下载的附件。附件响应返回下载/提取状态、SHA-256、页数、字符数和稳定错误码，不返回本地路径。授权只影响后续不可变 ContextSnapshot；Codex 事实引用必须精确匹配已纳入片段的附件 ID、文件名、页码、段落号和内容哈希。

`POST /api/v1/system/recover-pending-jobs` 与后台定时任务复用同一 PostgreSQL recovery service；写接口要求 Actor、Idempotency-Key、Correlation ID、权限和审计。恢复操作只重建 Outbox/状态，不在 API 线程运行 Codex。

## 4. 消息候选接口

```http
POST   /api/v1/inbox/candidates
GET    /api/v1/inbox/candidates
GET    /api/v1/inbox/candidates/:id
POST   /api/v1/inbox/candidates/:id/confirm-create
GET    /api/v1/inbox/candidates/:id/revisions
POST   /api/v1/inbox/candidates/:id/resolve
POST   /api/v1/inbox/candidates/:id/matter-update-proposals
GET    /api/v1/matter-update-proposals/:proposalId
POST   /api/v1/matter-update-proposals/:proposalId/review
```

`resolve` 只承载 `link_existing/information_only/ignore`。`update_existing` 必须改走 `matter-update-proposals`：创建时只登记 Candidate-Matter 更新关系和待审 Proposal，不改 Matter；审核接口同时校验 Proposal 版本与 `baseMatterVersion`，只应用法务逐字段批准的最终值。重新分析使用消息或 AgentRun retry API。

更新建议使用固定字段集合：`title/category/priority/deadline/owner/currentStatus/nextAction/newWorkItems`。服务端从当前 Matter 和 Candidate 的受控分析结果生成“当前值/消息提取值/AI 建议值”，不信任浏览器提交的 Actor ID，也不允许浏览器把建议直接写入正式记录。

```ts
interface ReviewMatterUpdateProposalRequest {
  proposalVersion: number;
  matterVersion: number;
  decisions: Array<{
    fieldName: string;
    decision: 'approve' | 'reject';
    finalValue?: unknown;
  }>;
  rejectionReason?: string;
}
```

Matter 已变化时返回 `409 ENTITY_VERSION_CONFLICT`，Proposal 保持 `pending`。新增 WorkItem、规范化 Deadline、Matter 更新、审计、Outbox 和幂等记录在同一 PostgreSQL 事务提交。

创建Candidate、`confirm-create`和新增WorkItem必须已建立认证 Session，写操作还必须携带：

```http
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
POST   /api/v1/work-items/:workItemId/start
POST   /api/v1/work-items/:workItemId/pause
POST   /api/v1/work-items/:workItemId/wait
POST   /api/v1/work-items/:workItemId/block
POST   /api/v1/work-items/:workItemId/resume
POST   /api/v1/work-items/:workItemId/complete
POST   /api/v1/work-items/:workItemId/cancel
POST   /api/v1/work-items/:workItemId/reopen
PATCH  /api/v1/work-items/:workItemId/owner
PATCH  /api/v1/work-items/:workItemId/deadline
PATCH  /api/v1/work-items/:workItemId/next-action
POST   /api/v1/work-items/:workItemId/dependencies
POST   /api/v1/work-items/:workItemId/dependencies/:dependencyId/resolve
```

新增WorkItem同样必须通过 Session 认证并携带`Idempotency-Key`。系统对Matter行加锁，保证并发新增时`sequenceOrder`稳定，并将业务写入、审计、Outbox和幂等记录在同一事务提交。

上述 WorkItem 状态、字段和依赖写接口还必须携带 `If-Match: <work-item-version>`；解决依赖的请求体另带 `dependencyVersion`。缺少 `If-Match` 返回 `428`，版本冲突返回 `409`。API 不直接写状态字符串，统一调用领域状态机；每个成功动作只增加一次 WorkItem 版本并追加审计、Outbox 和幂等结果。

状态请求：

```ts
interface WorkItemActionRequest {
  reason?: string;
  waitingPartyId?: string;
  blockerOwnerId?: string;
}
```

调用 `wait` 前先通过 `dependencies` 创建开放依赖；`pause/wait/block/cancel/reopen` 必须填写原因，`block` 还必须填写 `blockerOwnerId`。

## 6.1 今日工作台接口

```http
GET /api/v1/dashboard/today
```

接口只接受后端认证 Actor，并从 PostgreSQL 业务事实与实时健康快照投影以下队列：

```text
todayMustHandle
overdue
pendingCandidates
analysisFailed
waitingOthers
upcomingDeadlines
pendingOutboundReview
systemAbnormal
```

每项返回真实对象 `href`、截止时间、硬期限、法律风险、人工确认优先级、AI 建议优先级、等待时间和实际排序理由。队列按“硬期限 → 逾期 → 法律风险 → 人工确认优先级 → 等待时长 → 创建时间 → ID”确定性排序；AI 建议优先级不参与排序，也不得覆盖人工值。健康探针失败会形成脱敏的 `systemAbnormal` 项，不泄露原始异常或阻断其他业务队列。

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
POST /api/v1/evaluations/runs
GET  /api/v1/evaluations/runs/:runId
```

规则启用前必须关联通过的评测运行。

评估创建请求默认 `runtimeType=fake`，必须携带认证 Session、`Idempotency-Key` 和 Correlation ID；相同键只返回原 EvaluationRun。响应包含不可变 Fixture/AgentDefinition 版本、逐用例结果和相关性、分类、期限、角色、事实引用、推断误报、缺失信息、Schema 首次通过、平均耗时、失败率及重试率。`runtimeType=real` 还要求 `allowRealRuntime=true` 和服务端真实 Codex 门禁；当前 API 进程不持有 Codex 认证，因此真实路径由专用 CLI Runner 执行。评估不得启用规则、修改 Prompt 或改变 AgentDefinition 状态。

## 12.2 首次配置接口

```http
GET  /api/v1/setup/status
POST /api/v1/setup/feishu/validate
POST /api/v1/setup/feishu/start
POST /api/v1/setup/feishu/stop
POST /api/v1/setup/codex/validate
POST /api/v1/setup/codex/smoke-test
```

状态只返回 `configured`、掩码、稳定状态/错误码、可读说明和 Correlation ID，不返回 Secret。Codex 两个写接口返回 `202` 与 `checkRunId`，请求经事务 Outbox 交给只在 Worker 中可用的认证环境；外部运行期间不持有数据库事务。按当前用户确认，三个飞书写接口均不验证、不保存新 Secret、不启动连接，只返回 `not_executed / REAL_FEISHU_PHASE_DEFERRED`。

## 12.3 飞书群聊范围接口

```http
GET   /api/v1/settings/feishu-scopes
POST  /api/v1/settings/feishu-scopes
PATCH /api/v1/settings/feishu-scopes/:scopeId
POST  /api/v1/settings/feishu-scopes/:scopeId/compensate
```

新登记群聊固定为 `unapproved/disabled`。`PATCH` 支持 `allow/exclude/pause/resume`，写请求必须携带认证 Session、`Idempotency-Key`、Correlation ID 和当前版本 `If-Match`；旧版本返回 `409 ENTITY_VERSION_CONFLICT`，不得覆盖更新的人工决定。`allow/resume` 必须显式选择 `mentions_only` 或 `all_messages`。当前真实飞书阶段延后，补偿接口只写入 `last_compensation_status=not_executed` 与审计记录，返回 `REAL_FEISHU_PHASE_DEFERRED`，不调用飞书远端接口。

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
FeishuMessageReceived
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
| `FEISHU_MESSAGE_NOT_FOUND` | 飞书消息不存在 |
| `FEISHU_MESSAGE_NOT_AUTHORIZED` | 无权分析该消息 |
| `CONTEXT_BUILD_FAILED` | 上下文快照构建失败 |
| `AGENT_DEFINITION_NOT_FOUND` | Agent 定义不存在 |
| `AGENT_DEFINITION_DISABLED` | Agent 未启用或真实 Runtime 关闭 |
| `AGENT_RUNTIME_START_FAILED` | Runtime 启动失败 |
| `AGENT_RUNTIME_TIMEOUT` | Runtime 超时 |
| `AGENT_RUNTIME_CANCELLED` | Runtime 被取消 |
| `AGENT_OUTPUT_MISSING` | 结果文件缺失 |
| `AGENT_OUTPUT_INVALID_JSON` | 结果不是合法 JSON |
| `AGENT_OUTPUT_SCHEMA_INVALID` | Agent 输出不符合 Schema |
| `AGENT_OUTPUT_BUSINESS_RULE_INVALID` | Agent 输出违反业务/来源规则 |
| `CANDIDATE_ALREADY_EXISTS` | 同一消息已存在有效 Candidate |
| `UNSUPPORTED_OUTBOX_EVENT` | Outbox 事件未显式注册 |
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

当前已实现事件：`system.health`、`message.ingested`、`agent-run.updated`、`candidate.created`、`outbox.failed`。事件携带脱敏健康快照，前端收到后使对应 Query 失效并重新按权限查询；断线后指数退避重连并启用 15 秒轮询。

系统接口：

```http
GET  /api/v1/system/health
GET  /api/v1/system/metrics
POST /api/v1/system/recover-pending-jobs
GET  /api/v1/system/outbox/dead-letters
POST /api/v1/system/outbox/dead-letters/:id/requeue
```

上述写操作要求认证 Actor、`Idempotency-Key`、Correlation ID 和审计；死信重入队保留原记录并创建新 Outbox 事件。
