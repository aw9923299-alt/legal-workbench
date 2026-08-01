# 领域模型概览

完整字段、状态机和不变量见 [`docs/design/DATA_MODEL.md`](./design/DATA_MODEL.md)。

## 1. 核心对象

```text
FeishuMessage       原始飞书消息
ContextSnapshot     Agent 使用的不可变上下文快照
MessageCandidate    待法务确认的消息处理建议
LegalMatter         完整法务事项
WorkItem            事项下的具体行动
Deadline            法定、平台、合同、业务和内部期限
Dependency          等待材料、回复、决策或审批
AgentExecutionPlan  Agent 执行计划
AgentRun             一次可审计 Codex 执行
DraftArtifact        Agent 产生的草稿交付物
ReviewPackage        法务审核材料包
ReviewRecord         不可变审核决定
Communication        审核后发送记录与飞书回执
KnowledgeDocument    公司资料及适用元数据
LearningRecord       审核差异和学习记录
RuleCandidate        待审批和评测的规则候选
```

## 2. 关键修正

- `Task` 不再是整个系统唯一聚合；
- `待确认` 属于 MessageCandidate，不属于正式事项的起始状态；
- `等待材料/等待业务/待审批/阻塞` 不再被压缩为单一互斥状态；
- 一个事项可以有多个 WorkItem、Deadline、Dependency 和 AgentRun；
- 一条消息可以关联多个事项，一个事项可以关联多条消息；
- Agent 只产生 DraftArtifact；所有外发必须经过 ReviewPackage 和 ReviewRecord。

## 3. 独立状态机

- MessageCandidate：分析、确认、关联、知悉、忽略；
- LegalMatter：开放、解决、关闭、重新开启、取消；
- WorkItem：待办、处理中、等待、阻塞、待审核、完成、取消；
- AgentRun：排队、运行、补充信息、冲突、成功、失败、死信；
- ReviewPackage：草稿、待审、通过、修改、驳回；
- Communication：待发、发送中、已发、结果未知、失败。

## 4. 人工优先

人工确认值不得被 Codex 静默覆盖。重要字段保存：

- 当前值；
- 来源；
- 状态；
- 置信度；
- 证据；
- 生成者/确认人；
- 时间和版本。

## 5. Python与PostgreSQL映射

- 领域对象使用普通Python类或dataclass表达，不依赖SQLAlchemy；
- Pydantic模型用于API、事件和Agent契约；
- SQLAlchemy模型只负责持久化映射；
- PostgreSQL枚举优先使用受控字符串和CHECK约束，避免频繁修改数据库ENUM；
- 聚合根使用`version`乐观锁；
- 审核、审计和事件采用追加式记录；
- 知识片段使用`tsvector`、`pg_trgm`和可空`vector`字段。
