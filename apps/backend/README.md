# Legal Workbench Backend

Python 3.12 模块化单体后端。一个代码库通过不同进程角色提供 API、后台任务、飞书连接、文件索引和 Codex 运行能力，避免首期拆分微服务造成事务和部署复杂度。

## 当前已实现

首个业务垂直切片已经落地：

```text
ContextSnapshot → MessageCandidate
→ 法务确认创建 LegalMatter
→ 同事务创建一个或多个 WorkItem
→ AuditEvent + OutboxEvent + IdempotencyRecord
```

已包含：

- 纯 Python 领域实体和状态不变量；
- SQLAlchemy 2 映射、Repository 和 Unit of Work；
- `version` 乐观锁；
- PostgreSQL 行锁保护候选确认和 WorkItem 顺序写入；
- PostgreSQL事务级advisory lock消除并发幂等竞态；
- Alembic 首批业务表迁移；
- 幂等请求、审计事件和事务 Outbox；
- Candidate、Matter 和 WorkItem 查询及写入 API；
- 应用层单元测试和ORM元数据测试；
- CI真实PostgreSQL迁移及HTTP端到端集成测试。

## API

```text
POST /api/v1/inbox/candidates
GET  /api/v1/inbox/candidates
GET  /api/v1/inbox/candidates/{candidateId}
POST /api/v1/inbox/candidates/{candidateId}/confirm-create

GET  /api/v1/matters
GET  /api/v1/matters/{matterId}
GET  /api/v1/matters/{matterId}/work-items
POST /api/v1/matters/{matterId}/work-items
```

创建Candidate、确认创建事项和新增WorkItem都必须提交：

```text
X-Actor-ID: <法务用户ID>
Idempotency-Key: <调用方生成的唯一键>
```

重复使用相同幂等键和相同请求体会返回原结果；相同键对应不同请求体会返回 `409`。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e 'apps/backend[dev]'
alembic -c apps/backend/alembic.ini upgrade head
uvicorn legal_workbench.main:app --app-dir apps/backend/src --reload
```

后台 Worker：

```bash
celery -A legal_workbench.infrastructure.celery_app:celery_app worker --loglevel=INFO
```

## 验证

```bash
python -m ruff check apps/backend/src apps/backend/tests
python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
python -m pytest apps/backend/tests
PYTHONPATH=apps/backend/src alembic -c apps/backend/alembic.ini upgrade head --sql
```

正式业务对象和接口以 `docs/design/` 为准。飞书、Codex Runtime、审核包和真实外发尚未接入。
