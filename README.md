# 法务工作台

运行在本地 Mac 上的法务智能工作系统。系统从经过授权的飞书消息中发现工作，由受控的 Codex Agent 完成消息研判、事项归并、任务规划、专业分析、回复草拟、日报和复盘；所有发送给其他人员的内容必须经过法务审核。

> 当前已实现从消息研判、人工创建 Matter/WorkItem，到 Legal Butler、受控 Specialist DAG、PostgreSQL 法律知识检索、DraftArtifact 和 pending ReviewPackage 的 Phase 2 闭环。PDF/DOCX/TXT/Markdown 可受控解析，图片和扫描 PDF 明确显示正文不可用。真实飞书与 Real Codex E2E 均需显式开启并提供隔离凭证；默认和 CI 的 synthetic E2E 使用明确标记的 Fake Runtime，不代表真实模型通过。

## 核心闭环

```text
飞书消息
→ ContextSnapshot
→ MessageCandidate 人工确认
→ LegalMatter + WorkItem
→ 优先级/完成时间确认
→ AgentExecutionPlan
→ DraftArtifact
→ ReviewPackage
→ 法务审核
→ Communication 发送与回执
→ 跟踪、学习、日报和复盘
```

## 不可破坏的原则

1. **Codex 是唯一推理与生成 AI**，业务代码只能通过受控 Codex Runtime 调用。
2. **统一管家体验、内部职责拆分**，确定性编排器协调职责单一的核心和专业 Agent。
3. **消息、事项、行动任务、Agent 产物、审核和发送分层**，不得重新压缩为单一 Task。
4. **所有外发均需人工审核**，且审核包必须展示背景、事实、依据、处理理由、风险和拟发送内容。
5. **硬期限、状态机、权限、幂等、重试和发送由确定性服务负责**，Codex只提出建议和草稿。
6. **人工确认值不得被 Codex 静默覆盖**。
7. **PostgreSQL是唯一业务事实库**；全文检索、元数据、审计和可选向量字段均在PostgreSQL中管理。
8. **不引入外部Embedding或其他AI服务**；首期知识召回采用元数据、PostgreSQL全文检索和`pg_trgm`，pgvector仅作为可选扩展能力。
9. **学习是受控记忆和规则审批**，不是在线自动训练。

## 技术栈

### 前端

- React 18；
- TypeScript；
- Vite；
- Ant Design。
- React Router；
- TanStack Query（服务端状态、缓存、刷新和错误处理）。

### 后端

- Python 3.12；
- FastAPI + Pydantic；
- SQLAlchemy 2 + Psycopg 3；
- Alembic；
- Celery + Redis；
- PostgreSQL 18（`pg_trgm`/`unaccent`；pgvector 仅为可选扩展）；
- Docker Compose。

## 仓库结构

```text
legal-workbench/
├─ apps/
│  ├─ web/                    React 工作台
│  └─ backend/                Python 模块化单体
│     ├─ src/legal_workbench/
│     │  ├─ api/              FastAPI 路由
│     │  ├─ application/      用例与确定性编排
│     │  ├─ domain/           领域模型、状态机和策略
│     │  ├─ agents/           Codex Runtime 与 Agent 协议实现
│     │  ├─ integrations/     飞书、文件系统等适配器
│     │  ├─ infrastructure/   PostgreSQL、Redis、Celery
│     │  └─ workers/          异步任务
│     ├─ migrations/          Alembic 迁移
│     └─ tests/
├─ data/
│  ├─ knowledge/              本地知识目录挂载点
│  ├─ codex-runs/             Codex 隔离运行目录
│  ├─ operations/             脱敏运维状态与滚动日志
│  ├─ backups/                PostgreSQL 私有逻辑备份
│  └─ local-secrets/          本地私有集成 Secret
├─ infra/
│  ├─ docker/
│  └─ launchd/
├─ docs/design/               正式设计基线
├─ compose.yml
├─ Makefile
└─ package.json               前端 workspace 命令入口
```

## 快速启动

开发工具链统一为 Node `24.15.0`（见 `.node-version`）、Python `3.12` 和 uv
`0.12.3`。安装 uv 后，所有依赖都从仓库 lockfile 同步：

```bash
make setup
```

复制配置：

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
```

启动基础服务：

```bash
docker compose up -d --build
```

访问：

- Web：`http://localhost:5173`
- API文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/v1/health/live`

仅运行前端：

```bash
make web-dev
```

仅运行后端开发环境：

```bash
make setup-backend
make migrate
make backend-dev
```

## 检查

```bash
make lint
make test
npm run build
docker compose config --quiet
docker compose build api web
```

## 设计文档

从 [`docs/design/README.md`](./docs/design/README.md) 开始：

- [总体系统设计](./docs/design/SYSTEM_DESIGN.md)
- [Python 后端工程设计](./docs/design/BACKEND_ENGINEERING.md)
- [核心数据模型](./docs/design/DATA_MODEL.md)
- [统一 Agent 协议](./docs/design/AGENT_PROTOCOL.md)
- [知识检索设计](./docs/design/KNOWLEDGE_RETRIEVAL.md)
- [API 与事件契约](./docs/design/API_CONTRACTS.md)
- [Docker 部署与可靠性](./docs/design/DEPLOYMENT.md)
- [实施计划](./docs/design/IMPLEMENTATION_PLAN.md)
- [关键架构决策](./docs/design/DECISIONS.md)

## 当前实现进度

已完成：

- `ContextSnapshot`、`AgentDefinition`、`AgentRun`、`AgentRunSource`、`DraftArtifact` 和 `MessageCandidate` 正式模型；
- 两阶段 Legal Butler、五类既有 Specialist、最多四步有界 DAG、Step 直接依赖隔离、显式 rerun 与 latest-valid lineage；
- AgentRunAttempt lease/heartbeat/fencing 与 PostgreSQL recovery：过期 lease 才能通过 CAS 失效，stale Attempt、stale Step Run 或 stale Synthesis Run 均不能覆盖当前结果；
- Plan 级 `analysis_effective_date` 在 retry/recovery/rerun 中保持稳定，显式 `historical_as_of` 独立表示历史法律适用时点；
- Specialist citation 由服务端根据已授权 `sourceRef` 重建标题、类型、定位、哈希和 authority 元数据；越权引用、内部先例冒充正式法律依据和无 canonical metadata 均 fail closed；
- SQLAlchemy 映射、Repository、Unit of Work和 Alembic 可升降级迁移；
- 飞书消息 Outbox 自动投递、确定性限界快照、受控 `message_judgement` Agent 和 Pydantic/JSON Schema 输出校验；
- Codex CLI 统一 Runtime：独立运行目录、授权 JSON stdin、禁用 Shell/代码模式/网络搜索、输入输出审计、超时终止、心跳、输出大小限制和错误分类；
- Codex 启动前检查二进制、固定版本、隔离认证和运行目录；输出失败只允许使用同一快照做一次 Schema 修复重试；
- ContextSnapshot 记录 Builder/选择策略/消息与附件版本以及多维截断指标；AgentRun 状态事件和 Candidate 分析修订只追加保存；
- 附件以 `message_attachments → document_versions → document_extractions → document_segments` 保存；解析在无应用凭证的隔离子进程中执行，正文授权、片段限界和附件事实引用均可审计；
- Celery Beat 以 PostgreSQL advisory lock 扫描丢失的 queued 投递和过期 Worker 租约，重建 Outbox 或进入 `dead_letter`，Redis 清空不丢业务事实；
- 合法结果自动建立待人工确认 Candidate；无关消息不建 Candidate，任何置信度均不自动建立 Matter；
- Candidate确认创建Matter和初始WorkItem的事务闭环；
- 前端接入Candidate、Matter、WorkItem、优先级、期限、依赖和审核接口；Matter 更新审核稳定区分当前值、消息提取值、AI 建议值和法务最终值，409 冲突刷新后保留法务草稿；
- PriorityConfirmation、Deadline和WorkItemDependency模型；
- WorkItem 完整生命周期、依赖解决、领域状态机、乐观锁、审计和幂等操作页；操作后同步刷新 Matter、WorkItem 和今日工作台；
- 今日工作台使用 PostgreSQL 业务事实和实时健康快照生成八类队列；硬期限、逾期、风险、人工优先级、等待时长和创建时间确定排序，AI 优先级仅作提示；
- ReviewPackage、ReviewRecord、Communication及所有外发人工审核门禁；
- Outbox并发领取、指数退避、重试、死信和重新入队；
- Outbox Handler 显式注册，未知事件会失败、重试并最终死信；
- 飞书原始事件及消息按事件ID、消息ID幂等落库；
- 飞书官方 SDK 长连接和 Webhook 共用同一 Application Service；连接状态、编辑/撤回历史、附件下载状态和补偿结果均持久化在 PostgreSQL；
- 撤回消息资格由集中策略控制，并在 Gate、Outbox dispatch、Worker prepare/runtime start 和 Agent 成功落库时重复校验；运行中撤回保留 AgentRun 审计但不新建或更新有效 Candidate，只有用户明确提交 `override_recalled=true` 才允许 override 并独立留痕；
- 乐观锁、行锁、事务级幂等锁、审计和事务Outbox；
- HttpOnly 本地会话认证边界；只有显式 `local/development` 环境可签发本地 Session，开发 Actor Header 需显式开关；Compose 端口默认只绑定 `127.0.0.1`；
- 收件箱与 Agent 详情页展示来源、状态、版本、置信度、理由、事实/推断、期限和缺失信息。
- AI 收件箱、消息详情、Agent 运行中心和系统状态页使用真实 FastAPI 数据；支持状态/分类/时间/群聊筛选、Candidate 人工动作、运行重试/取消、补偿同步、遗留任务恢复和死信重新入队；
- SSE 推送系统健康、消息、AgentRun、Candidate 和 Outbox 变化，断开后按指数退避重连并回退到有限频率轮询；
- AI 质量评估使用 11 类合成非敏感版本化 Fixture，持久化 EvaluationCase/Run/Result，并确定性汇总相关性、分类、期限、角色、事实引用、推断误报、缺失信息、Schema、耗时、失败和重试指标；Fake 只验证评估管线，只有显式真实 Runner 结果才代表模型质量；
- `/setup` 九步向导从 PostgreSQL 和实时探针恢复基础服务、飞书凭证掩码/授权范围、Codex CLI/版本/认证/冒烟状态；本地 SecretProvider 使用 `0700/0600` 和原子替换，Codex 验证与冒烟只排队给隔离 Worker；
- `/settings/feishu-scopes` 使用 PostgreSQL 真实范围数据；未知群默认 `unapproved/disabled`，允许、排除、暂停、恢复和延后补偿都使用 Actor、版本锁、幂等键与审计；
- `scripts/legal_workbench_ops.py` 提供安全启动/停止、睡眠唤醒自检、PostgreSQL 每日自定义格式备份、Codex 运行目录保留、脱敏诊断包和滚动运维日志；系统状态页展示磁盘、附件配额、最近备份、最近唤醒和 PostgreSQL 待恢复任务；
- Agent stdout/stderr 常见凭证格式脱敏，运行目录只返回受控逻辑路径；所有新增写操作继续要求后端 Actor、Idempotency-Key、Correlation ID 和审计。
- `domain/entities.py` 与 `application/ports` 已按 bounded context 拆分，旧 public import 由兼容 facade/package re-export；仍是同一 modular monolith，没有新增网络服务边界；
- Personal Sync 结果明确区分 `claimedAt`、`windowStart`、`windowEnd`、`completedAt`；前端 CI 使用 `npm ci` 并依次执行 typecheck、Vitest 和 build。

部分实现：

- 飞书开关关闭时真实入口 fail closed；长连接缺少 App ID/Secret、Webhook 缺少 Verification Token 时拒绝启动。当前 Mac 已使用 Workbench OAuth Token 实测 OAuth refresh、群历史、群发现和文档搜索；Identity/Messages/Chat discovery/Documents Scope 投影均为 ready。当前库没有可复用 P2P、Thread 或文档 Markdown fixture，相关结果保持 `partial/unsupported`，未伪造通过。Webhook 加密载荷仍明确拒绝；
- 容器 Worker 以专用 UID、最小环境变量和无知识目录挂载运行 Codex；主机模式仍依赖 Codex 自身只读沙箱，不声称是完整 OS 级隔离。
- `CODEX_CLI_VERSION` 是唯一 Codex 部署版本来源。Synthetic Fake Runtime E2E 与 Real Codex E2E 使用不同测试和显式门禁；前者只证明确定性编排、持久化和审核边界，不能替代真实模型证据。
- `infra/launchd` 模板已在当前 Mac 实际安装为 Supervisor 与每日备份 Agent；Supervisor 运行退出码为 0，真实 Scheduled Personal Sync、PostgreSQL custom backup 和隔离恢复均已通过。物理睡眠因 `pmset` 计划唤醒要求 root 且无非交互 sudo 而未执行，详见 `artifacts/mac-operations/final-acceptance-20260809.json`。
- 当前 Registry 最新 `react-router-dom@7.18.2` 仍命中 RSC Action CSRF 公告 `GHSA-qwww-vcr4-c8h2`；本项目不启用 RSC/Server Actions，但在上游发布可安装修复版本前，`npm audit` 仍会报告 2 个 high，详见 `QA_REPORT.md`。

## 当前开发顺序

1. 在具备 `pmset` root 权限或有人现场唤醒时补做真实 Mac 睡眠/唤醒，并发送一条新的非敏感飞书消息验证唤醒后新增入库；
2. 在专用 Runner 隔离认证可用时显式执行 Real Codex E2E 与真实评估；不得读取真实敏感法务材料；
3. 真实飞书测试消息和官方长连接验收按用户要求后置，恢复时单独执行且人工确认个人未读状态。
