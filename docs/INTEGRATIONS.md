# 外部集成与适配器契约

## 1. 总体原则

外部系统通过适配器接入。领域层只使用内部模型，不直接依赖飞书、具体模型厂商或某个 Agent 平台的返回结构。

## 2. 飞书适配器

建议接口能力：

```ts
interface FeishuAdapter {
  getAuthorizationState(): Promise<AuthorizationState>;
  listAuthorizedChats(cursor?: string): Promise<Page<ChatRef>>;
  syncMessages(input: SyncCursor): Promise<SyncBatch>;
  getThreadContext(messageId: string, window: number): Promise<MessageRef[]>;
  getFileMetadata(fileToken: string): Promise<FileRef>;
  downloadAuthorizedFile(fileToken: string): Promise<BinaryReference>;
  resolveUsers(userIds: string[]): Promise<Person[]>;
  pauseSync(scope?: DataScope): Promise<void>;
  revokeScope(scope: DataScope): Promise<void>;
}
```

必须处理：事件重复投递、消息编辑/撤回、机器人不可见消息、文件权限失效、用户离职、会话名称变化和 API 限流。

## 3. AI 识别服务

建议输出严格结构化结果：

```ts
interface LegalMessageAnalysis {
  decision:
    | 'explicit_task'
    | 'possible_task'
    | 'for_information'
    | 'waiting_for_others'
    | 'not_legal'
    | 'insufficient_information';
  title?: string;
  matterType?: string;
  requester?: EntityCandidate;
  owner?: EntityCandidate;
  collaborators: EntityCandidate[];
  deadline?: DateCandidate;
  priority: Priority;
  legalRisk: LegalRisk;
  businessImpact: BusinessImpact;
  requiredMaterials: MaterialCandidate[];
  riskReasons: EvidenceBackedReason[];
  evidenceRefs: string[];
  confidence: number;
  modelVersion: string;
}
```

服务端必须验证结构，不允许页面直接信任模型文本。原始提示词、模型版本和结果哈希应进入审计记录。

## 4. Agent 网关

```ts
interface AgentGateway {
  listDefinitions(): Promise<AgentDefinition[]>;
  recommend(taskId: string): Promise<AgentRecommendation[]>;
  requestRun(input: AgentRunRequest): Promise<AgentRun>;
  approveRun(runId: string, decision: ApprovalDecision): Promise<AgentRun>;
  cancelRun(runId: string): Promise<AgentRun>;
  retryRun(runId: string): Promise<AgentRun>;
  getRun(runId: string): Promise<AgentRun>;
}
```

Agent 请求至少包含任务快照版本、允许读取的数据引用、允许回写的位置和幂等键。Agent 不能自行扩大读取范围。

## 5. 前端配置

`.env.example` 只保存公开运行配置。以下内容不得进入 Vite 前端环境变量：

- 飞书 App Secret；
- 模型 API Key；
- 数据库连接串；
- 对象存储 Secret；
- Agent 平台管理令牌。

## 6. Mock 与真实实现切换

建议通过依赖注入或适配器工厂切换：

```ts
const services = createServices({
  mode: import.meta.env.VITE_APP_MODE,
});
```

测试和本地演示默认使用 Mock。生产构建若缺少真实后端配置，应启动失败或显示明确的配置错误，不应静默回退到 Mock。
