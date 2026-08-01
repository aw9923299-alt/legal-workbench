# Claude Code / Codex 项目交接说明

更新日期：2026-08-01

## 当前阶段

仓库已完成从单一前端原型到工业化工程骨架的第一步：

- 前端迁入 `apps/web`；
- 新增 `apps/backend` Python模块化单体；
- 新增FastAPI健康检查、SQLAlchemy、Alembic和Celery基础；
- 新增PostgreSQL 18 + pgvector + Redis Docker Compose；
- 正式设计已切换为Python后端和PostgreSQL单一事实库。

真实领域表、飞书接入、Codex Runner、文件解析和专业Agent尚未实现。

## 已实现的工程骨架

| 模块 | 状态 |
|---|---|
| React工作台 | Mock原型，已迁入 `apps/web` |
| FastAPI应用 | 已建立，含live/ready健康检查 |
| PostgreSQL连接 | 已建立SQLAlchemy异步Engine |
| Alembic | 已建立，首个迁移启用vector/pg_trgm/unaccent |
| Celery/Redis | 已建立最小Worker和ping任务 |
| Docker Compose | api/worker/web/postgres/redis可编排 |
| Codex/飞书/索引进程 | 仅提供禁用状态的骨架入口 |
| 正式设计 | 已更新为Python + PostgreSQL + pgvector |

## 关键技术债

1. 尚未建立正式领域SQLAlchemy模型；
2. 尚未实现事务Outbox和死信表；
3. 前端仍使用旧Task ViewModel和Mock；
4. 未生成Python和npm锁文件；
5. 未实现认证、权限和字段脱敏；
6. 未实现飞书事件幂等和补偿同步；
7. 未实现Codex隔离执行；
8. 知识库尚无解析器、版本和检索接口；
9. Compose中的集成Profiles是骨架，不应当作已上线能力。

## 下一迭代

优先完成“候选消息和事项”后端垂直切片：

```text
SQLAlchemy模型与迁移
→ MessageCandidate API
→ LegalMatter/WorkItem API
→ 幂等与乐观锁
→ 前端从Mock切换到FastAPI
→ 组件和集成测试
```

暂不接真实飞书、Codex和外发。
