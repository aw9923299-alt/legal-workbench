# 法务工作台设计文档索引

本目录是“法务工作台”从高保真前端原型演进为本地可运行系统的正式实现基线。除非有新的架构决策记录覆盖，本目录中的约束优先于早期讨论稿和页面 Mock。

## 文档导航

| 文档 | 用途 |
|---|---|
| [SYSTEM_DESIGN.md](./SYSTEM_DESIGN.md) | 总体产品边界、模块职责、主流程、异常处理与扩展原则 |
| [DATA_MODEL.md](./DATA_MODEL.md) | 核心实体、关系、状态机、字段来源和数据库建议 |
| [AGENT_PROTOCOL.md](./AGENT_PROTOCOL.md) | Codex Runtime、核心 Agent 拆分、专业 Agent 协议、权限和质量体系 |
| [API_CONTRACTS.md](./API_CONTRACTS.md) | BFF/API、事件、幂等、审核和飞书通信接口契约 |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | Mac + Docker Compose 部署、恢复、监控、备份和安全隔离 |
| [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) | 可执行开发阶段、首条垂直闭环、验收标准与依赖顺序 |
| [DECISIONS.md](./DECISIONS.md) | 已确认的关键架构决策及其后果 |

## 文档使用规则

1. 开发前先阅读 `AGENTS.md`、本索引及与任务相关的设计文档。
2. 任何影响领域模型、Agent 输入输出、审核门禁、飞书权限或数据保留的改动，必须同步更新本目录。
3. 页面字段必须能映射到正式领域对象，不得为展示方便重新引入“一个 Task 承载所有状态”的模型。
4. 所有外发内容统一经过 `ReviewPackage → ReviewRecord → Communication` 门禁。
5. Codex 是唯一 AI 执行核心；确定性状态、权限、重试、排序硬规则和发送动作由本地服务负责。
