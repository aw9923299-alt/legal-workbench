# Docker部署与本地可靠性设计

## 1. 目标

在Mac上提供可重复启动、可恢复、可备份的本地运行环境。Docker解决依赖隔离和容器重启，但不能解决主机关机、深度休眠或Docker Desktop停止；主机级问题由`launchd`、电源策略和补偿同步治理。

## 2. 默认Compose服务

```text
web       React静态站点
api       FastAPI
worker    Celery
postgres  PostgreSQL 18 + pgvector
redis     队列和短期协调
```

可选Profiles：

```text
agents        worker 内受控 CodexCliRuntime
integrations  feishu-connector、file-indexer
```

`feishu-connector` 已实现官方 SDK 长连接；真实运行仍需测试应用凭证并显式开启。`file-indexer` 仍是工程入口。

## 3. 镜像策略

- Python：3.12 slim；
- Python依赖：uv 0.12.3读取`apps/backend/uv.lock`，生产环境排除`dev` group并以非editable方式安装；
- Node：22.23.2 Alpine，仅用于前端构建，使用根`package-lock.json`和`npm ci`；
- Web运行：Nginx；
- PostgreSQL：固定`pgvector/pgvector:0.8.5-pg18-bookworm`；
- Redis：稳定主版本镜像，正式部署应补充digest锁定。

禁止长期使用`latest`。依赖升级通过独立PR和回归测试。

## 4. 持久化

| 数据 | 存储 | 说明 |
|---|---|---|
| 领域、审计、知识元数据和正文 | PostgreSQL Volume | 唯一事实库，每日备份 |
| 队列和延时任务 | Redis AOF | 可重建；不得成为任务状态或消息事实库 |
| 飞书附件 | 本地受控目录 | 仅元数据/下载/哈希，默认不授权给 Codex |
| 公司原始资料 | 本地受控目录 | 默认只读挂载给服务 |
| Codex运行目录 | 本地隔离目录 | 定期清理，保留哈希和必要产物 |
| Agent定义和提示词 | Git | 版本控制 |

不再使用独立Qdrant Volume。

## 5. PostgreSQL

启动时由API容器执行Alembic升级。首个迁移启用：

- `vector`；
- `pg_trgm`；
- `unaccent`。

生产化要求：

- 数据库不暴露到局域网；
- 使用独立强密码和本地密钥管理；
- 每日逻辑备份，定期物理快照；
- 每月至少一次恢复演练；
- 大迁移先备份并提供降级或前向修复方案。

## 6. Mac主机保障

- 常驻、接电的Mac mini优于经常合盖的MacBook；
- 禁止深度休眠，允许关闭显示器；
- `launchd`在开机/登录后执行`docker compose up -d`；
- 监控Docker是否可用、最后飞书事件时间、队列年龄和磁盘空间；
- 主机离线窗口写入系统状态。

仓库内 `scripts/legal_workbench_ops.py` 是唯一主机运维入口：

```bash
make ops-start         # 不启动延后的飞书连接器
make ops-wake-check    # 拉起基础服务、检查健康并从 PostgreSQL 恢复任务
make ops-backup        # pg_dump custom 格式、原子落盘、SHA-256、保留期清理
make ops-diagnostics   # 生成不含环境变量、密钥和真实正文的诊断包
make ops-cleanup       # 仅清理过期、非活动、UUID 命名的 Codex 运行目录
make ops-stop          # 暂停接入、等待事务、先停 Worker/Scheduler 再停 Compose
```

运维状态和 5 MiB 滚动日志默认写入 `data/operations`，备份写入 `data/backups`，文件权限为 `0600`；Compose 的全部服务另使用 `json-file` 10 MiB × 3 文件轮转。脚本从 `.env` 读取非敏感运行参数，但失败输出只返回错误类型，不输出异常正文或命令凭证。宿主路径可以用 `LEGAL_WORKBENCH_OPS_STATE_ROOT`、`LEGAL_WORKBENCH_OPS_BACKUP_ROOT`、`LEGAL_WORKBENCH_OPS_CODEX_RUNS_ROOT` 和 `LEGAL_WORKBENCH_OPS_ATTACHMENT_ROOT` 的绝对路径覆盖；同一变量同时驱动主机脚本与 Compose bind source，容器目标仍固定为 `/data/operations`、`/data/backups`、`/data/codex-runs` 和 `/data/feishu-attachments`，避免两侧观察不同目录。

`infra/launchd/com.legal-workbench.supervisor.plist.example` 在登录后及每 300 秒执行唤醒自检；`com.legal-workbench.backup.plist.example` 每日 03:15 备份。一键安全停止会留下持久标记，Supervisor 只记录 `paused`，不会在 5 分钟后擅自拉起；活动事务检查失败或超时也会失败关闭，不继续停止数据库。只有显式 `make ops-start` 才清除标记。自动恢复使用独立 `mac-supervisor / local_supervisor` 审计身份。安装前复制到 `~/Library/LaunchAgents`、用`command -v uv`确认 uv 0.12.3 的绝对路径，并把模板中的 uv、仓库和项目路径占位符全部替换后执行 `plutil -lint`。模板通过`uv run --locked --project apps/backend`运行，不依赖硬编码的Python解释器路径；若本机 Docker 安装在其他位置，仍须同步调整 PATH。当前仓库不会自动改写用户的 launchd 配置；模板 stdout/stderr 指向 `/dev/null`，结果和失败类型统一进入受控滚动运维日志。

执行 Personal Scheduled Sync 的 Worker 必须挂载与 API 相同的 `/data/local-secrets`，因为 TokenProvider 会读取并原子轮换 Workbench OAuth generation；不得用 lark-cli token 代替。当前 Mac 的安装、基础服务、Scheduled Sync、backup/restore 与物理睡眠 blocker 记录在 `artifacts/mac-operations/final-acceptance-20260809.json`；该机器级证据不代表其他安装自动通过。

唤醒自检只有在 PostgreSQL、Redis、Worker、Scheduler 和磁盘/附件配额均正常时才触发 PostgreSQL 恢复。备份缺失/过期和 Codex 未认证会保留为 warning，并把本次唤醒标记为 `degraded`；不会伪装成已就绪。首装时它们不会阻止数据库事实恢复，真实 Codex AgentRun 仍受 Worker 运行时健康门禁保护。

## 7. 飞书恢复

```text
检测断线
→ 指数退避重连
→ 读取last_event_cursor/last_event_at
→ 执行允许的补偿同步
→ 幂等写入
→ 重放Outbox和未完成任务
→ 工作台展示恢复结果和不可覆盖窗口
```

当前远端补偿是配置群聊的时间窗查询，不是租户级游标。按本轮用户指示，真实测试消息和官方长连接验收后置，因此当前 `wake-check` 不启动连接器或调用远端补偿，只保存 `not_executed / REAL_FEISHU_PHASE_DEFERRED`；PostgreSQL Outbox、queued 消息和过期租约仍会恢复。恢复真实飞书阶段后，才在单独验收中启用配置群时间窗补偿。

## 8. Worker与Codex Runner

Worker：

- `acks_late`；
- Worker丢失时任务重新入队；
- 指数退避和最大重试；
- 超限进入死信表；
- 所有业务消费者幂等。

Codex Runner：

- 每个AgentRun独立工作目录；
- 只挂载授权文件；
- 超时先终止再强杀；
- stdout/stderr、退出码和Schema结果写入技术日志；
- 失败不得生成正式Artifact；
- `queued` 超时后重建 Outbox；`preparing/running` 租约过期后以 `AGENT_LEASE_EXPIRED` 标记失败并自动重试，耗尽进入 `dead_letter`；
- Celery Beat 默认每 30 秒使用 PostgreSQL advisory lock 扫描，Redis 清空后仍可从事实表恢复。

## 9. 健康检查

- `/api/v1/health/live`：进程存活；
- `/api/v1/health/ready`：PostgreSQL和Redis就绪；
- `/api/v1/system/health`：FastAPI、PostgreSQL、Redis、Worker、Scheduler、飞书、Codex CLI/认证、磁盘、备份和运行指标；
- `/api/v1/events/stream`：SSE 运行变化，断开不影响 PostgreSQL 事实；
- 飞书连接状态和最后事件时间；
- Celery队列长度、最老任务和死信；
- Codex运行数、超时和租约；
- 文件解析失败；
- 磁盘空间和最近备份。

系统页的“待恢复任务”仅统计 PostgreSQL 中无活动 Run 的待分析消息、陈旧 queued Run，以及心跳陈旧且租约已过期/缺失的 preparing/running Run；仍持有有效未来租约的单并发 Worker 不会被误报。

## 10. 日志和审计

技术日志使用JSON，至少包含`correlationId`、`matterId`、`workItemId`、`runId`。不得记录完整私聊、合同正文、身份证号、手机号、令牌和密钥。

AuditEvent单独存储，记录操作者、动作、对象、版本、原因和时间。审核、外发、规则启用、权限变化和数据删除必须审计。

## 11. 启动和验证

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
curl http://localhost:8000/api/v1/health/live
curl http://localhost:8000/api/v1/health/ready
# 先 POST /api/v1/auth/local-session 获取本地 HttpOnly Session，再访问：
curl --cookie-jar /tmp/legal-workbench-cookie http://localhost:8000/api/v1/system/health
```

故障恢复验证应依次停止/恢复 Redis、Worker 和 API，并检查 PostgreSQL 中 queued 消息、AgentRun 租约、Outbox 和死信仍可由 scheduler 或 `/system/recover-pending-jobs` 恢复。Codex 进程终止测试必须得到明确失败码，不能以伪造成功结果完成。

备份恢复演练应使用独立临时数据库，先对 `.dump` 执行 `pg_restore --list`，再恢复并验证 Alembic head、核心表数量和只追加审计；不得覆盖正在运行的业务库。诊断包只含 Docker/Compose/Git 状态、磁盘及脱敏运维元数据，不含 `.env`、数据库内容、飞书正文或附件。

集成Profiles在功能实现和安全评审完成后才启用：

```bash
docker compose --profile integrations --profile agents up -d
```
