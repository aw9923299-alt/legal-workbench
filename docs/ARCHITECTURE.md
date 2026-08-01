# 系统架构概览

本文件保留为架构快速入口。完整设计见 [`docs/design/SYSTEM_DESIGN.md`](./design/SYSTEM_DESIGN.md) 和 [`docs/design/DEPLOYMENT.md`](./design/DEPLOYMENT.md)。

## 1. 核心架构

```text
Web Frontend
   ↓
API / Application Service
   ↓
Legal Domain + Manager Orchestrator
   ↓
Workers + Codex Runtime + Knowledge Service
   ↓
PostgreSQL + Redis + Qdrant + Local File Storage
```

## 2. 管家拆分

前端对用户呈现统一“法务管家”，内部由确定性编排器协调：

- 消息研判 Agent；
- 事项归并 Agent；
- 任务规划 Agent；
- 优先级建议 Agent；
- 结果汇总 Agent；
- 日报与工作复盘 Agent。

专业 Agent只产出草稿交付物，不直接修改正式记录或发送消息。

## 3. 运行组件

```text
web
api
feishu-connector
worker
codex-runner
file-indexer
postgres
redis
qdrant
watchdog
```

初期后端可采用模块化单体，通过不同进程/容器运行，不要求立即拆成多个独立仓库或微服务。

## 4. 核心链路

```text
FeishuMessage
→ ContextSnapshot
→ MessageCandidate
→ LegalMatter + WorkItem
→ AgentExecutionPlan
→ AgentRun + DraftArtifact
→ ReviewPackage + ReviewRecord
→ Communication
```

## 5. 确定性服务边界

确定性服务负责：

- 飞书连接、幂等、重试和发送；
- 状态迁移、硬期限和审核门禁；
- 权限、审计、文件版本和备份；
- 队列、死信和恢复。

Codex Agent负责：

- 消息理解和关联建议；
- 任务规划和软优先级；
- 专业分析、回复草拟；
- 审核差异分析、日报和复盘归纳。

## 6. 前端演进

建议逐步迁移为：

```text
src/
├─ app/
├─ features/
├─ entities/
├─ shared/
├─ services/
└─ mocks/
```

当前不为目录美观一次性重构。先引入路由、应用服务和正式领域类型，再按功能迁移。
