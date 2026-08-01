# 系统架构设计

## 1. 架构目标

系统需要同时处理高频消息流、结构化任务、敏感文件、AI 推理和专业 Agent 执行。架构应优先保证：可追溯、最小授权、可替换、可回滚和人工可控。

## 2. 建议逻辑架构

```text
┌──────────────── Web Frontend ────────────────┐
│ 工作台 / 收件箱 / 任务 / Agent / 权限 / 审计 │
└──────────────────────┬───────────────────────┘
                       │ OpenAPI / SSE / WebSocket
┌──────────────────────▼───────────────────────┐
│ BFF / Application Service                    │
│ Auth · Task Use Cases · Inbox · Files · Audit│
└───────┬────────────────┬─────────────────────┘
        │                │
┌───────▼────────┐ ┌─────▼────────────────────┐
│ Domain Services│ │ Workflow / Event Workers  │
│ Task State     │ │ Sync · Reminder · Agent   │
│ Deduplication  │ │ Retry · Approval · Outbox │
│ Risk Policy    │ └───────────┬───────────────┘
└───────┬────────┘             │
        │              ┌───────▼──────────────┐
┌───────▼────────┐     │ External Adapters     │
│ PostgreSQL     │     │ Feishu / LLM / Agent  │
│ Redis / Queue  │     │ Storage / Notification│
│ Object Storage│     └────────────────────────┘
└────────────────┘
```

## 3. 前端分层

建议逐步迁移为：

```text
src/
├─ app/               路由、Provider、权限守卫、全局错误边界
├─ features/          inbox、tasks、agents、security 等业务特性
├─ entities/          task、message、agent、person、file
├─ shared/            UI、hooks、lib、api、config
├─ services/          适配器与应用服务接口
└─ mocks/             Mock handlers 与 fixtures
```

当前目录无需一次性重构。应按功能迭代逐步迁移，避免只为“目录漂亮”进行大范围无业务价值改动。

## 4. 关键领域服务

### Task Lifecycle Service

负责合法状态迁移、必填字段校验、提醒计划和审计事件。

### Message Classification Service

负责判断消息类型、抽取字段、输出证据与置信度。它只创建候选结果，不直接越过人工确认规则。

### Matter Linking Service

计算新消息与历史任务的关联候选。输出候选任务、分数和理由，由规则或人工确认是否合并。

### Agent Orchestrator

负责权限预检、输入快照、脱敏、Agent 调用、结构校验、审批、回写、成本和失败重试。

### Audit Service

记录操作主体、数据对象、前后值、来源、请求 ID、模型/Agent 版本和时间。审计记录只能追加，不能由普通业务接口覆盖。

## 5. 事件模型

建议使用领域事件解耦同步与后续动作：

- `FeishuMessageReceived`
- `InboxCandidateCreated`
- `InboxCandidateConfirmed`
- `TaskCreated`
- `TaskLinkedToMessage`
- `TaskStatusChanged`
- `TaskWaitingStarted`
- `TaskDeadlineApproaching`
- `TaskRiskEscalated`
- `AgentRunRequested`
- `AgentRunApprovalRequired`
- `AgentRunCompleted`
- `TaskClosed`

所有消费者需使用幂等键，避免飞书重试或队列重投导致重复任务、重复通知和重复回写。

## 6. 可观测性

至少记录：

- 飞书同步延迟、失败率、被权限拒绝比例；
- AI 识别数量、人工确认率、误判修正率、关联准确率；
- Agent 成功率、平均耗时、重试次数、人工拒绝率和成本；
- 任务逾期率、等待超时率、材料缺失率；
- 权限拒绝、敏感数据导出和高风险操作次数。

日志与指标只保存必要元数据，避免写入原始聊天全文和合同正文。
