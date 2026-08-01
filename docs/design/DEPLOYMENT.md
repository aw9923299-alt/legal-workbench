# Mac + Docker Compose 部署与可靠性设计

## 1. 部署目标

系统运行在法务专员本地 Mac 上，通过 Docker Compose 提供一致的依赖环境、健康检查、自动重启和数据持久化。设计目标是“尽可能稳定且可恢复”，不是宣称单台个人电脑具备数据中心级高可用。

必须明确：

- Docker 可以重启容器，但不能在 Mac 关机或深度休眠时继续执行；
- Docker Desktop 或容器运行时未启动时，`restart` 策略无法生效；
- 因此可靠性由容器、主机守护、事件补偿和备份共同提供。

## 2. 推荐目录结构

```text
infra/
├─ docker-compose.yml
├─ docker-compose.dev.yml
├─ env/
│  ├─ api.env.example
│  ├─ feishu.env.example
│  └─ codex.env.example
├─ postgres/
│  └─ init/
├─ qdrant/
├─ redis/
├─ scripts/
│  ├─ start.sh
│  ├─ health.sh
│  ├─ backup.sh
│  ├─ restore.sh
│  └─ reconcile.sh
└─ launchd/
   └─ com.legalworkbench.service.plist.example
```

## 3. Docker Compose 服务

```yaml
services:
  web:
    build: ./apps/web
    restart: unless-stopped
    depends_on:
      api:
        condition: service_healthy

  api:
    build: ./apps/api
    restart: unless-stopped
    env_file: ./infra/env/api.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  feishu-connector:
    build: ./apps/api
    command: ["node", "dist/feishu.js"]
    restart: unless-stopped
    env_file: ./infra/env/feishu.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  worker:
    build: ./apps/api
    command: ["node", "dist/worker.js"]
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      codex-runner:
        condition: service_healthy

  codex-runner:
    build: ./apps/codex-runner
    restart: unless-stopped
    env_file: ./infra/env/codex.env
    volumes:
      - codex_runs:/runs
      - ${LEGAL_KNOWLEDGE_DIR}:/knowledge:ro
    healthcheck:
      test: ["CMD", "node", "dist/health.js"]
      interval: 30s
      timeout: 5s
      retries: 3

  file-indexer:
    build: ./apps/api
    command: ["node", "dist/indexer.js"]
    restart: unless-stopped
    volumes:
      - ${LEGAL_KNOWLEDGE_DIR}:/knowledge:ro
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy

  postgres:
    image: postgres:17
    restart: unless-stopped
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $POSTGRES_USER"]
      interval: 10s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 10

  qdrant:
    image: qdrant/qdrant:latest
    restart: unless-stopped
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:6333/healthz || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 10

  watchdog:
    build: ./apps/watchdog
    restart: unless-stopped
    depends_on:
      api:
        condition: service_healthy
```

实际实现应固定镜像版本，不能长期使用 `latest`。

## 4. 持久化与数据位置

| 数据 | 存储位置 | 备份要求 |
|---|---|---|
| 领域数据和审计 | PostgreSQL Volume | 每日备份 |
| 队列和延时任务 | Redis AOF | 可重建但需保留 |
| 向量索引 | Qdrant Volume | 定期快照，可由源文件重建 |
| 原始附件/派生文件 | 本地受控目录 | 加密备份 |
| Codex 临时工作目录 | `codex_runs` | 按保留策略清理 |
| 提示词/Agent 配置 | Git 仓库 | 版本控制 |

高敏感原始载荷如保存在数据库，应采用字段级或磁盘级加密。密钥不得写入仓库。

## 5. 主机级守护

## 5.1 launchd

使用 `launchd` 实现：

1. 用户登录或开机后启动 Docker 运行环境；
2. 等待 Docker API 可用；
3. 执行 `docker compose up -d`；
4. 定期运行健康脚本；
5. 容器集群完全停止时重新拉起。

示例任务只提交模板，不提交用户真实路径和凭证。

## 5.2 电源策略

若要求接近实时监听：

- 优先使用常驻、接电的 Mac mini；
- 禁止自动深度休眠；
- 允许显示器关闭但保持网络和进程运行；
- 明确记录主机离线窗口。

个人 MacBook 如果经常合盖或断电，只适合作为“在线时实时、离线后补偿”的节点。

## 6. 飞书连接恢复

连接恢复流程：

```text
检测断线
→ 指数退避重连
→ 读取 last_successful_cursor / last_event_at
→ 调用允许的补偿同步接口
→ 幂等写入漏收消息
→ 重放未完成 Outbox/Queue
→ 工作台显示恢复结果
```

如果飞书不支持完整补拉，应在系统状态中显示不可覆盖时间窗，不能静默假设没有消息。

## 7. Worker 可靠性

- 所有长任务持久化到队列；
- Worker 领取任务使用可见性超时；
- 进程退出后任务可重新领取；
- 重试采用指数退避和最大次数；
- 超限进入死信队列；
- 死信必须在工作台可见并可人工重放；
- 同一业务操作使用幂等键和数据库唯一约束。

## 8. Codex Runner 可靠性

- 每次运行独立子进程和工作目录；
- 运行超时后先发送终止信号，再强制杀死；
- 记录 stdout/stderr、退出码和输出校验结果；
- 失败不得写入正式 Artifact；
- 容器重启后从数据库恢复 `queued/running` 异常任务；
- 对 `running` 超过租约时间的 AgentRun 标记为 abandoned 并重试或人工处理。

## 9. 健康检查与告警

最少监控：

- 飞书连接状态和最后消息时间；
- 事件处理延迟；
- 队列长度、最老任务年龄和死信数量；
- Codex Runner 活跃进程和超时；
- PostgreSQL/Redis/Qdrant 健康；
- 文件解析和索引失败；
- 磁盘剩余空间；
- 最近备份时间；
- 发送失败和结果不确定数量。

告警优先展示在本地工作台，并可使用 macOS 通知。外发告警到飞书仍然需要符合外发审核规则；系统级故障告警可单独定义已批准的固定模板，但首期建议只在本地通知。

## 10. 日志

日志要求：

- JSON 结构化；
- 包含 `requestId/correlationId/runId/matterId`；
- 不记录完整合同正文和私聊全文；
- 敏感字段脱敏；
- Docker 日志配置大小和文件数轮转；
- 审计日志与技术日志分开。

## 11. 备份与恢复

每日备份：

- PostgreSQL 逻辑备份；
- Qdrant 快照或索引重建清单；
- 文件元数据和生成产物；
- AgentDefinition、提示词和规则配置已由 Git 保存。

建议：

- 最近 7 天每日备份；
- 最近 4 周每周备份；
- 备份加密；
- 每月至少执行一次恢复演练；
- 恢复后重新校验消息游标、审核版本和向量索引。

## 12. 安全配置

- 飞书和 Codex 凭证通过 `.env` 外部文件或 macOS 钥匙串注入；
- `.env` 文件权限限制为当前用户；
- 后端端口默认只绑定 `127.0.0.1`；
- PostgreSQL、Redis、Qdrant 不暴露到局域网；
- 知识目录只读挂载；
- Codex Runner 使用非 root 用户；
- 容器禁用不必要 capabilities；
- 生成文件写入专用目录；
- 定期更新依赖和基础镜像。

## 13. 开发、测试和生产模式

### 开发模式

- Mock 飞书和 Mock Codex 适配器；
- 热更新；
- 使用脱敏 fixtures；
- 不挂载真实公司目录。

### 本地试运行

- 连接测试飞书应用和受控群；
- Codex 真实运行；
- 使用复制出的脱敏知识目录；
- 所有外发仍需审核；
- AgentDefinition 状态为 `trial`。

### 正式本地运行

- 连接正式授权范围；
- 使用真实本地知识目录；
- 启用备份、监控和 Legal Hold；
- 仅激活通过评测的 Agent；
- 无 Mock 静默回退。
