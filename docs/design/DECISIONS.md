# 关键架构决策

## ADR-001：Codex是唯一推理和生成AI

**状态：已确认**

系统不引入其他LLM、Embedding API或云端AI服务。Codex Runtime统一控制提示词、工作目录、文件范围、工具、超时、重试、Schema和审计。业务代码不得散落调用Codex CLI。

## ADR-002：统一管家体验，内部职责拆分

**状态：已确认**

前端呈现统一法务管家；后端由确定性Manager Orchestrator协调消息研判、事项归并、任务规划、优先级建议、结果汇总和日报复盘Agent。Agent不直接改变正式状态或发送消息。

## ADR-003：核心领域对象分层

**状态：已确认**

```text
FeishuMessage → ContextSnapshot → MessageCandidate
→ LegalMatter → WorkItem → AgentExecutionPlan → AgentRun
→ DraftArtifact → ReviewPackage → ReviewRecord → Communication
```

不得使用单一Task承载全部生命周期。

## ADR-004：所有外发必须由法务审核

**状态：已确认**

业务回复、HR沟通、老板汇报、外部回复、催材料和发送给他人的提醒均需审核。发送服务必须验证审核决定、Artifact版本和当前事项状态。

## ADR-005：优先级采用规则、Codex建议和人工确认

**状态：已确认**

硬期限和逾期由规则计算；业务影响和真实紧急程度由Codex建议；高风险、低置信度、模糊期限或工作冲突由法务确认。

## ADR-006：后端采用Python模块化单体

**状态：已确认**

使用Python 3.12、FastAPI、Pydantic、SQLAlchemy 2、Psycopg 3和Alembic。一个代码库通过不同进程角色运行API、Worker、飞书连接、文件索引和Codex Runner。初期不拆微服务。

## ADR-007：PostgreSQL是唯一业务事实库

**状态：已确认**

PostgreSQL保存领域、审计、原始事件、知识元数据、正文、全文索引和可选向量。Redis只用于队列、锁、短期缓存和延时任务，不保存正式业务事实。

## ADR-008：使用PostgreSQL全文、pg_trgm和可选pgvector

**状态：已确认**

首期检索采用元数据过滤、全文检索、`pg_trgm`和Codex候选选择。不使用Qdrant。pgvector扩展启用，但向量字段允许为空；没有批准的本地向量生成方案时不启用向量召回。

## ADR-009：学习是受控记忆和规则审批

**状态：已确认**

学习Agent只生成样例、偏好、规则候选、知识缺口和改进建议。规则必须人工批准、限定范围、经过评测并可回滚。

## ADR-010：Docker Compose与launchd共同保证本地运行

**状态：已确认**

Docker负责依赖和容器；launchd负责主机拉起。Mac关机、深度休眠和Docker停止通过电源策略、断线重连、补偿同步、Outbox重放和健康告警治理。

## ADR-011：首个专业闭环为合同审核

**状态：已确认**

合同审核用于验证消息、事项、文件版本、知识检索、Agent协议、审核门禁、发送、学习和日报的完整链路。
