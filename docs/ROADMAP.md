# 开发路线图

正式阶段和验收标准见 [`docs/design/IMPLEMENTATION_PLAN.md`](./design/IMPLEMENTATION_PLAN.md)。

## P0：工程骨架（已完成）

- 前端迁入`apps/web`；
- Python 3.12 + FastAPI模块化单体；
- SQLAlchemy、Psycopg、Alembic；
- Celery + Redis；
- PostgreSQL 18 + pgvector Compose；
- 健康检查、首个迁移和CI基线。

## P1：领域持久化

- MessageCandidate、LegalMatter、WorkItem等SQLAlchemy模型；
- AuditEvent、OutboxEvent和IdempotencyRecord；
- Repository、用例、乐观锁和事务测试。

## P2：候选确认和前端API化

- Candidate确认动作；
- 事项关联和多个WorkItem；
- 优先级/完成时间确认；
- 前端查询层和Mock/Real切换；
- 组件与端到端测试。

## P3：审核包和外发门禁

- DraftArtifact、ReviewPackage、ReviewRecord、Communication；
- 批准版本锁定、模拟发送和结果未知状态。

## P4：飞书受控接入

- 机器人私聊、指定群@、手动转发、线程和附件；
- 幂等、撤回、编辑、断线补偿和回执。

## P5：Codex Runtime和核心Agent

- AgentDefinition和Schema；
- 独立工作目录和工具权限；
- 消息研判、事项归并、任务规划、优先级和结果汇总；
- 重试、死信和人工检查点。

## P6：本地知识库

- 文件哈希、版本、解析和审批；
- PostgreSQL全文、`pg_trgm`、元数据和权限；
- 可选pgvector能力；
- 引用定位、删除同步和检索审计。

## P7：合同审核闭环

完成从飞书合同请求到审核发送、学习记录和日报的端到端链路。

## P8：学习、评测和其他专业Agent

建立固定评测、Agent版本治理和规则候选，再依次接入文案、人力、纠纷和知产Agent。
