# 实施计划与开发顺序

## 原则

- Python后端采用模块化单体，不在首期拆微服务；
- PostgreSQL是唯一业务事实库；
- 先领域、迁移、审核门禁和Agent协议，再扩Agent；
- 先跑通合同审核垂直闭环；
- 每阶段必须可运行、可测试、可回滚。

## 目标结构

```text
legal-workbench/
├─ apps/
│  ├─ web/
│  └─ backend/
│     ├─ src/legal_workbench/{api,application,domain,agents,integrations,infrastructure,workers}
│     ├─ migrations/
│     └─ tests/
├─ data/{knowledge,codex-runs}/
├─ infra/{docker,launchd}/
├─ docs/design/
├─ compose.yml
└─ Makefile
```

## 阶段0：工程基础（当前）

已完成：

- 前端迁入`apps/web`；
- Python后端骨架；
- FastAPI健康检查；
- SQLAlchemy、Alembic和Celery配置；
- PostgreSQL 18 + pgvector + Redis Compose；
- 首个扩展迁移；
- Python/前端CI基线；
- 正式文档切换到Python和PostgreSQL。

验收：目录和配置可解析，Python源码可编译，Compose配置通过静态校验。

## 阶段1：领域持久化（首个切片已完成）

已完成：

- ContextSnapshot、MessageCandidate、LegalMatter、WorkItem；
- CandidateMatterLink、AuditEvent、OutboxEvent、IdempotencyRecord；
- SQLAlchemy模型、Repository、Unit of Work和首批Alembic迁移；
- `version`乐观锁、确认事务行锁和唯一幂等键；
- Candidate确认创建Matter并批量创建WorkItem的应用用例。

后续实现：

- FeishuMessage原始事件和消息表；
- Deadline、Dependency及事项状态聚合；
- 真实并发压力测试；
- Outbox发布Worker和死信处理。

验收：空库可升级；重复请求不重复建单；version冲突返回409；Outbox与业务写入原子提交。

## 阶段2：候选确认API与前端（创建事项路径已完成）

已完成：

- Candidate创建、列表、详情和`confirm-create`；
- CI真实PostgreSQL迁移和HTTP端到端集成测试；
- Matter列表、详情及WorkItem列表/新增；
- 创建事项和新增WorkItem的幂等门禁。

后续实现：

- 关联/更新/知悉/忽略；
- 一条Candidate生成多个WorkItem；
- 优先级和完成时间确认；
- 前端API查询层、Mock/Real切换和错误状态。

验收：刷新可恢复；人工确认值不被自动覆盖；端到端测试覆盖主流程。

## 阶段3：审核和发送门禁

实现：

- DraftArtifact、ReviewPackage、ReviewRecord、Communication；
- 审核包页面；
- 批准版本锁定；
- 模拟发送服务、Outbox和结果未知状态。

验收：缺少审核、版本不一致或事项状态变化时拒绝发送。

## 阶段4：飞书受控接入

范围：机器人私聊、指定群@消息、手动转发、已有事项线程。

实现事件签名、幂等落库、附件版本、撤回/编辑、断线重连和补偿同步。

## 阶段5：Codex Runtime与核心Agent

实现：

- AgentDefinition和版本目录；
- 独立运行目录、工具白名单和Schema校验；
- 消息研判、事项归并、任务规划、优先级建议、结果汇总；
- AgentRun租约、超时、重试和死信。

## 阶段6：知识库

实现：

- 文件目录扫描、哈希、版本和解析；
- 正式制度、模板、历史事项、审核样例分域；
- PostgreSQL全文、`pg_trgm`、元数据和权限过滤；
- 引用定位和检索审计；
- 可空pgvector字段和向量能力开关。

不引入外部Embedding服务。向量能力必须单独评审和评测。

## 阶段7：合同审核闭环

```text
飞书合同请求 → Candidate → Matter/WorkItem
→ 知识检索 → 合同Agent → 结果汇总 → 回复Agent
→ ReviewPackage → 法务审核 → 飞书发送
→ LearningRecord → 日报
```

关键验收：绑定明确合同版本、关键结论有引用、缺失材料时停止、发送只使用批准版本。

## 阶段8：学习、评测和日报

实现审核差异结构化、规则候选审批、固定评测集、Agent试运行/激活/回滚、日报事实底稿和复盘。

## 阶段9：其他专业Agent

建议顺序：文案、人力、纠纷、知产。每个Agent必须有Definition、Schema、停止条件、测试集、权限和质量门槛。
