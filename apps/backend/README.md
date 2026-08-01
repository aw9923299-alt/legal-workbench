# Legal Workbench Backend

模块化 Python 后端。一个代码库通过不同进程角色提供 API、后台任务、飞书连接、文件索引和 Codex 运行能力，避免在初期拆成多个独立微服务。

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

正式业务对象和接口以 `docs/design/` 为准。当前代码只提供工程骨架、健康检查、数据库和队列基础设施，不代表飞书或 Codex 已经接入。
