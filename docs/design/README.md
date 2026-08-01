# 法务工作台正式设计索引

本文档目录是项目的权威设计基线。README和其他概览文档只能摘要引用，不得维护相互冲突的第二套架构。

## 阅读顺序

1. [`SYSTEM_DESIGN.md`](./SYSTEM_DESIGN.md)：产品闭环、逻辑分层和职责边界；
2. [`BACKEND_ENGINEERING.md`](./BACKEND_ENGINEERING.md)：Python模块化单体、事务和进程角色；
3. [`DATA_MODEL.md`](./DATA_MODEL.md)：实体、关系、状态机和不变量；
4. [`AGENT_PROTOCOL.md`](./AGENT_PROTOCOL.md)：Codex Agent统一协议和质量门槛；
5. [`KNOWLEDGE_RETRIEVAL.md`](./KNOWLEDGE_RETRIEVAL.md)：PostgreSQL全文、pg_trgm和可选pgvector；
6. [`API_CONTRACTS.md`](./API_CONTRACTS.md)：HTTP、事件和错误契约；
7. [`DEPLOYMENT.md`](./DEPLOYMENT.md)：Docker Compose、Mac守护、备份和恢复；
8. [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md)：阶段、顺序和验收；
9. [`DECISIONS.md`](./DECISIONS.md)：已确认的ADR。

## 当前技术基线

```text
React + TypeScript
Python 3.12 + FastAPI + Pydantic
SQLAlchemy 2 + Psycopg 3 + Alembic
PostgreSQL 18 + pgvector
Celery + Redis
Docker Compose + launchd
Codex-only AI policy
```

## 变更规则

以下变化必须新增或更新ADR：

- 引入新的AI或Embedding服务；
- 更换主数据库；
- 绕过人工外发审核；
- 拆分独立微服务；
- 修改核心领域链路；
- 修改知识资料的权限、保留或Legal Hold规则。
