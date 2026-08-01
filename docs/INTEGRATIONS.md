# 集成与运行边界

完整API契约见 [`docs/design/API_CONTRACTS.md`](./design/API_CONTRACTS.md)，Agent契约见 [`docs/design/AGENT_PROTOCOL.md`](./design/AGENT_PROTOCOL.md)。

## 飞书适配器

负责机器人私聊、指定群聊@消息、手动转发和已有事项线程。当前已实现官方 SDK 长连接与 Verification Token Webhook 双模式，二者统一调用 `IngestFeishuEventHandler`，完成原始事件/消息事务幂等、线程关系、编辑/撤回版本、附件元数据与受控下载、连接状态和时间窗补偿审计。

事件接收线程只做校验、持久化和投递，不运行Codex。

长连接默认使用 `FEISHU_EVENT_SOURCE=long_connection`。SDK 心跳和内部重连之外，连接器还使用 `1/2/4/8/16/30` 秒有上限退避；状态写入 `integration_connections`。`ENABLE_REAL_FEISHU=true` 时缺凭证直接失败，不会退回 Fake。

补偿同步只查询 `FEISHU_RECONCILE_CHAT_IDS` 明确列出的群聊和可配置时间窗，数据库通过事件/消息唯一约束吸收重复。飞书接口不是全租户游标日志；未配置群聊或权限不足时状态为 `partial/local_only`，不得承诺绝不漏消息。

附件只下载到 `FEISHU_ATTACHMENT_ROOT/<tenant>/<message UUID>`，校验最大字节数、计算 SHA-256 并登记路径。`authorized_for_analysis=false` 为默认值，本轮不做 OCR、正文解析或向量化。

## Codex Runtime

Codex是唯一推理和生成AI。所有业务调用统一经过`CodexCliRuntime`，由 Celery Worker 调用，负责AgentDefinition、提示词版本、单次工作目录、授权来源、工具权限、超时、重试、Schema和审计。当前仅`message_judgement`已实现。

业务服务不得直接执行Codex CLI。

## 知识服务

知识服务基于PostgreSQL提供：

- 元数据和权限过滤；
- 正式制度、模板、历史事项和审核样例分域；
- 全文检索和`pg_trgm`；
- 可选pgvector字段；
- 文件版本、生效状态、适用主体和保密等级；
- 引用定位和检索审计。

不使用Qdrant或外部Embedding服务。Agent不能直接扫描整个本地目录或绕过知识服务查询数据库。

## 外发门禁

发送接口只接受已批准的Artifact引用，不接受任意正文。服务端验证审核决定、版本哈希、接收人、会话、幂等键、事项当前状态和飞书权限。

## 配置边界

前端环境变量只能包含公开配置。以下内容必须由Python后端持有：

- 飞书App Secret和验证信息；
- Codex凭证和命令配置；
- PostgreSQL/Redis连接信息；
- 本地知识目录和加密配置。

## Mock与真实实现

前端的候选、事项、任务和消息研判路径访问 FastAPI；与当前闭环无关的页面仍可包含演示数据。真实模式缺少后端、飞书或Codex配置时必须报错，不得静默回退演示数据。
