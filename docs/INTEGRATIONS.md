# 集成与运行边界

完整 API 契约见 [`docs/design/API_CONTRACTS.md`](./design/API_CONTRACTS.md)，Agent 契约见 [`docs/design/AGENT_PROTOCOL.md`](./design/AGENT_PROTOCOL.md)。

## 1. 飞书适配器

负责：

- 机器人私聊、指定群聊和 @消息接入；
- 事件幂等落库；
- 线程上下文和附件；
- 消息编辑、撤回和权限变化；
- 断线重连和补偿同步；
- 审核后消息发送和回执。

事件接收线程不得直接运行 Codex。

## 2. Codex Runtime

Codex 是唯一 AI 执行核心。所有调用统一经过 `codex-runner`，负责：

- AgentDefinition 和提示词版本；
- 单次运行上下文和文件授权；
- 工具权限；
- 超时、重试和隔离；
- JSON Schema 校验；
- 日志和审计。

系统不建设其他模型提供方适配层，但业务服务仍不得直接调用 Codex CLI。

## 3. 知识服务

知识服务提供受控混合检索：

- PostgreSQL 元数据和全文检索；
- Qdrant 向量召回；
- 文件版本、生效状态、适用主体和保密等级过滤；
- 正式制度、模板、历史事项和审核样例分域；
- 引用定位和检索审计。

Agent不能直接访问 Qdrant 或扫描整个本地目录。

## 4. 外发门禁

发送接口只接受已批准 ReviewRecord，不接受任意正文。服务端验证：

- 审核决定；
- 版本哈希；
- 接收人和会话；
- 幂等键；
- 最新事实变化；
- 飞书权限。

没有审核记录时发送服务必须拒绝。

## 5. 前端配置

以下内容不得进入 Vite 前端环境变量：

- 飞书 App Secret；
- Codex 凭证；
- 数据库连接串；
- Qdrant/Redis 密码；
- 本地知识目录的敏感配置。

## 6. Mock 与真实实现

前端演示允许 Mock；正式模式缺少后端或 Codex/飞书配置时必须显式报错，不得静默回退到 Mock。
