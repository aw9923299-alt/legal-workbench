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
agents        codex-runner
integrations  feishu-connector、file-indexer
```

Profiles中的进程当前是工程入口，不代表真实功能已实现。

## 3. 镜像策略

- Python：3.12 slim；
- Node：22 Alpine，仅用于前端构建；
- Web运行：Nginx；
- PostgreSQL：固定`pgvector/pgvector:0.8.5-pg18-bookworm`；
- Redis：稳定主版本镜像，正式部署应补充digest锁定。

禁止长期使用`latest`。依赖升级通过独立PR和回归测试。

## 4. 持久化

| 数据 | 存储 | 说明 |
|---|---|---|
| 领域、审计、知识元数据和正文 | PostgreSQL Volume | 唯一事实库，每日备份 |
| 队列和延时任务 | Redis AOF | 可重建但需持久化 |
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
- 运行租约过期后标记abandoned并人工或自动恢复。

## 9. 健康检查

- `/api/v1/health/live`：进程存活；
- `/api/v1/health/ready`：PostgreSQL和Redis就绪；
- 飞书连接状态和最后事件时间；
- Celery队列长度、最老任务和死信；
- Codex运行数、超时和租约；
- 文件解析失败；
- 磁盘空间和最近备份。

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
```

集成Profiles在功能实现和安全评审完成后才启用：

```bash
docker compose --profile integrations --profile agents up -d
```
