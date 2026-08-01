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

## 阶段一增量结果：飞书本地消息接入

- **已实现**：官方 `lark-oapi` SDK 长连接和现有 Webhook 共用 `IngestFeishuEventHandler`；长连接支持启动、SDK 心跳、内部重连、外层 `1/2/4/8/16/30` 秒退避和优雅退出；
- **已实现**：`integration_connections`、`feishu_message_versions`、`feishu_attachments` 及迁移 `20260801_0005`；连接错误、事件时间、重连次数和补偿结果不再只存在内存；
- **已实现**：text/post/file/image、回复、线程、编辑、撤回和 unsupported 标准化；unsupported 可见但不写分析 Outbox；
- **已实现**：附件受控下载、大小上限、权限化路径、SHA-256 和默认 `authorized_for_analysis=false`；没有 OCR/正文解析；
- **已实现**：`GET status`、`POST reconnect`、`POST reconcile`；写接口要求后端认证 Actor、Idempotency-Key、Correlation ID 并写审计；
- **已通过模拟验证**：15 个飞书新增针对性测试，长连接失败两次后按 1/2 秒退避并在成功时保持连接；全量后端测试 76 passed、2 skipped；
- **已通过真实 PostgreSQL 验证**：临时数据库从空库升级到 `20260801_0005`，执行 `downgrade -1 → upgrade head` 成功；两条数据库集成测试 `2 passed`；
- **尚未真实集成验证**：当前环境未提供飞书 App ID/Secret、租户和授权群聊，未连接真实飞书。远端补偿是配置群聊的时间窗查询，不承诺租户全量零遗漏；加密 Webhook 仍拒绝。

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

## 阶段二增量结果：Codex 消息解析加固

- **已实现**：CLI 存在性、固定版本、隔离认证和运行目录可写检查，健康状态区分 `available/unauthenticated/version_mismatch/misconfigured/unreachable`，不把“已安装”当作可推理；
- **已实现**：ContextSnapshot v2 将当前/父/根/线程消息、参与者、附件元数据、消息版本、Builder/选择策略版本、内容哈希和截断指标持久化，创建后不可修改；
- **已实现**：AgentRun 的 `queued → preparing → running → validating → completed/failed` 每次迁移追加状态事件，并记录 Worker、租约、Runtime/Agent/Prompt 版本、校验错误、修复次数和可用时的 Token 用量；
- **已实现**：飞书正文被标记为不可信业务证据；Prompt 明确禁止执行消息命令、Shell、环境变量读取、未授权文件读取、数据库修改、飞书回复和自动建 Matter；
- **已实现**：JSON、Pydantic 和业务规则失败后最多使用同一快照修复一次；第二次失败不创建 Candidate，禁止正则或手工拼接修 JSON；
- **已实现**：`candidate_revisions` 保存每次分析 Payload、Run、修订号和 superseded 关系；重新分析不再无痕覆盖；
- **已实现**：PostgreSQL 恢复服务扫描无活动 Run 的排队消息、陈旧 queued Run 和过期 preparing/running 租约，通过 Outbox 重派，耗尽后进入 `dead_letter`；
- **已通过模拟验证**：11 类消息 Fake Runtime 冒烟全部成功；闲聊、仅供知悉和 Prompt 注入不创建 Candidate，其他合法请求均完成严格校验；
- **已通过真实 PostgreSQL 验证**：迁移 `20260801_0005 → 0006 → 0005 → 0006` 成功；集成测试验证状态历史与 Candidate revision 均落库；
- **尚未真实集成验证**：宿主 CLI `0.146.0-alpha.9.2` 与配置 `0.145.0-alpha.9` 不匹配；即使按宿主版本检查，隔离环境仍为 `missing_runtime_api_key`。未发起真实模型推理请求。

## 数据库与运行时验证

- PostgreSQL 18 临时数据库上执行 `alembic upgrade head → downgrade -1 → upgrade head`，当前版本为 `20260801_0006 (head)`；
- 在 `20260801_0003` 插入两个历史重复 ContextSnapshot 和一个历史 Candidate 外部 Agent UUID 后执行升级/降级，快照没有被合并删除，历史 UUID 可完整恢复；
- PostgreSQL 集成测试验证 `FeishuMessage → ContextSnapshot → AgentRun → MessageCandidate`，结果为 `2 passed, 62 deselected`；
- Worker 镜像构建成功，包含固定版本 `codex-cli 0.145.0-alpha.9`；
- 镜像内已创建专用 `codex-agent` UID/GID 10001；
- Runtime 的完整 `--strict-config`、只读 sandbox、工具禁用和输出 Schema 参数通过当前 CLI 无联网参数解析检查；
- 普通单元测试使用 `FakeAgentRuntime`，不调用真实 Codex。
- Runtime 测试验证即使工具全部禁用，stdin 仍包含唯一授权消息内容；重分析测试验证待确认 Candidate 更新/作废语义。

## 阶段三增量结果：可运营工作台

- **已实现**：React Router 与 TanStack Query 接管 `/inbox`、消息详情、Candidate 跳转、AgentRun 列表/详情、系统状态和 Matter 路由；核心页面不读取 Mock 状态；
- **已实现**：AI 收件箱按待分析、排队、分析中、待确认、已处理、忽略、失败和死信分类，并支持正文、分类、时间和群聊筛选；
- **已实现**：消息详情左右分栏显示原文/线程/附件/编辑撤回历史，以及 Agent 状态、版本、建议、已确认事实、AI 推断、缺失信息和分析修订；人工可创建、关联、登记更新、仅供知悉、忽略或重新分析；
- **已实现**：Agent 运行中心显示状态历史、ContextSnapshot、实际来源、版本、租约、Worker、校验错误、受限输出和 Candidate，并提供取消与重试；
- **已实现**：系统状态页读取 FastAPI/PostgreSQL/Redis/Celery/Feishu/Codex/队列/死信真实健康值，危险恢复操作二次确认；Outbox 死信重入队增加 Actor、幂等、Correlation ID 和审计；
- **已实现**：SSE 区分 `system.health`、`message.ingested`、`agent-run.updated`、`candidate.created` 和 `outbox.failed`；连续失败后回退到 15 秒轮询；
- **已通过自动化验证**：前端测试覆盖收件箱状态映射、消息详情、事实与推断视觉分离、Agent 状态刷新、SSE 退避/轮询、幂等键复用、结构化错误和 Candidate 人工动作请求头；
- **部分实现**：SSE 当前使用数据库健康快照差异检测，不是 PostgreSQL LISTEN/NOTIFY；列表为上限分页而非游标分页；前端生产包仍有大 chunk 警告；
- **尚未真实集成验证**：因缺飞书凭证和隔离 Codex 认证，真实消息→真实模型→人工确认的现场演示未执行；Fake Runtime + PostgreSQL 闭环是本轮可重复验证基线。

## 最终验证命令

提交前以本节记录的最终结果为准。宿主 `.venv` 为 Python 3.14.6，生产镜像按项目基线使用 Python 3.12.13：

```bash
git diff --check
cd apps/backend
../../.venv/bin/python -m compileall src
../../.venv/bin/ruff check .
../../.venv/bin/mypy --config-file pyproject.toml src
../../.venv/bin/pytest --disable-warnings
# 89 passed, 3 skipped, 390 warnings

RUN_POSTGRES_INTEGRATION_TESTS=1 \
LEGAL_WORKBENCH_TEST_DATABASE_URL=postgresql+psycopg://legal_workbench:change-me-local-only@127.0.0.1:5432/legal_workbench_stage3_019fbdd2 \
../../.venv/bin/pytest -m integration --disable-warnings
# 3 passed, 89 deselected, 30 warnings

../../.venv/bin/python ../../scripts/smoke_test_codex_triage.py \
  --database-url postgresql+psycopg://legal_workbench:change-me-local-only@127.0.0.1:5432/legal_workbench_stage3_019fbdd2 \
  --runtime fake --allow-database-write
# 11/11 success；realInferenceExecuted=false

cd ../web
npm install
npm run typecheck
npm test
npm run build
# 6 test files / 10 tests passed；构建成功
cd ../..
docker compose config --quiet
docker compose build
docker compose up -d postgres redis api worker scheduler web
docker compose ps
# API/PostgreSQL/Redis healthy；Worker/Scheduler/Web running

cd apps/backend
LEGAL_WORKBENCH_DATABASE_URL=postgresql+psycopg://legal_workbench:change-me-local-only@127.0.0.1:5432/legal_workbench_stage3_019fbdd2 \
  ../../.venv/bin/alembic -c alembic.ini upgrade head
LEGAL_WORKBENCH_DATABASE_URL=postgresql+psycopg://legal_workbench:change-me-local-only@127.0.0.1:5432/legal_workbench_stage3_019fbdd2 \
  ../../.venv/bin/alembic -c alembic.ini downgrade -1
LEGAL_WORKBENCH_DATABASE_URL=postgresql+psycopg://legal_workbench:change-me-local-only@127.0.0.1:5432/legal_workbench_stage3_019fbdd2 \
  ../../.venv/bin/alembic -c alembic.ini upgrade head
# 20260801_0006 (head)

cd ../..
docker compose run --rm --no-deps --entrypoint codex worker --version
# codex-cli 0.145.0-alpha.9
docker compose run --rm --no-deps --entrypoint id worker codex-agent
# uid=10001(codex-agent) gid=10001(codex-agent) groups=10001(codex-agent)
```

结果：`git diff --check`、`compileall`、Ruff、mypy、pytest、迁移往返、数据库集成测试、Fake Runtime 冒烟、前端 typecheck/test/build、Compose 配置和全部镜像构建均通过。Vite 构建产生单个 `1,440.35 kB`（gzip `453.38 kB`）chunk 警告，不影响构建成功。

`npm audit` 返回 `2 high`：两项均源自 React Router 的 RSC Action CSRF 公告 `GHSA-qwww-vcr4-c8h2`。当前 Registry 最新 `react-router-dom` 为 `7.18.2`，公告要求 `>=8.3.0`，暂无可安装修复版本；本项目是纯 Vite SPA，不启用 RSC/Server Actions，但该上游告警仍明确保留，未通过降级或强制安装掩盖。

## 故障注入与恢复

- **已通过模拟验证**：停止 Redis 后，PostgreSQL 中消息、Run、Candidate 与 Outbox 数量不变；系统状态准确显示 Redis/Worker/Scheduler 不可用；Redis 启动并执行 `FLUSHALL` 后，恢复扫描可从 PostgreSQL 重新发现任务，Scheduler 心跳重新建立；
- **已通过模拟验证**：停止/恢复 Worker，系统状态由降级恢复正常；停止/恢复 API，HTTP 由不可达恢复 200；
- **已通过模拟验证**：终止无网络隔离容器中的实际 `codex exec` 进程，退出码为 137；AgentRun 租约超时、重派与死信路径由自动化测试覆盖。因缺真实认证，这不是一次真实模型运行中的故障；
- **已通过模拟验证**：飞书连接器在 `ENABLE_REAL_FEISHU=false` 时持久化为 `disabled`，人工重连返回 HTTP 409 `INVALID_STATE_TRANSITION`；长连接断线按 `1/2/4/8/16/30` 秒退避测试通过；
- **修复并回归**：故障演练发现 Celery Beat 任务复用了跨事件循环异步 Redis 客户端，已改为每次任务使用独立同步客户端并增加回归测试；系统页 Worker 探测阈值由 0.5 秒调整为 1 秒，减少单 Worker Mac 的瞬时误报。

## 页面可视化验证

浏览器基于 Compose 实例和真实 API 数据完成检查，控制台 `error/warning` 为 0：

![AI 收件箱](screenshots/ai-inbox.png)

![消息详情与人工确认](screenshots/message-detail.png)

![Agent 运行中心](screenshots/agent-run-center.png)

![系统状态](screenshots/system-health.png)

## 部分实现与未验证项

- 已完成真实 Codex CLI 二进制、版本、特性注册表及严格参数解析检查；当前环境未向容器提供 Codex 认证，因此未发起真实模型推理请求，也不声称真实模型调用通过；
- 宿主机模式依赖 Codex CLI 只读 sandbox 和工作目录约束，不是可证明的完整文件读取白名单；
- Agent 可控 Web/浏览器/MCP 工具已关闭，但模型传输仍需要服务端出网；当前 Compose 尚未配置目的地址 allowlist 或代理级 egress 限制；
- 飞书长连接、Verification Token Webhook 和配置群聊时间窗补偿代码已实现并通过模拟/数据库验证；真实凭证联调和加密 Webhook 尚未完成；
- 生产认证的外部登录/会话签发器尚未实现；本轮只建立可扩展的后端会话边界；
- Candidate 的“更新已有 Matter”当前只登记可审计关联与人工决定，不静默覆盖已有 Matter 字段；字段级更新应在后续单独定义并通过版本冲突测试；
- SSE 当前基于 PostgreSQL 快照差异，不提供跨重启事件游标；前端路由包仍需做按页分包。
