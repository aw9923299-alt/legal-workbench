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

## 阶段0：工程基础（已完成）

已完成：

- 前端迁入`apps/web`；
- Python后端骨架；
- FastAPI健康检查；
- SQLAlchemy、Alembic和Celery配置；
- PostgreSQL 18 + Redis Compose（pgvector 为可选扩展）；
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

已完成补充：

- FeishuMessage原始事件和消息表；
- Deadline、Dependency及事项状态聚合；
- Outbox发布Worker、显式 Handler 注册、指数退避和死信处理。

尚未完成：真实高并发压力测试。

验收：空库可升级；重复请求不重复建单；version冲突返回409；Outbox与业务写入原子提交。

## 阶段2：候选确认API与前端（核心闭环已完成）

已完成：

- Candidate创建、列表、详情和`confirm-create`；
- CI真实PostgreSQL迁移和HTTP端到端集成测试；
- Matter列表、详情及WorkItem列表/新增；
- 创建事项和新增WorkItem的幂等门禁。

已完成补充：

- 一条Candidate生成多个WorkItem；
- 优先级和完成时间确认；
- 前端 API 查询层与消息研判相关加载/错误/重试状态。
- 统一 `resolve` API 支持关联、登记更新、仅供知悉和忽略，所有动作保留人工身份、幂等和审计；
- React Router + TanStack Query 的 AI 收件箱、消息详情、AgentRun 列表/详情和系统状态页；
- SSE 五类事件、断线退避和有限轮询回退；
- Candidate 分析版本对比、人工创建/关联 Matter 和死信恢复操作。

部分实现：`update_existing` 当前登记 Candidate 与既有 Matter 的更新关系，不直接修改事项字段；与本闭环无关的旧页面仍可能保留演示数据。

验收：刷新可恢复；人工确认值不被自动覆盖；端到端测试覆盖主流程。

## 阶段3：审核和发送门禁（部分完成）

已实现：

- DraftArtifact、ReviewPackage、ReviewRecord、Communication；
- 审核包页面；
- 批准版本锁定；
- 模拟发送服务、Outbox和结果未知状态。

验收：缺少审核、版本不一致或事项状态变化时拒绝发送。

占位/未完成：通用 DraftArtifact 已建模；实际飞书外发仍禁用。

## 阶段4：飞书受控接入（代码完成，真实凭证待验证）

范围：机器人私聊、指定群@消息、手动转发、已有事项线程。

已实现：官方 SDK 长连接和 Webhook 双入口、真实模式 fail-closed、有上限断线退避、持久化连接状态、事件/消息事务幂等、原始载荷哈希、富文本/线程/回复标准化、编辑/撤回版本、附件元数据/受控下载、群聊时间窗补偿与审计、Outbox 自动分析。

已通过模拟验证：断线重试与优雅退出、标准化、版本表/附件表、配置 fail-closed、迁移升降级和 PostgreSQL 主链路。

后续增量：迁移 `20260803_0008` 已增加附件文档版本、隔离正文提取、片段、总磁盘配额和人工正文授权；真实飞书测试消息、官方长连接/远端补偿仍按用户要求后置，加密 Webhook 尚未实现。

## 阶段4.5：Candidate 到 Matter 更新建议（本轮已完成）

迁移 `20260803_0009` 已增加 `matter_update_proposals` 及 Matter 人工确认优先级、目标期限和下一步行动。`update_existing` 不再通过通用 resolve 接口登记后结束，而是生成待审 Proposal；审核页稳定展示当前值、消息提取值、AI 建议值和法务最终值。批准/部分批准使用 Proposal + Matter 双版本校验，并将字段、Deadline、WorkItem、审计、Outbox 和幂等记录一次提交。PostgreSQL 集成测试已覆盖实际持久化；Matter 版本冲突时不会修改 Proposal 或 Matter。

## 阶段5：Codex Runtime与消息研判 Agent（本轮已完成）

已实现：

- AgentDefinition/AgentRun/AgentRunSource/DraftArtifact 模型与版本；
- 独立运行目录、无工具白名单、受控来源与 Schema/业务校验；
- ContextSnapshot v2 确定性选取、版本/排序复用键、多维限界、附件片段引用与 `message_judgement@2.1.0`；
- Codex CLI 版本/隔离认证健康检查、Prompt 注入边界和一次 Schema 修复重试；
- AgentRun 心跳、租约、只追加状态历史、超时、尝试、错误分类、指数退避和死信；
- Candidate revision 历史及 Redis/Worker 丢失后的 PostgreSQL 定时恢复；
- 收件箱、消息详情、AgentRun 运行中心、系统状态及人工处理闭环。

已通过模拟验证：11 类消息 Fake Runtime + PostgreSQL 冒烟、Prompt 注入、截断、输出修复、Candidate revision、队列/租约/死信恢复和 0006 迁移往返。

尚未验证/实现：当前宿主 CLI 版本与容器固定版本不一致，隔离 Worker 无 API Key，因此真实 Codex 推理未执行；事项归并、任务规划、优先级建议和结果汇总 Agent 不在本轮范围。

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
