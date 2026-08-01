# Codex 项目交接说明

更新日期：2026-08-01

## 当前可用闭环

```text
FeishuEvent
→ FeishuMessage
→ FeishuMessageReceived Outbox
→ Celery feishu.process_message
→ ContextSnapshot
→ AgentDefinition(message_judgement) + AgentRun + AgentRunSource
→ CodexCliRuntime
→ Pydantic/业务校验
→ MessageCandidate(pending_confirmation) 或 ignored
```

Runtime 前后使用独立短事务，不在数据库事务内等待 Codex。任何置信度都不会自动创建 `LegalMatter`。

## 状态矩阵

| 能力 | 状态 |
|---|---|
| React 收件箱/Candidate/Matter/WorkItem/审核页 | 已实现，闭环相关数据已连接 FastAPI |
| Python FastAPI + SQLAlchemy + PostgreSQL | 已实现 |
| Outbox 领取、重试、死信、显式 Handler 注册 | 已实现 |
| 飞书长连接/Webhook、原始事件/消息幂等落库 | 已实现；真实凭证未联调 |
| ContextSnapshot/AgentDefinition/AgentRun/Source/DraftArtifact | 已实现 |
| `message_judgement` + `CodexCliRuntime` | 已实现，真实请求需显式配置 |
| Codex 版本/隔离认证健康检查 | 已实现；当前宿主为版本不匹配且隔离认证缺失 |
| AgentRun 状态历史、租约与 PostgreSQL 恢复 | 已实现，Celery Beat 定时扫描 |
| Candidate 分析修订历史 | 已实现，旧修订不覆盖 |
| HttpOnly 本地会话与 Actor 来源审计 | 已实现；生产会话签发器尚未实现 |
| 飞书连接状态、消息版本、附件元数据/受控下载 | 已实现；下载不授权给 Codex |
| 飞书补偿同步 | 已实现配置群聊时间窗方案；未配置群聊时明确为部分恢复 |
| 飞书加密 Webhook | 尚未实现；加密载荷明确拒绝 |
| 知识解析/检索/专业 Agent/外发 | 本轮未实现 |

## 重要代码入口

- `application/context_snapshots.py`：确定性授权上下文选择与快照去重；
- `application/message_analysis.py`：准备、Runtime 外调、结果落库三段编排；
- `agents/message_judgement.py`：严格输出 Schema 和 Candidate 决策；
- `agents/codex_cli.py`：Codex 工作目录、子进程、超时和审计文件；
- `workers/tasks.py`：Celery 自动重试；
- `application/analysis_recovery.py`：Redis/Worker 丢失后的 PostgreSQL 恢复扫描；
- `agents/codex_health.py`：真实 CLI 版本、隔离认证和运行目录检查；
- `infrastructure/outbox.py`：显式事件 Handler 注册。
- `integrations/feishu_sdk.py`：官方 SDK 原始事件、长连接和优雅退出；
- `application/feishu_operations.py`：持久化连接状态、补偿和受控附件下载。

## 配置门禁

- `LEGAL_WORKBENCH_ENABLE_REAL_CODEX=false` 时禁止真实 Codex，但仍保存可审计失败运行；
- `LEGAL_WORKBENCH_ENABLE_REAL_FEISHU=false` 时真实入口关闭；长连接模式必须配置 App ID/Secret，Webhook 模式必须配置 Verification Token；
- 只有 `local/development` 可签发本地 Session 和按开关使用开发 Actor Header；所有非本地环境必须使用至少 32 字符的非默认 Session Secret；Compose 端口默认仅绑定 `127.0.0.1`；
- Runtime 审计目录不得写入飞书 Token、数据库 URL、Redis URL 或 Codex 凭证。

Runtime 将唯一授权 ContextSnapshot 作为不可信 JSON 直接送入 stdin，同时禁用 Shell、统一执行、代码模式、多 Agent、Apply Patch、网络搜索、MCP Apps、浏览器、Computer Use、插件和技能发现。Worker 单并发运行，并在子进程结束后收回审计目录所有权。该限制显著缩小权限面，但仍不宣称宿主机模式达到可证明的 OS 级隔离。

当前 Compose 没有做容器零出网：模型传输需要访问 Codex/OpenAI 服务。生产化时应使用目的地址 allowlist/代理；不要把“Agent 网络工具关闭”描述为“进程完全无网络”。

人工重新分析会创建新 AgentRun，并向 `candidate_revisions` 追加完整分析版本：待确认 Candidate 随最新合法结果更新，最新结果无关时旧 Candidate 作废；已人工确认/关联的 Candidate 不被覆盖。

## 下一步

1. 在专用容器内使用非生产凭证执行真实 Codex 冒烟和故障注入；
2. 使用测试应用完成真实飞书长连接/时间窗补偿验证，并评审加密 Webhook；
3. 实现生产会话签发与授权策略；
4. 再开始知识检索与合同 Agent，不在当前消息研判边界内扩展。
