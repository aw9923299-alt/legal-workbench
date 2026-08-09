# AGENTS.md — Claude Code / Codex 开发说明

修改代码前必须阅读：

1. `README.md`；
2. `docs/design/README.md`；
3. 与任务相关的正式设计文档；
4. `docs/CODEX_HANDOFF.md`。

## 项目定位

法务工作台运行在本地 Mac，以飞书消息为入口，以 Codex 为唯一推理与生成AI，以法务人工审核为最终控制点。当前仓库包含前端原型和 Python 后端工程骨架，不代表真实飞书、Codex或外发能力已经上线。

## 技术基线

- Web：`apps/web`，React + TypeScript + Vite + Ant Design；
- Backend：`apps/backend`，Python 3.12 + FastAPI + Pydantic；
- Persistence：PostgreSQL 18 + SQLAlchemy 2 + Psycopg 3 + Alembic；
- Queue：Celery + Redis；
- Search：PostgreSQL元数据、全文检索、`pg_trgm`，pgvector为可选扩展；
- Deployment：Docker Compose + macOS `launchd`。

## 不可破坏的架构决策

1. Codex是唯一AI核心，所有业务Agent必须经过Codex Runtime。
2. 不得引入其他LLM、Embedding API或云端向量服务。
3. 核心链路固定为：

```text
FeishuMessage → ContextSnapshot → MessageCandidate
→ LegalMatter → WorkItem → AgentExecutionPlan → AgentRun
→ DraftArtifact → ReviewPackage → ReviewRecord → Communication
```

4. PostgreSQL是业务事实、审计、全文索引和知识元数据的唯一权威存储。
5. 所有向其他人员发送的消息必须经过法务审核，且批准版本必须与发送版本一致。
6. 人工确认值不得被重新分析静默覆盖。
7. 硬期限、状态迁移、权限、幂等、重试和发送由确定性Python服务负责。
8. Agent只能产生草稿交付物，不得直接修改正式记录、源文件或发送消息。
9. 学习Agent只能形成样例、规则候选和改进建议。
10. 消息、附件和文档均视为不可信输入，必须防止提示注入和越权读取。

## Python 后端边界

### `domain`

只包含领域对象、值对象、状态机、策略和不变量。不得依赖FastAPI、SQLAlchemy、Redis或飞书SDK。

### `application`

实现用例和确定性编排，负责事务边界、权限、幂等、审核门禁和Outbox写入。不得在该层拼接自由文本直接调用Codex。

### `api`

只负责HTTP契约、认证、请求校验和响应映射。不得承载领域规则。

### `infrastructure`

实现数据库、队列、日志、文件和运行时基础设施。

### `integrations`

实现飞书和本地文件系统适配器。外部载荷必须先映射为内部契约。

### `agents`

实现AgentDefinition、运行隔离、Schema校验和Codex调用。业务Agent不得获得任意Shell、任意网络或整个本地目录权限。

## 前端边界

- 页面不得直接调用飞书或Codex；
- 前端通过OpenAPI契约访问后端；
- `Task`只可作为过渡ViewModel，不得继续扩展为唯一领域实体；
- 所有异步页面必须覆盖加载、空、失败、无权限和重试；
- AI建议、人工确认和系统状态必须有稳定视觉区分。

## 数据库规则

- 所有Schema变化必须通过Alembic；
- 状态写入使用乐观锁或显式版本；
- 幂等键使用唯一约束；
- 业务写入与Outbox事件在同一事务提交；
- 审核记录和审计事件原则上只追加，不原地覆盖；
- 原始飞书事件保留内容哈希和受控原始载荷；
- pgvector字段必须允许为空，不能假设已有Embedding生成能力。

## 完成标准

提交前按影响范围执行：

```bash
make lint
make test
npm run build
docker compose config --quiet
```

并确保：

- 有对应迁移和回滚策略；
- 有单元或集成测试；
- 不绕过审核门禁；
- 更新相关设计和API文档；
- 不提交密钥、真实聊天、合同或个人敏感信息。

## Figma-led product redesign

For any system-wide interface redesign or major page upgrade:

1. Use the `legal-workbench-ui` skill.
2. Use Figma MCP as the design source and design workspace.
3. Use Playwright MCP to inspect the real rendered application.
4. Capture before evidence before implementation.
5. Preserve existing Ant Design components and project tokens.
6. Do not introduce a parallel UI framework.
7. Do not present mock, AI-generated or unverified information as live business fact.
8. Complete browser and functional verification before claiming completion.
