# Codex Agent Runtime 与统一执行协议

## 1. 目标

本协议用于约束所有 Codex Agent 的注册、输入、执行、输出、权限、审核和质量评价。新增 Agent 必须遵循本协议，不得直接在页面组件、Worker 或业务服务中拼接自由文本并调用 Codex。

### 1.1 实现状态

- **已实现**：持久化 AgentDefinition/AgentRun/AgentRunSource/DraftArtifact，以及 `message_judgement@2.2.0`、严格 Codex Structured Output Schema、CLI 版本/显式隔离认证健康检查、一次受控修复、状态事件、Worker 租约、Candidate revision、附件片段引用、Celery 调度和 PostgreSQL 恢复。
- **部分实现**：容器模式使用专用 UID、最小环境变量和工作目录约束；宿主机模式不具备可证明的 OS 级读取白名单。
- **占位实现**：DraftArtifact 本轮仅建模，未开发通用产物 UI。
- **尚未实现**：事项归并、任务规划、优先级建议、结果汇总、知识检索和所有专业 Agent。本文中对这些 Agent 的约束是后续设计要求，不代表已上线。

## 2. Agent 分层

## 2.1 核心 Agent

| Agent | 主要职责 | 禁止事项 |
|---|---|---|
| 消息研判 Agent | 法务相关性、消息作用、分类和期限候选 | 创建正式事项、发送消息 |
| 事项归并 Agent | 关联现有事项、拆分多事项、建议重新开启 | 自动合并或关闭正式事项 |
| 任务规划 Agent | 拆解 WorkItem、形成执行计划 | 改写人工确认事实 |
| 优先级建议 Agent | 软优先级、工作负荷和影响分析 | 覆盖硬期限和人工优先级 |
| 结果汇总 Agent | 汇总结论、暴露冲突、形成审核材料 | 静默消解专业冲突 |
| 日报与复盘 Agent | 基于事实底稿生成日报和复盘 | 凭会话记忆编造事实 |

## 2.2 专业 Agent

| Agent | 首要输出 |
|---|---|
| 合同 Agent | 条款提取、风险、修改建议、待确认问题 |
| 文案 Agent | 合规问题、修改建议、替代表达 |
| 人力 Agent | 关系定性、流程、材料和劳动风险 |
| 纠纷 Agent | 事实、争议焦点、证据、策略和时限 |
| 知产 Agent | 权利链、授权、侵权风险和处置建议 |

## 2.3 支持 Agent/能力

| Agent/能力 | 定位 |
|---|---|
| Knowledge Search | 默认作为受控工具，复杂研究时可升级为 AgentRun |
| 回复 Agent | 将已批准的事实和策略转化为目标受众语言，不重新作法律结论 |
| 学习 Agent | 分析审核差异，生成样例、规则候选和改进建议 |

## 3. Codex Runtime

`CodexCliRuntime` 是当前唯一业务 Codex 调用入口，由 Celery `feishu.process_message` Worker 调用。旧的独立 runner 占位进程不承载业务执行。

### 3.1 每次运行必须隔离

每个 AgentRun 创建独立目录：

```text
data/codex-runs/<run-id>/                 # 第一次尝试
├─ input.json
├─ prompt.md
├─ output.schema.json
├─ allowed_sources/
├─ output.json
├─ stdout.log
├─ stderr.log
├─ metadata.json
├─ empty_home/
└─ attempts/002/...                    # 后续尝试，不覆盖历史
```

运行结束后：

- input/output、stdout/stderr、提示词快照和 metadata 保留作为审计材料；
- 文件使用 0600，目录使用 0700；
- 密钥、Feishu Token、数据库/Redis URL 不写入运行目录；
- 不复用长期 Codex 会话。

Runtime 使用 `codex exec --ephemeral --ignore-user-config --ignore-rules --strict-config --sandbox read-only`，并显式禁用 Shell/统一执行/快照、代码模式、多 Agent、Apply Patch、网络搜索、MCP Apps、浏览器、Computer Use、插件和技能发现。确定性构造的授权快照以标记为不可信证据的 JSON 同时写入 `input.json` 和 stdin；Codex 不需要、也不能通过工具自行寻找输入。它实现超时 terminate/kill、心跳、stdout/stderr 大小限制和环境变量白名单；子进程的 `HOME` 与 `CODEX_HOME` 均固定为本次运行的空目录，父进程的 Codex 配置/认证目录不会被继承，首期认证只允许通过白名单中的 `OPENAI_API_KEY` 注入。Docker Worker 还将子进程降权到 `codex-agent` UID/GID，并不挂载知识目录；Worker 当前固定 `--concurrency=1`，每次运行期间把目录交给子用户，结束后收回所有权，避免同容器并发子进程互读运行目录。

Runtime 读取 `output.json` 后依次执行 JSON、Pydantic 和业务规则校验。首次失败可把脱敏校验摘要交回同一 Runtime，且必须复用同一 ContextSnapshot、不得增加业务资料、必须返回完整 JSON；第二次失败进入正式失败/死信流程，不做正则或手工 JSON 修补。

### 3.2 撤回消息语义

- 消息撤回后保留已落库消息版本、附件、AgentRun 和 Audit，不删除历史；
- 自动分析资格由集中 policy 决定，并在自动 Gate、Outbox dispatch、Worker prepare/runtime start 与成功结果持久化时重新校验；
- Runtime 尚未开始时 no-op；已经真正开始时不强杀进程，但输出不得新建或更新有效 Candidate；
- 只有 `actor_source=user` 且请求明确携带并持久化 `override_recalled=true` 时可以 override；普通用户请求不等于 override，request、dispatch/prepare、runtime start 和 success persistence 均写入或复核可追溯 Audit。

**边界说明**：Codex CLI 只读 sandbox 不等于一个经证明的主机文件读取白名单，主机模式仍受父进程 OS 权限影响。为调用 Codex 模型，进程仍需到 Codex/OpenAI 服务的传输网络；“禁用网络”在当前实现中指禁用 Agent 可控的 Web/浏览器/MCP 工具，并不等于容器零出网。生产部署仍应增加目的地址 allowlist/代理或独立容器网络策略。高敏感数据的真实执行应优先使用专用容器/用户，不得将当前实现宣称为完全隔离。

### 3.3 工具权限

AgentDefinition 声明可用工具，例如：

- `knowledge.search`；
- `file.read_authorized`；
- `file.extract_text`；
- `matter.read_snapshot`；
- `artifact.write_draft`。

当前消息研判 Runtime 的命令行强制禁用；AgentDefinition 中的 `allowedTools=[]` 不是唯一安全控制。默认禁止：

- 任意 Shell；
- 任意网络访问；
- 读取未授权目录；
- 删除或覆盖源文件；
- 发送飞书消息；
- 修改正式领域对象；
- 修改 AgentDefinition 或提示词。

确需 Shell 的内部开发 Agent 与业务法务 Agent 必须分开运行环境。

### 3.4 提示注入防护

- 消息、合同、网页和附件全部标记为不可信内容；
- 系统提示明确禁止执行文档中的指令；
- 工具服务再次校验目录、资源 ID 和 Matter 权限；
- 任何扩大权限的请求返回错误并写入审计；
- 输出中的工具调用建议不自动执行。

## 4. AgentDefinition

```ts
interface AgentDefinition {
  id: string;
  key: string;
  name: string;
  description: string;
  version: string;
  promptTemplate: string;
  inputSchema: Record<string, unknown>;
  outputSchema: Record<string, unknown>;
  allowedTools: string[];
  allowedKnowledgeScopes: string[];
  timeoutSeconds: number;
  maxRetries: number;
  requiresHumanReview: boolean;
  status: 'draft' | 'trial' | 'active' | 'paused' | 'retired';
}
```

`key + version` 数据库唯一；只有 `active` 版本可执行。每次 AgentRun 保留完整 prompt 快照，定义升级不改写历史。

配置文件建议位于`apps/backend/agent_definitions/`或后续独立受控目录：

```text
agents/
├─ core/message-triage/
├─ core/matter-linking/
├─ core/task-planning/
├─ core/priority-advisor/
├─ core/result-synthesizer/
├─ core/daily-review/
├─ professional/contract/
├─ professional/copy/
├─ professional/hr/
├─ professional/dispute/
├─ professional/ip/
├─ support/reply/
└─ support/learning/
```

每个目录包含：

```text
agent.yaml
system.md
output.schema.json
examples/
evaluation/
```

### 4.1 已激活定义：`message_judgement@2.2.0`

该 Agent 只处理消息法务相关性、消息作用、行动性、建议标题/分类/期限、事实/推断、缺失信息、理由和置信度。`allowedTools=[]`、`allowedKnowledgeScopes=[]`、`requiresHumanReview=true`。

输入同样由 Pydantic `MessageJudgementInput` 定义完整字段并生成持久化 `input_schema`；Runtime 执行前先核对定义中的 Schema 与该版本运行契约完全一致，再校验实际 payload，额外字段或权限布尔值不合法会在启动 Codex 前失败。

输出 JSON 顶层严格为：

```text
legalRelevance, messageRole, actionability, suggestedTitle,
categoryCandidates, deadlineCandidates, confirmedFacts,
inferredFacts, missingInformation, reasons, confidence
```

- Pydantic 使用 `extra=forbid`，所有置信度限制在 0–1；
- 必须输出纯 JSON，不得使用 Markdown 代码块；
- 每条 `confirmedFacts` 必须且只能选择 `sourceMessageId` 或 `attachmentCitation`；消息 ID 必须在快照 `allowedMessageIds` 内，附件引用必须精确匹配已纳入片段的附件 ID、文件名、页码、段落号和内容哈希；
- 事实与推断严格分字段；输出或业务规则失败时不创建 Candidate；
- `irrelevant` 或 `actionability=ignore` 不创建 Candidate；其他合法结果只创建 `pending_confirmation` Candidate，不自动建 Matter。

## 5. 统一输入协议

本节是后续事项/专业 Agent 的通用目标协议。当前消息研判使用更小的 `runId + contextSnapshot + constraints` 输入，不接收 Matter、WorkItem 或知识库查询权限。

```ts
interface AgentRequest {
  requestVersion: '1.0';
  runId: string;
  agentId: string;
  objective: string;
  matter: MatterSnapshot;
  workItem?: WorkItemSnapshot;
  contextSnapshot: ContextSnapshotRef;
  confirmedFacts: Fact[];
  unconfirmedFacts: Fact[];
  entities: EntityRef[];
  deadlines: DeadlineRef[];
  sourceReferences: SourceRef[];
  fileReferences: AuthorizedFileRef[];
  knowledgePolicy: KnowledgePolicy;
  requestedOutputs: ArtifactRequest[];
  constraints: string[];
  upstreamResults: UpstreamResultRef[];
  idempotencyKey: string;
}
```

### 5.1 Fact

```ts
interface Fact {
  id: string;
  statement: string;
  status: 'confirmed' | 'proposed' | 'disputed';
  evidenceRefs: string[];
  confirmedBy?: string;
}
```

Agent不得把 `proposed` 或 `disputed` 事实写成已确认事实。

### 5.2 KnowledgePolicy

```ts
interface KnowledgePolicy {
  allowedDomains: Array<'official_policy' | 'template' | 'historical_matter' | 'approved_reply'>;
  applicableEntityIds: string[];
  matterCategories: string[];
  maxConfidentiality: 'internal' | 'confidential' | 'restricted';
  asOf: string;
  includeExpired: false;
  requireApprovedSources: boolean;
}
```

## 6. 统一输出协议

本节是后续专业 Agent 的通用目标协议；当前 `message_judgement` 以第 4.1 节和代码中的 Pydantic Schema 为准。

```ts
interface AgentResult {
  resultVersion: '1.0';
  runId: string;
  agentId: string;
  agentVersion: string;
  status:
    | 'completed'
    | 'needs_more_information'
    | 'conflict_detected'
    | 'out_of_scope'
    | 'failed';
  executiveSummary: string;
  confirmedFactsUsed: FactUsage[];
  inferredFacts: Inference[];
  findings: Finding[];
  risks: RiskItem[];
  recommendations: Recommendation[];
  missingInformation: MissingInformation[];
  conflicts: ConflictItem[];
  citations: Citation[];
  draftArtifacts: DraftArtifactPayload[];
  confidence: number;
  limitations: string[];
  suggestedNextActions: SuggestedAction[];
}
```

### 6.1 结论必须可追溯

```ts
interface Finding {
  id: string;
  title: string;
  conclusion: string;
  type: 'fact' | 'legal_issue' | 'contract_issue' | 'process_issue' | 'communication_issue';
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  evidenceRefs: string[];
  citationIds: string[];
  confidence: number;
  conditions: string[];
}
```

没有依据的结论不得放入 `findings`，只能放入 `limitations` 或 `missingInformation`。

### 6.2 Citation

```ts
interface Citation {
  sourceRef: string;
  sourceType: 'context_snapshot' | 'feishu_message' | 'attachment' | 'knowledge_document' | 'historical_matter' | 'approved_example';
  locator?: string;
  contentHash?: string;
  title: string;
  internalPrecedent: boolean;
  authorityType?: string;
  authorityRole?: string;
  authorityStatus?: 'effective' | 'superseded' | 'repealed' | 'unknown';
  jurisdiction?: string;
}
```

模型只能选择 authorized `sourceRef`；服务端从持久化来源重建其余 citation 元数据，不能信任模型自报 title、locator、hash 或 authority。前端应可从引用跳转至授权范围内的原始位置。

## 7. Agent 停止条件

以下情况必须返回 `needs_more_information` 或 `conflict_detected`，不得强行补全：

- 缺少决定性合同或附件；
- 无法确认公司或签约主体；
- 关键事实互相矛盾；
- 使用资料版本冲突；
- 正式制度已失效；
- 任务超出 Agent 范围；
- 需要法务选择谈判策略；
- 需要未授权数据；
- 结论会直接影响诉讼、监管或重大外发而依据不足。

## 8. 执行计划

Butler Planning 只能在五个已注册 Specialist 中生成最多四步的无环 DAG。确定性编排器按拓扑波次运行：每个 Step 只获得自身 Context Builder 结果、直接依赖的 latest-valid 输出，以及这些依赖 Run 已持久化的原始授权来源；兄弟 Step 和旧依赖 Run 不得泄漏。

每个 Specialist Run 固定保存 `dependencyRunIds`。单 Step rerun 必须在 Plan/Step 行锁内确认目标仍是 current Run、直接依赖仍是 current valid lineage，并原子设置新的 `latestRunId`；同一 Plan 不允许并发 rerun。上游重跑会把依赖旧 Run 的下游标记 `STALE_DEPENDENCY_RUN`，其旧输出和来源从新 synthesis 中排除，直到下游显式重跑。

Planning、Specialist、Synthesis 的成功或失败只能更新当前 Plan/Step 指向的 Run。Attempt lease 过期恢复必须通过数据库 CAS；旧 Worker、续租竞态或已被替代的 Run 只保留历史审计，不能覆盖当前结果。

冲突由 Butler Synthesis 显式列入 `conflicts`，最终只创建 pending `ReviewPackage` 供法务选择；Agent 不得自行修改 Matter/WorkItem 或发送 Communication。

## 9. 回复 Agent 约束

回复 Agent输入必须包含已经形成的：

- 沟通目标；
- 已确认事实；
- 法务策略；
- 允许表达的结论；
- 不得表达的内容；
- 目标受众；
- 渠道和期望长度；
- 历史审核通过样例。

回复 Agent不得：

- 新增未经专业 Agent或法务确认的法律结论；
- 删除审核包中的关键风险而不标注；
- 将不确定事实改写为确定事实；
- 直接发送消息。

输出至少包含：

- 推荐版本；
- 可选版本（确有策略差异时）；
- 每个版本的使用条件；
- 生成理由；
- 引用的表达样例 ID。

## 10. 学习 Agent 约束

学习 Agent仅处理已完成审核的数据。

输出分为：

- `LegalDecisionMemory`：法律判断、事实和流程修正；
- `CommunicationStyleMemory`：受众、长度、语气和结构偏好；
- `RuleCandidate`：需审批的规则候选；
- `KnowledgeGap`：缺失或过期资料；
- `AgentImprovementSuggestion`：提示词、工具或流程问题。

一次审核默认不得形成全局规则。只有多条一致样例或法务主动标记时，才能生成规则候选。

## 11. 质量评价

## 11.1 系统质量

- 执行成功率；
- 超时率；
- Schema 失败率；
- 重试和死信率；
- 工具调用失败率；
- 平均耗时；
- 目录/权限拒绝次数。

## 11.2 内容质量

- 事实准确率；
- 关键问题覆盖率；
- 高风险遗漏率；
- 引用覆盖率；
- 过期资料引用率；
- 无依据推断率；
- 缺失信息识别率；
- 冲突发现率。

## 11.3 审核质量

审核结果分级：

- 原样通过；
- 轻微表达修改；
- 重大内容修改；
- 驳回；
- 要求补充材料。

原因标签：

- 事实错误；
- 法律判断错误；
- 风险遗漏；
- 引用错误；
- 使用旧资料；
- 结论过度；
- 缺少执行方案；
- 语气或长度不适合；
- 对象不匹配；
- 分类/路由错误；
- 不应发送。

不得仅用文本编辑距离评价质量。

## 12. 发布和版本治理

Agent 发布流程的目标状态：

```text
draft → trial → active → paused → retired
```

当前持久化枚举为 `draft/trial/active/paused/retired`；仅 `active` 可正式执行。完整的评测发布自动化仍属后续能力。

从 `trial` 进入 `active` 前必须：

- 输出 Schema 全部通过；
- 关键结论具备引用；
- 无越权工具调用；
- 固定评测集达到门槛；
- 法务重大修改率低于配置阈值；
- 高风险遗漏率满足要求。

每次提示词、Schema、工具权限或知识策略变更都增加 Agent 版本，并保留回滚能力。


## 13. Python实现约定

- AgentRequest和AgentResult以Pydantic模型作为运行时权威契约；
- JSON Schema由Pydantic导出并版本化；
- AgentDefinition保存在Git并同步入PostgreSQL注册表；
- Celery任务只传递ID和版本，不传递完整合同正文；
- 应用服务从 PostgreSQL 读取授权快照，提交准备事务后由 Runtime 在独立目录组装输入；
- 输出先通过 Pydantic 和业务规则校验；消息研判创建 MessageCandidate，后续专业 Agent 创建 DraftArtifact。
- 首次输出校验失败只允许基于同一 ContextSnapshot 和错误摘要修复一次；不使用正则或手工拼接修 JSON；
- AgentRun 每次领域状态迁移追加事件；API 返回前对 stdout/stderr 常见 Token/API Key 格式脱敏，并隐藏宿主运行目录前缀；
- 页面显示 Prompt/Runtime/AgentDefinition 版本、授权来源、租约、校验错误和 Candidate 修订，但不允许通过页面注入任意 Shell、网络或文件权限；
- `cancel` 是确定性状态门禁：取消后即使外部进程稍后返回，结果也不得创建 Candidate；`retry` 创建新的可审计尝试，不覆盖历史 Run。
