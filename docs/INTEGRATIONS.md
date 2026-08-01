# 集成与运行边界

完整API契约见 [`docs/design/API_CONTRACTS.md`](./design/API_CONTRACTS.md)，Agent契约见 [`docs/design/AGENT_PROTOCOL.md`](./design/AGENT_PROTOCOL.md)。

## 飞书适配器

负责机器人私聊、指定群聊@消息、手动转发和已有事项线程；完成事件签名、幂等落库、线程上下文、附件、编辑/撤回、断线重连、补偿同步、审核后发送和回执。

事件接收线程只做校验、持久化和投递，不运行Codex。

## Codex Runtime

Codex是唯一推理和生成AI。所有调用统一经过`codex-runner`，负责AgentDefinition、提示词版本、单次工作目录、授权文件、工具权限、超时、重试、Schema和审计。

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

前端允许显式Mock模式。真实模式缺少后端、飞书或Codex配置时必须报错，不得静默回退Mock。
