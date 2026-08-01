# Claude Code / Codex 下一轮开发指令

```text
你正在继续开发 GitHub 仓库 aw9923299-alt/legal-workbench。

当前技术基线：
- apps/web：React + TypeScript + Vite + Ant Design
- apps/backend：Python 3.12 + FastAPI + Pydantic + SQLAlchemy 2
- PostgreSQL 18 + pgvector，Alembic迁移
- Celery + Redis
- Docker Compose
- Codex是唯一推理和生成AI，但本轮不接真实Codex

开始前必须阅读：
1. AGENTS.md
2. README.md
3. docs/design/README.md
4. docs/design/SYSTEM_DESIGN.md
5. docs/design/BACKEND_ENGINEERING.md
6. docs/design/DATA_MODEL.md
7. docs/design/API_CONTRACTS.md
8. docs/design/IMPLEMENTATION_PLAN.md
9. docs/CODEX_HANDOFF.md

本轮目标：实现 MessageCandidate → LegalMatter → WorkItem 的后端垂直切片，并让前端候选确认页面通过API运行。

必须完成：
- SQLAlchemy模型和Alembic迁移；
- Repository和Application Service；
- FastAPI CRUD/confirm接口；
- 幂等键、乐观锁和审计事件；
- Pydantic请求/响应Schema；
- OpenAPI错误模型；
- pytest单元/集成测试；
- 前端API客户端和TanStack Query或等价查询层；
- 保留Mock模式用于演示；
- 不接真实飞书、Codex、知识文件或外发。

不可违反：
- 不使用单一Task承载全部对象；
- 人工确认值不得被后续自动分析覆盖；
- 所有数据库变更必须通过Alembic；
- 不引入其他AI、Embedding API或Qdrant；
- 不绕过ReviewRecord发送门禁；
- 不提交真实敏感数据和凭据。

验收：
1. docker compose up -d 可启动postgres/redis/api/web/worker；
2. Alembic可从空库升级；
3. 同一candidate确认请求重复提交不重复创建事项；
4. version冲突返回409；
5. 一条candidate可创建一个Matter和多个WorkItem；
6. API测试、ruff、mypy、前端typecheck/build通过；
7. 更新设计、QA和迁移说明。
```
