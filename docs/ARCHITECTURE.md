# 系统架构概览

完整设计见 [`docs/design/SYSTEM_DESIGN.md`](./design/SYSTEM_DESIGN.md)、[`BACKEND_ENGINEERING.md`](./design/BACKEND_ENGINEERING.md) 和 [`DEPLOYMENT.md`](./design/DEPLOYMENT.md)。

## 核心架构

```text
React Web
   ↓ HTTP / SSE
FastAPI API
   ↓
Application Use Cases + Manager Orchestrator
   ↓
Domain Policies / Agent Runtime / Integration Adapters / Celery Workers
   ↓
PostgreSQL 18 + pgvector + Redis + Local File Storage
```

后端采用一个Python模块化单体，通过不同进程角色运行API、Worker、飞书连接、文件索引和Codex Runner。初期不拆独立微服务或独立仓库。

## 运行组件

- `web`：React工作台；
- `api`：FastAPI、用例、审核门禁和查询接口；
- `worker`：Celery后台任务、重试、日报和索引；
- `feishu-connector`：受控飞书事件和发送适配；
- `worker + CodexCliRuntime`：当前唯一业务Codex执行入口；
- `file-indexer`：本地资料解析和索引；
- `postgres`：业务事实、审计、全文检索、知识元数据和可选向量；
- `redis`：队列、锁、短期缓存和延时任务。

## 确定性服务与Agent边界

确定性服务负责状态、硬期限、权限、幂等、事务、重试、审核门禁和发送；Codex Agent负责语义理解、专业分析、回复草拟、日报归纳和复盘建议。

## 知识检索

首期采用：

```text
Metadata Filter
+ PostgreSQL Full Text Search
+ pg_trgm Similarity
+ Codex reranking/selection
```

pgvector扩展已启用，但向量字段必须可空；在没有经批准的本地向量生成方案前，不把向量召回作为上线前置条件。
