# 集成与运行边界

完整API契约见 [`docs/design/API_CONTRACTS.md`](./design/API_CONTRACTS.md)，Agent契约见 [`docs/design/AGENT_PROTOCOL.md`](./design/AGENT_PROTOCOL.md)。

## 飞书适配器

负责机器人私聊、指定群聊@消息、手动转发和已有事项线程。当前已实现官方 SDK 长连接与 Verification Token Webhook 双模式，二者统一调用 `IngestFeishuEventHandler`，完成原始事件/消息事务幂等、线程关系、编辑/撤回版本、附件元数据与受控下载、连接状态和时间窗补偿审计。

事件接收线程只做校验、持久化和投递，不运行Codex。

长连接默认使用 `FEISHU_EVENT_SOURCE=long_connection`。SDK 心跳和内部重连之外，连接器还使用 `1/2/4/8/16/30` 秒有上限退避；状态写入 `integration_connections`。`ENABLE_REAL_FEISHU=true` 时缺凭证直接失败，不会退回 Fake。

补偿同步只查询 `FEISHU_RECONCILE_CHAT_IDS` 明确列出的群聊和可配置时间窗，数据库通过事件/消息唯一约束吸收重复。飞书接口不是全租户游标日志；未配置群聊或权限不足时状态为 `partial/local_only`，不得承诺绝不漏消息。

附件只下载到 `FEISHU_ATTACHMENT_ROOT/<tenant>/<message UUID>`，校验单文件上限和 PostgreSQL 协调的总磁盘配额，使用清理后的文件名、私有权限和 SHA-256 登记。正文提取在限时、限输出、无数据库/Redis/飞书/Codex凭证的子进程中完成；当前只支持文本型 PDF、DOCX、UTF-8 TXT 和 Markdown。图片、扫描 PDF、宏文档和其他格式只保存元数据并显示“正文暂不可解析”，不做 OCR、不执行宏或 PDF 脚本。

`authorized_for_analysis=false` 仍是默认值。只有人工授权且解析成功的片段能进入后续 ContextSnapshot；片段受数量、单段字符和总字符三重上限约束。API 和前端不返回附件本地路径，Codex 只接收被选中的不可信 JSON 片段，不能读取附件目录。

## Codex Runtime

Codex是唯一推理和生成AI。所有业务调用统一经过`CodexCliRuntime`，由 Celery Worker 调用，负责AgentDefinition、提示词版本、单次工作目录、授权来源、工具权限、超时、重试、Schema和审计。当前仅`message_judgement@2.2.0`已实现。启动前检查固定 CLI 版本、显式隔离认证目录和运行目录；正文始终作为不可信业务证据，失败输出最多使用同一 ContextSnapshot 修复一次。每条确认事实只能引用授权消息或一个精确附件片段，附件引用包含附件 ID、文件名、页码、段落号和正文哈希。

AgentRun、状态事件、Candidate 修订、租约和失败码全部存 PostgreSQL。Celery Beat 定期扫描丢失队列投递与过期租约并重建 Outbox；Redis 不保存唯一业务事实。

工作台通过 `/api/v1/events/stream` 接收系统健康、消息、AgentRun、Candidate 和 Outbox 变化。SSE 只用于刷新提示；断线时由 TanStack Query 有限轮询 PostgreSQL 查询接口，因此 SSE 或 Redis 丢失不会丢业务状态。

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

前端的收件箱、消息详情、Candidate 人工动作、Agent 运行中心和系统状态访问 FastAPI，不使用演示状态；与当前闭环无关的旧页面仍可能包含演示数据。真实模式缺少后端、飞书或Codex配置时必须报错，不得静默回退演示数据。
