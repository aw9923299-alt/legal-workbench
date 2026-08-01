# 开发路线图

正式阶段和验收标准见 [`docs/design/IMPLEMENTATION_PLAN.md`](./design/IMPLEMENTATION_PLAN.md)。本文件提供快速优先级。

## P0：领域模型和前端审核闭环

- 引入 React Router 和统一应用服务；
- 新增 `MessageCandidate/LegalMatter/WorkItem/ReviewPackage/ReviewRecord/Communication`；
- 实现消息候选创建、关联、更新、知悉和忽略；
- 实现优先级/完成时间确认弹窗；
- 实现审核包 UI、修改后通过和模拟发送门禁；
- 增加状态机、版本冲突和重复操作测试。

## P1：后端与 Docker 基础

- TypeScript API/BFF；
- PostgreSQL、Redis、Qdrant；
- Outbox、队列、幂等和乐观锁；
- Docker Compose、healthcheck、日志轮转和备份；
- OpenAPI/SSE；
- AuditEvent。

## P2：飞书受控接入

- 机器人私聊；
- 指定群聊 @消息；
- 手动转发消息；
- 线程和附件；
- 断线重连、游标和补偿同步；
- 审核后发送和回执；
- 权限撤销、编辑和撤回。

## P3：Codex Runtime 和核心 Agent

- AgentDefinition 和统一协议；
- 独立工作目录、工具/目录权限和 JSON Schema；
- 消息研判、事项归并、任务规划、优先级建议；
- 结果汇总、日报和复盘；
- 重试、死信、冲突和人工确认。

## P4：本地知识库

- 指定目录监听；
- 文件版本和哈希；
- 正式资料审批和适用元数据；
- PostgreSQL 全文 + Qdrant 向量混合检索；
- 引用定位、删除同步和检索审计。

## P5：合同审核垂直闭环

```text
飞书合同请求
→ 候选确认
→ 事项/任务
→ 优先级确认
→ 检索
→ 合同 Agent
→ 结果汇总
→ 回复 Agent
→ 审核包
→ 法务审核
→ 飞书发送
→ 学习记录
→ 日报
```

## P6：学习、评测和 Agent 治理

- 法律修改与表达修改分离；
- 审核样例和规则候选；
- 固定评测集；
- Agent trial/active/rollback；
- 事实准确、风险遗漏、引用覆盖和重大修改率指标。

## P7：其他专业 Agent

按顺序接入：

1. 文案 Agent；
2. 人力 Agent；
3. 纠纷 Agent；
4. 知产 Agent。

## 当前建议开发任务

**标题：实现消息候选、事项、行动任务和审核包的前端本地闭环**

验收：

1. 消息不再直接等同于任务；
2. 可新建、关联、更新、知悉和忽略；
3. 可确认优先级和计划完成时间；
4. 一个事项可包含多个 WorkItem；
5. 外发草稿必须存在审核记录；
6. 重复提交不重复创建；
7. 单元、组件和端到端测试覆盖主路径。
