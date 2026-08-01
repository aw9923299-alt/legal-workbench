# 法务工作台总体设计

## 1. 文档目的

本文定义可直接指导开发的正式系统设计。项目运行在本地Mac，以飞书消息为入口，以Codex为唯一推理和生成AI，以法务人工审核为最终控制点。前端采用React，后端采用Python模块化单体，PostgreSQL是唯一业务事实库。

## 2. 产品闭环

```text
发现工作 → 理解消息 → 形成候选 → 人工确认
→ 建立事项与行动任务 → 排序和规划 → 专业作业
→ 形成审核包 → 法务审核 → 对外回复
→ 跟踪后续 → 结案复盘 → 沉淀受控经验
```

首期受控消息来源：机器人私聊、指定群聊@消息、法务手动转发消息、已有事项线程后续消息。不得默认读取法务个人账号全部普通私聊。

## 3. 总体架构

```text
┌──────────────────────────────────────────────────────────────┐
│ apps/web                                                     │
│ React工作台：收件箱、事项、任务、审核、知识库、日报、系统状态 │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼───────────────────────────────────┐
│ apps/backend · FastAPI API                                  │
│ Auth · Request Validation · Query Models · Review Gate       │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│ Application Layer                                            │
│ Use Cases · Manager Orchestrator · Transaction · Outbox      │
└───────────────┬──────────────────────────────┬────────────────┘
                │                              │
┌───────────────▼──────────────┐  ┌────────────▼────────────────┐
│ Domain                       │  │ Agent Runtime                │
│ Matter · WorkItem · Review   │  │ Codex isolation · schemas   │
│ Deadline · Communication     │  │ tools · retries · artifacts │
└───────────────┬──────────────┘  └────────────┬────────────────┘
                │                              │
┌───────────────▼──────────────────────────────▼────────────────┐
│ Infrastructure / Integrations / Celery Workers                │
│ PostgreSQL · Redis · Feishu · File Indexer · Codex Runner     │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────┐
│ PostgreSQL 18 + pgvector · Redis · Local Encrypted Files      │
└──────────────────────────────────────────────────────────────┘
```

## 4. 模块化单体与进程角色

后端是一个Python代码库，但可运行为多个进程：

| 角色 | 职责 |
|---|---|
| API | HTTP、认证、用例、查询和SSE |
| Worker | Celery任务、重试、日报、提醒和Outbox消费 |
| Feishu Connector | 长连接、事件落库、附件下载、发送和回执 |
| File Indexer | 文件扫描、解析、版本和知识索引 |
| Codex Runner | Agent隔离执行、工具权限和输出校验 |
| Scheduler | 定时提醒、保留策略和健康检查 |

初期不拆独立微服务。只有在安全隔离、独立伸缩或发布节奏确有需求时，才基于现有边界拆分。

## 5. 管家拆分

用户只看到统一“法务管家”，内部由确定性`Manager Orchestrator`协调：

- 消息研判Agent；
- 事项归并Agent；
- 任务规划Agent；
- 优先级建议Agent；
- 结果汇总Agent；
- 日报与工作复盘Agent。

专业Agent包括合同、文案、人力、纠纷、知产、回复和学习Agent。

编排器负责允许的步骤、状态、事务、超时、重试、暂停和人工检查点；Agent只提供建议、分析和草稿。

## 6. 核心领域链路

```text
FeishuMessage
→ ContextSnapshot
→ MessageCandidate
→ LegalMatter
→ WorkItem
→ AgentExecutionPlan
→ AgentRun
→ DraftArtifact
→ ReviewPackage
→ ReviewRecord
→ Communication
```

关系约束：

- 一条消息可产生多个候选；
- 多条消息可关联一个事项；
- 一个事项包含多个WorkItem、Deadline、Dependency和AgentRun；
- Agent只产生DraftArtifact；
- Communication只能引用已批准且版本一致的草稿。

## 7. 消息接入流程

```text
飞书事件到达
→ 签名和授权校验
→ eventId/messageId幂等落库
→ 保存原始载荷哈希和受控正文
→ 下载授权附件并计算SHA-256
→ 创建ContextSnapshot任务
→ 消息研判Agent
→ MessageCandidate
```

Mac离线或断线后，连接器根据飞书能力执行补偿同步；无法补拉的时间窗必须在工作台明确显示。

## 8. 候选确认

MessageCandidate的最终处理动作：

- 创建新事项；
- 关联已有事项；
- 更新事项；
- 补充材料；
- 重新开启事项；
- 仅供知悉；
- 忽略；
- 需要补充信息。

低置信度、多事项、高风险、期限模糊或关联冲突必须由法务确认。

## 9. 优先级

```text
硬期限与逾期规则
+ 法律风险与业务影响规则
+ Codex软建议
+ 当前工作负荷
→ PriorityProposal
→ 法务确认或自动接受低风险建议
```

紧急/高、模糊完成时间、重大风险、老板直接要求或挤压现有高优任务时，工作台弹出确认。保存系统建议、人工决定和覆盖理由。

## 10. Agent执行

每个AgentRun绑定：

- Matter/WorkItem版本；
- ContextSnapshot；
- Agent和提示词版本；
- 允许的文件、知识域和工具；
- 输入输出Schema；
- 幂等键、超时、重试和租约。

Agent不得读取未授权目录、修改正式文件、发送消息或覆盖人工确认事实。

## 11. 审核和发送

ReviewPackage必须包括：

1. 原始需求和对话背景；
2. 已确认和未确认事实；
3. Agent结论、冲突和限制；
4. 依据和可定位引用；
5. 处理策略及为什么这样处理；
6. 风险和替代方案；
7. 发送对象、渠道和拟发送正文。

发送门禁：

```text
ReviewRecord.decision ∈ {approved, approved_with_edits}
AND approvedArtifactVersion == communicationArtifactVersion
AND currentMatterState still allows send
```

否则发送服务拒绝执行。发送结果未知时不得盲目重试。

## 12. 知识库

PostgreSQL负责元数据、正文、全文索引、`pg_trgm`和可选向量字段。首期不使用外部Embedding服务；Codex只在受控候选集合上进行选择和引用。

正式制度、模板、历史事项和审核样例分域管理。失效、草稿、其他主体和无权限资料不能作为正式依据。

## 13. 学习和复盘

审核差异分为：法律内容、事实、流程和表达风格。学习Agent输出审核样例、规则候选、知识缺口和Agent改进建议。规则必须经过法务批准、限定范围、回归评测和版本发布。

日报由系统先生成结构化事实底稿，再由Codex归纳；不得依赖长期会话记忆编造数据。

## 14. 安全与可靠性

- PostgreSQL事务、乐观锁、唯一幂等键和Outbox；
- Celery至少一次投递，消费者幂等；
- Docker健康检查和自动重启；
- `launchd`负责主机级拉起；
- 原始敏感数据和日志分离；
- 本地目录最小只读挂载；
- 数据备份、恢复演练和Legal Hold；
- API、数据库和Redis默认只暴露本机。
