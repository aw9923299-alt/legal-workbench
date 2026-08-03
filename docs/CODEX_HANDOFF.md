# Codex 项目交接说明

更新日期：2026-08-03

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
→ 法务人工创建/关联 Matter，或提交 MatterUpdateProposal
→ 法务逐字段批准/部分批准/拒绝
→ LegalMatter + WorkItem + Deadline
```

Runtime 前后使用独立短事务，不在数据库事务内等待 Codex。任何置信度都不会自动创建 `LegalMatter`。

## 状态矩阵

| 能力 | 状态 |
|---|---|
| React 收件箱/消息详情/Agent运行中心/系统状态/Candidate动作 | 已实现，核心闭环数据均连接 FastAPI |
| SSE + 断线轮询回退 | 已实现，五类运行事件触发 Query 刷新 |
| Python FastAPI + SQLAlchemy + PostgreSQL | 已实现 |
| Outbox 领取、重试、死信、显式 Handler 注册 | 已实现；人工重入队带 Actor/幂等/审计 |
| 飞书长连接/Webhook、原始事件/消息幂等落库 | 已实现；真实凭证未联调 |
| ContextSnapshot/AgentDefinition/AgentRun/Source/DraftArtifact | 已实现 |
| `message_judgement` + `CodexCliRuntime` | 已实现，真实请求需显式配置 |
| Codex 版本/隔离认证健康检查 | 已实现；当前宿主为版本不匹配且隔离认证缺失 |
| AgentRun 状态历史、租约与 PostgreSQL 恢复 | 已实现，Celery Beat 定时扫描 |
| Candidate 分析修订历史 | 已实现，旧修订不覆盖 |
| MatterUpdateProposal 人工审核 | 已实现；Proposal/Matter 双版本锁、逐字段最终值、WorkItem/Deadline 同事务落库；409 刷新保留法务草稿 |
| WorkItem 全生命周期 | 已实现；13 类领域动作、WorkItem/Dependency 双版本、审计/Outbox/幂等同事务；页面按状态展示合法操作并刷新相关队列 |
| 今日工作台 | 已实现；八类 PostgreSQL/健康队列、确定性排序、真实链接和完整查询状态，运行时 Mock 已删除 |
| PDF/DOCX/TXT/Markdown 附件正文 | 已实现受控解析与引用；图片/扫描 PDF 无 OCR，明确正文不可用 |
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
- `api/routes/messages.py`：收件箱和消息详情查询；
- `api/routes/events.py`：SSE 健康及业务变化事件；
- `infrastructure/system_status.py`：真实依赖健康和 PostgreSQL 运行指标；
- `apps/web/src/pages/{InboxPage,MessageDetailPage,AgentCenterPage,AgentRunDetailPage,SystemStatusPage}.tsx`：核心操作页面；
- `integrations/feishu_sdk.py`：官方 SDK 原始事件、长连接和优雅退出；
- `application/feishu_operations.py`：持久化连接状态、补偿和受控附件下载。
- `application/matter_updates.py`：Candidate 更新建议、双版本审核和人工最终值事务落库；
- `application/work_item_lifecycle.py`：WorkItem 状态、字段和依赖解决的统一领域编排；
- `api/routes/matter_update_proposals.py`：更新建议读取与审核 API；
- `apps/web/src/pages/MatterUpdateProposalPage.tsx`：当前值/消息提取值/AI建议值/法务最终值四列审核页。
- `apps/web/src/components/{MatterUpdateComparison,WorkItemActions}.tsx`：逐字段人工决定与按状态派生的 WorkItem 操作控件。
- `application/dashboard.py`：八类队列契约和确定性排序；
- `infrastructure/dashboard.py`：PostgreSQL 事实与健康状态投影；
- `apps/web/src/pages/DashboardPage.tsx`：真实今日工作台、异常提示和对象跳转。

## 配置门禁

- `LEGAL_WORKBENCH_ENABLE_REAL_CODEX=false` 时禁止真实 Codex，但仍保存可审计失败运行；
- `LEGAL_WORKBENCH_ENABLE_REAL_FEISHU=false` 时真实入口关闭；长连接模式必须配置 App ID/Secret，Webhook 模式必须配置 Verification Token；
- 只有 `local/development` 可签发本地 Session 和按开关使用开发 Actor Header；所有非本地环境必须使用至少 32 字符的非默认 Session Secret；Compose 端口默认仅绑定 `127.0.0.1`；
- Runtime 审计目录不得写入飞书 Token、数据库 URL、Redis URL 或 Codex 凭证。

Runtime 将唯一授权 ContextSnapshot 作为不可信 JSON 直接送入 stdin，同时禁用 Shell、统一执行、代码模式、多 Agent、Apply Patch、网络搜索、MCP Apps、浏览器、Computer Use、插件和技能发现。Worker 单并发运行，并在子进程结束后收回审计目录所有权。该限制显著缩小权限面，但仍不宣称宿主机模式达到可证明的 OS 级隔离。

当前 Compose 没有做容器零出网：模型传输需要访问 Codex/OpenAI 服务。生产化时应使用目的地址 allowlist/代理；不要把“Agent 网络工具关闭”描述为“进程完全无网络”。

人工重新分析会创建新 AgentRun，并向 `candidate_revisions` 追加完整分析版本：待确认 Candidate 随最新合法结果更新，最新结果无关时旧 Candidate 作废；已人工确认/关联的 Candidate 不被覆盖。

前端一次业务动作会把请求 Payload 与 Idempotency-Key/Correlation ID 绑定在当前 Tab；网络超时保留同一键，收到明确成功或确定性 4xx 后清除。SSE 断开时页面明确显示降级并使用 15 秒轮询，不把 Redis 中的临时心跳当作业务事实。

## 下一步

1. 完成 AI 质量评测和反馈记录；
2. 完成 `/setup`、飞书群聊授权范围和本地 Mac 运维恢复；
3. 真实飞书测试消息与官方长连接验收已按用户要求后置，后续有测试凭证时再执行，不得写成已通过；
4. 在专用容器内使用非生产凭证执行真实 Codex 冒烟和故障注入。
