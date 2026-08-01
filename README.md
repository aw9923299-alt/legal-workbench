# 法务工作台

运行在本地 Mac 上的法务智能工作系统。系统从经过授权的飞书消息中发现工作，由受控的 Codex Agent 完成消息研判、事项归并、任务规划、专业分析、回复草拟、日报和复盘；所有发送给其他人员的内容必须经过法务审核。

> 当前已实现 `FeishuEvent → FeishuMessage → Outbox → ContextSnapshot → AgentRun → MessageCandidate` 消息研判闭环，以及官方 SDK 长连接/Webhook 双入口、断线重连、消息版本与附件元数据、时间窗补偿接口。真实飞书与真实 Codex 均需显式开启并提供可用凭证；知识解析和专业 Agent 尚未实现。

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
│  └─ codex-runs/             Codex 隔离运行目录
├─ infra/
│  ├─ docker/
│  └─ launchd/
├─ docs/design/               正式设计基线
├─ compose.yml
├─ Makefile
└─ package.json               前端 workspace 命令入口
```

## 快速启动

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
npm install
npm run dev
```

仅运行后端开发环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/python -m pip install -e 'apps/backend[dev]'
alembic -c apps/backend/alembic.ini upgrade head
npm run backend:dev
```

## 检查

```bash
npm run typecheck
npm run build
.venv/bin/python -m ruff check apps/backend/src apps/backend/tests
.venv/bin/python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
.venv/bin/python -m pytest apps/backend/tests
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
- SQLAlchemy 映射、Repository、Unit of Work和 Alembic 可升降级迁移；
- 飞书消息 Outbox 自动投递、确定性限界快照、受控 `message_judgement` Agent 和 Pydantic/JSON Schema 输出校验；
- Codex CLI 统一 Runtime：独立运行目录、授权 JSON stdin、禁用 Shell/代码模式/网络搜索、输入输出审计、超时终止、心跳、输出大小限制和错误分类；
- Codex 启动前检查二进制、固定版本、隔离认证和运行目录；输出失败只允许使用同一快照做一次 Schema 修复重试；
- ContextSnapshot 记录 Builder/选择策略/消息与附件版本以及多维截断指标；AgentRun 状态事件和 Candidate 分析修订只追加保存；
- Celery Beat 以 PostgreSQL advisory lock 扫描丢失的 queued 投递和过期 Worker 租约，重建 Outbox 或进入 `dead_letter`，Redis 清空不丢业务事实；
- 合法结果自动建立待人工确认 Candidate；无关消息不建 Candidate，任何置信度均不自动建立 Matter；
- Candidate确认创建Matter和初始WorkItem的事务闭环；
- 前端接入Candidate、Matter、WorkItem、优先级、期限、依赖和审核接口；
- PriorityConfirmation、Deadline和WorkItemDependency模型；
- ReviewPackage、ReviewRecord、Communication及所有外发人工审核门禁；
- Outbox并发领取、指数退避、重试、死信和重新入队；
- Outbox Handler 显式注册，未知事件会失败、重试并最终死信；
- 飞书原始事件及消息按事件ID、消息ID幂等落库；
- 飞书官方 SDK 长连接和 Webhook 共用同一 Application Service；连接状态、编辑/撤回历史、附件下载状态和补偿结果均持久化在 PostgreSQL；
- 乐观锁、行锁、事务级幂等锁、审计和事务Outbox；
- HttpOnly 本地会话认证边界；只有显式 `local/development` 环境可签发本地 Session，开发 Actor Header 需显式开关；Compose 端口默认只绑定 `127.0.0.1`；
- 收件箱与 Agent 详情页展示来源、状态、版本、置信度、理由、事实/推断、期限和缺失信息。

部分实现：

- 飞书开关关闭时真实入口 fail closed；长连接缺少 App ID/Secret、Webhook 缺少 Verification Token 时拒绝启动。当前环境未提供真实凭证，长连接与远端时间窗补偿仅通过 Fake/自动化测试验证；Webhook 加密载荷仍明确拒绝；
- 容器 Worker 以专用 UID、最小环境变量和无知识目录挂载运行 Codex；主机模式仍依赖 Codex 自身只读沙箱，不声称是完整 OS 级隔离。
- 当前宿主 CLI 为 `0.146.0-alpha.9.2`，与容器固定版本 `0.145.0-alpha.9` 不匹配，且隔离 Worker 未配置 API Key；因此真实 Codex 推理未执行，11 类消息仅通过 Fake Runtime + 真实 PostgreSQL 验证。

## 当前开发顺序

1. 在测试飞书应用上验证长连接、撤回和按群聊时间窗补偿，并评审加密 Webhook；
2. 在容器内使用真实凭证执行 Codex 安全冒烟与故障注入测试；
3. 建立知识文件解析、全文检索和可追溯引用；
4. 跑通合同审核端到端专业Agent闭环；
5. 完善Communication发送回执、失败补偿和人工重发；
6. 建立学习、评测、日报和事项复盘；
7. 依次接入文案、人力、纠纷和知产Agent；
8. 完善权限、备份、监控和Mac常驻运行。
