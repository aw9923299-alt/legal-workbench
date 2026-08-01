# QA Report

更新日期：2026-08-01

## 检查范围

- 1440px 与 1920px 桌面端设计目标；
- 1320px 与 1100px 响应式退化；
- 长任务标题、下一步行动和表格横向溢出；
- AI 建议、AI 提取、人工确认和系统日志的视觉区分；
- 空模块、失败 Agent 记录、待审批和无权限状态；
- 飞书授权范围、暂停同步和敏感群排除提示；
- 任务状态、等待对象、下一步行动、期限和升级语义；
- 基础深色模式；
- Codex 交接文档、架构边界和路线图完整性。

## 已完成自动检查

- `package.json` 与 TypeScript 配置 JSON 解析通过；
- 16 个 `.ts` / `.tsx` 文件使用 TypeScript 5.8.3 完成语法转译检查；
- 结果：**未发现 TypeScript 语法错误**；
- `preview.html` 为自包含静态预览，不依赖 npm 包；
- 项目名称已统一为“法务工作台 / Legal Workbench”；
- 已补充 `.gitignore`，排除密钥、依赖、构建产物和本地文件。

## 环境限制

当前执行环境无法访问公网 npm Registry，内部 npm 代理也对 React、Ant Design 等公开包返回 HTTP 404，因此无法完成 `npm install` 和最终 Vite 生产构建。

这意味着：

- 已完成源码语法级检查；
- 尚未在本环境完成依赖解析、类型声明解析和真实打包；
- 代码提交后应由正常网络环境或 GitHub Actions 执行 `npm install`、`npm run typecheck` 和 `npm run build`。

## 已进行的自动修正

1. 将首页从统计看板优先调整为下一步工作队列优先；
2. 增加当前责任人、等待对象、等待时长和下一步行动；
3. 增加 AI 证据、置信度和人工确认标识；
4. 明确低置信度消息不得直接成为正式任务；
5. 增加 Agent 版本、权限、审批、成本、重试和回写边界；
6. 增加飞书授权范围和敏感群排除；
7. 增加响应式布局和长内容处理；
8. 增加基础深色模式；
9. 补充 `AGENTS.md` 和 Codex 交接文档；
10. 补充架构、领域模型、适配器、路线图和测试规范；
11. 明确当前功能为 Mock 前端原型，避免误认为已接入真实飞书或 AI 服务。

## 提交后建议验证

```bash
npm install
npm run typecheck
npm run build
npm run dev
```

人工检查：

- 今日工作台与任务详情在 1440px、1920px 下的布局；
- AI 收件箱长消息与批量操作；
- 深色模式状态标签对比度；
- 页面加载、空、错误、无权限和重试状态；
- Mock 状态是否有明确演示标识。

## 2026-08-01 设计文档落地检查

本次新增正式设计基线 `docs/design/`，并同步更新 README、AGENTS、架构、领域模型、集成、路线图、测试和交接文档。

已执行：

- `git diff --check`：通过；
- Markdown 相对链接检查：通过；
- 关键冲突词检查：未发现旧的多模型、万能管家或单一 Task 设计残留；
- `npm run typecheck`：未完成，原因是当前运行环境没有安装 React、Ant Design 等 npm 依赖，错误均为模块/类型声明缺失；本次未修改前端源码。

设计文档覆盖：

- 管家 Agent 职责拆分；
- 消息、事项、行动任务、Agent 产物、审核和发送模型；
- 优先级人工确认；
- Codex Runtime 和统一 Agent 协议；
- Agent 质量评价；
- 混合知识检索和受控学习；
- Mac + Docker Compose 可靠性；
- API、领域事件、异常和实施计划。

## 2026-08-01 Python/PostgreSQL 工程基线更新

本次完成：

- 前端迁移至`apps/web`并保留根目录npm workspace命令；
- 新增`apps/backend` Python 3.12模块化单体；
- 新增FastAPI live/ready健康检查；
- 新增SQLAlchemy、Psycopg、Alembic和Celery基础；
- 新增PostgreSQL 18 + pgvector + Redis Docker Compose；
- 首个迁移启用`vector`、`pg_trgm`和`unaccent`；
- 新增Python/前端/Compose CI；
- 正式文档删除TypeScript后端和Qdrant基线，改为PostgreSQL单一事实库；
- 明确不引入外部Embedding服务，首期使用全文检索和`pg_trgm`。

本地已完成静态检查；依赖安装、真实Docker拉取和完整CI需在具备正常网络的环境验证。

### 本次验证结果

已通过：

- `python -m compileall`：后端源码、测试和Alembic迁移语法通过；
- `pyproject.toml`、JSON、Compose YAML和CI YAML解析；
- `git diff --check`；
- Markdown相对链接检查；
- 旧TypeScript后端和Qdrant设计残留检查；
- Python包使用setuptools完成editable构建；
- `test_agent_models.py`通过。

未完成：

- 完整Python依赖安装：当前内部PyPI代理缺少Celery、Redis、structlog、pgvector等依赖；
- 完整pytest、Ruff和mypy：受上述依赖限制；
- 前端typecheck/build：当前环境未安装React、Ant Design等npm依赖；
- `docker compose config/up`：当前执行环境没有Docker命令。

GitHub CI已配置在正常公网包源环境执行前端、后端和Compose检查。

## 2026-08-01 首个后端垂直切片

已实现并检查：

- SQLAlchemy 2 正式映射：ContextSnapshot、MessageCandidate、LegalMatter、WorkItem；
- CandidateMatterLink、AuditEvent、OutboxEvent、IdempotencyRecord；
- Alembic `20260801_0002` 首批业务表迁移及完整降级顺序；
- Candidate确认创建Matter和多个初始WorkItem的原子用例；
- PostgreSQL行锁、事务级advisory幂等锁、SQLAlchemy乐观锁、审计和事务Outbox；
- Candidate/Matter/WorkItem查询和写入API；
- 应用层单元测试、幂等冲突测试、version冲突测试和ORM元数据测试；
- CI中的真实PostgreSQL迁移及HTTP端到端集成测试。

本地已执行：

- `python -m compileall`：通过；
- 核心垂直切片与ORM测试：12项通过；
- PostgreSQL HTTP集成测试：已加入，当前本地环境按配置跳过；
- `alembic upgrade head --sql`：通过，成功生成PostgreSQL离线DDL；
- Python文件100字符行宽检查：通过；
- `git diff --check`：通过。

当前环境的内部Python包源仍缺少`structlog`、`redis`、`psycopg`等公开依赖，且没有Docker命令，因此未在本环境执行完整测试套件和真实PostgreSQL迁移。声明依赖完整的CI或本地Docker环境应继续执行Ruff、mypy、全量pytest及真实数据库升级/降级验证。

## 2026-08-01 完整法务工作流与飞书接入

已实现：

- 前端接入Candidate、Matter、WorkItem、优先级、Deadline、Dependency和审核接口；
- PriorityConfirmation、Deadline、WorkItemDependency正式模型与迁移；
- ReviewPackage、ReviewRecord、Communication及外发审核门禁；
- Outbox并发领取、指数退避、重试、死信和重新入队；
- 飞书原始事件和消息按event_id、tenant_key/message_id幂等落库；
- Communication正文哈希校验，防止审核后正文被静默修改；
- Celery Beat定时发布Outbox，Compose增加scheduler角色。

本轮按功能优先要求未新增测试，完成了Python语法、Alembic离线升级/降级、TypeScript语法、TOML/JSON/YAML和`git diff --check`等静态检查。完整运行验证仍需在具备Docker及公网依赖源的环境执行。
