# Codex Agent Runtime 与统一执行协议

## 1. 目标

本协议用于约束所有 Codex Agent 的注册、输入、执行、输出、权限、审核和质量评价。新增 Agent 必须遵循本协议，不得直接在页面组件、Worker 或业务服务中拼接自由文本并调用 Codex。

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

`codex-runner` 是唯一 Codex 调用入口。

### 3.1 每次运行必须隔离

每个 AgentRun 创建独立目录：

```text
/runs/<run-id>/
├─ input/request.json
├─ input/context/
├─ input/files/
├─ prompt/system.md
├─ prompt/task.md
├─ output/result.json
├─ output/artifacts/
└─ logs/runtime.jsonl
```

运行结束后：

- 输入和输出哈希写入数据库；
- 临时明文按保留策略清理；
- 必需交付物复制到受控存储；
- 不复用长期 Codex 会话。

### 3.2 工具权限

AgentDefinition 声明可用工具，例如：

- `knowledge.search`；
- `file.read_authorized`；
- `file.extract_text`；
- `matter.read_snapshot`；
- `artifact.write_draft`。

默认禁止：

- 任意 Shell；
- 任意网络访问；
- 读取未授权目录；
- 删除或覆盖源文件；
- 发送飞书消息；
- 修改正式领域对象；
- 修改 AgentDefinition 或提示词。

确需 Shell 的内部开发 Agent 与业务法务 Agent 必须分开运行环境。

### 3.3 提示注入防护

- 消息、合同、网页和附件全部标记为不可信内容；
- 系统提示明确禁止执行文档中的指令；
- 工具服务再次校验目录、资源 ID 和 Matter 权限；
- 任何扩大权限的请求返回错误并写入审计；
- 输出中的工具调用建议不自动执行。

## 4. AgentDefinition

```ts
interface AgentDefinition {
  id: string;
  name: string;
  role: 'core' | 'professional' | 'support';
  description: string;
  version: string;
  promptVersion: string;
  inputSchemaVersion: string;
  outputSchemaVersion: string;
  supportedMatterCategories: string[];
  allowedTools: string[];
  allowedKnowledgeScopes: string[];
  allowedArtifactTypes: string[];
  timeoutSeconds: number;
  maxRetries: number;
  concurrencyLimit: number;
  riskLevel: 'low' | 'medium' | 'high';
  requiresHumanReview: boolean;
  status: 'draft' | 'trial' | 'active' | 'paused' | 'retired';
}
```

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

## 5. 统一输入协议

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
  id: string;
  sourceType: 'message' | 'file' | 'knowledge_chunk' | 'upstream_agent';
  sourceId: string;
  locator?: string;
  excerptHash: string;
  title: string;
  effectiveStatus?: 'effective' | 'expired' | 'draft' | 'unknown';
}
```

前端应可从引用跳转至授权范围内的原始位置。

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

### 8.1 顺序执行

```text
Knowledge Search → Contract Agent → Reply Agent
```

### 8.2 并行执行

```text
Contract Agent ─┐
HR Agent ───────┼→ Result Synthesizer
Dispute Agent ──┘
```

### 8.3 条件执行

```text
若合同 Agent 标记 possible_employment_relationship
→ 调用人力 Agent
```

### 8.4 冲突处理

当不同 Agent 结论冲突：

1. `AgentExecutionPlan` 进入 `paused`；
2. 结果汇总 Agent列出冲突，不作最终选择；
3. 创建 `ReviewPackage(type=agent_result)`；
4. 法务确认采用结论和原因；
5. 编排器根据确认结果继续。

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

Agent 状态：

```text
draft → trial → active → paused → retired
```

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
- Codex Runner从PostgreSQL读取授权快照并在独立目录组装输入；
- 输出先通过Pydantic校验，再创建DraftArtifact。
