# QA Report

更新日期：2026-08-01

## 本轮范围

验证主闭环：

```text
FeishuEvent → FeishuMessage → FeishuMessageReceived Outbox
→ Celery Worker → ContextSnapshot → AgentRun
→ CodexCliRuntime/FakeAgentRuntime → MessageCandidate → 人工确认
```

同时覆盖未知 Outbox 事件、前端重试幂等键、认证边界和真实飞书配置 fail-closed。

## 已实现并验证

- `message_judgement` 输出使用 Pydantic 2 严格 Schema，禁止额外字段，置信度限制为 0–1；
- ContextSnapshot 定长、定序、SHA-256 去重且持久化；
- AgentRun 状态迁移、乐观锁、心跳、超时、尝试次数、失败码和 Correlation ID；
- Runtime 不在数据库长事务内执行；完成前后分两次短事务落库；
- 有效相关结果创建唯一活跃 Candidate；无关结果不创建；低置信度不跳过人工确认；
- Outbox 未注册事件会以 `UNSUPPORTED_OUTBOX_EVENT` 失败，按指数退避重试并死信；
- HttpOnly 会话解析 Actor；只有 `local/development` 签发本地 Session，非本地环境要求显式 Secret，Compose 端口仅绑定本机；
- `ENABLE_REAL_FEISHU=false` 时 Webhook 直接返回 503；启用时缺少 Verification Token 会在配置加载阶段失败，仅 Encrypt Key 也不能启动真实模式；
- 前端显示 Agent 版本、状态、理由、置信度、已确认事实、推断、期限候选和缺失信息；
- 一次前端业务操作在自动网络重试和用户再次点击间，通过 `sessionStorage` 复用同一 `Idempotency-Key`，直到明确响应、请求内容变化或用户取消。

## 数据库与运行时验证

- PostgreSQL 18 实例上执行 `alembic upgrade head → downgrade -1 → upgrade head`，最终版本为 `20260801_0004 (head)`；
- 在 `20260801_0003` 插入两个历史重复 ContextSnapshot 和一个历史 Candidate 外部 Agent UUID 后执行升级/降级，快照没有被合并删除，历史 UUID 可完整恢复；
- PostgreSQL 集成测试验证 `FeishuMessage → ContextSnapshot → AgentRun → MessageCandidate`，结果为 `2 passed, 62 deselected`；
- Worker 镜像构建成功，包含固定版本 `codex-cli 0.145.0-alpha.9`；
- 镜像内已创建专用 `codex-agent` UID/GID 10001；
- Runtime 的完整 `--strict-config`、只读 sandbox、工具禁用和输出 Schema 参数通过当前 CLI 无联网参数解析检查；
- 普通单元测试使用 `FakeAgentRuntime`，不调用真实 Codex。
- Runtime 测试验证即使工具全部禁用，stdin 仍包含唯一授权消息内容；重分析测试验证待确认 Candidate 更新/作废语义。

## 最终验证命令

提交前以本节记录的最终结果为准。后端命令均使用仓库根目录 `.venv`：

```bash
git diff --check
cd apps/backend
../../.venv/bin/python -m compileall src
../../.venv/bin/ruff check .
../../.venv/bin/mypy src
../../.venv/bin/pytest --disable-warnings
# 63 passed, 2 skipped, 281 warnings

RUN_POSTGRES_INTEGRATION_TESTS=1 \
LEGAL_WORKBENCH_TEST_DATABASE_URL=postgresql+psycopg://legal_workbench:change-me-local-only@127.0.0.1:5432/legal_workbench \
../../.venv/bin/pytest -m integration --disable-warnings
# 2 passed, 63 deselected, 20 warnings

cd ../web
npm install
npm run typecheck
npm run build
cd ../..
docker compose config --quiet
docker compose up -d postgres redis
docker compose run --rm --no-deps worker alembic -c apps/backend/alembic.ini upgrade head
docker compose run --rm --no-deps worker alembic -c apps/backend/alembic.ini downgrade -1
docker compose run --rm --no-deps worker alembic -c apps/backend/alembic.ini upgrade head
docker compose run --rm --no-deps worker alembic -c apps/backend/alembic.ini current
# 20260801_0004 (head)

docker compose build worker
docker compose run --rm --no-deps --entrypoint codex worker --version
# codex-cli 0.145.0-alpha.9
docker compose run --rm --no-deps --entrypoint id worker codex-agent
# uid=10001(codex-agent) gid=10001(codex-agent) groups=10001(codex-agent)
```

结果：`compileall`、Ruff、mypy、pytest、迁移往返、数据库集成测试、前端 typecheck/build、Compose 配置、Worker 镜像构建均通过。Vite 构建产生单个约 1.30 MB chunk 的体积警告，不影响构建成功。

## 部分实现与未验证项

- 已完成真实 Codex CLI 二进制、版本、特性注册表及严格参数解析检查；当前环境未向容器提供 Codex 认证，因此未发起真实模型推理请求，也不声称真实模型调用通过；
- 宿主机模式依赖 Codex CLI 只读 sandbox 和工作目录约束，不是可证明的完整文件读取白名单；
- Agent 可控 Web/浏览器/MCP 工具已关闭，但模型传输仍需要服务端出网；当前 Compose 尚未配置目的地址 allowlist 或代理级 egress 限制；
- 飞书 Verification Token 回调已实现，加密回调解密、WebSocket 长连接和补偿同步尚未实现；
- 生产认证的外部登录/会话签发器尚未实现；本轮只建立可扩展的后端会话边界。
