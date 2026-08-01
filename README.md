# 法务工作台

运行在本地 Mac 上的法务智能工作系统。系统通过飞书消息发现工作，由 Codex 核心 Agent 进行消息研判、事项归并、任务规划和优先级建议，再调用合同、文案、人力、纠纷、知产等专业 Agent 完成作业。所有向他人发送的内容必须由法务审核，并展示背景、依据、处理理由和风险。

> 当前仓库是 React 高保真前端原型和正式设计基线。真实飞书接入、Codex Runtime、数据库、Docker 部署和专业 Agent 尚未实现。

## 1. 核心闭环

```text
飞书消息
→ 消息研判与上下文聚合
→ MessageCandidate 人工确认
→ LegalMatter + WorkItem
→ 优先级/完成时间确认
→ AgentExecutionPlan
→ 专业 Agent 作业
→ ReviewPackage
→ 法务审核
→ 飞书发送与回执
→ 后续跟踪、学习、日报和复盘
```

## 2. 关键设计原则

1. **Codex 是唯一 AI 执行核心**：所有 Agent 通过受控 `Codex Runtime` 运行，不在页面或 Worker 中散落调用。
2. **统一管家体验，内部职责拆分**：确定性编排器协调消息研判、事项归并、任务规划、优先级建议、结果汇总和日报复盘 Agent。
3. **消息、事项、任务和产物分层**：不得使用单一 Task 承载全部生命周期。
4. **所有外发必须人工审核**：包括业务回复、HR 沟通、老板汇报、外部回复、材料催办和发送给他人的提醒。
5. **审核包必须解释原因**：背景、确认事实、未确认事实、依据、处理策略、风险、替代方案和待发送正文缺一不可。
6. **优先级不是纯 AI 判断**：硬期限和逾期由规则计算，软优先级由 Codex 建议，高风险或不确定事项由法务确认。
7. **知识库采用混合检索**：PostgreSQL 元数据/全文检索 + Qdrant 向量召回，严格过滤版本、生效状态、主体和权限。
8. **学习是受控记忆**：审核差异形成样例和规则候选，必须经法务批准和评测后启用。
9. **本地服务可恢复**：Docker Compose、`launchd`、幂等、重试、死信、补偿同步和备份共同保证稳定性。

## 3. Agent 体系

### 核心 Agent

- 消息研判 Agent；
- 事项归并 Agent；
- 任务规划 Agent；
- 优先级建议 Agent；
- 结果汇总 Agent；
- 日报与工作复盘 Agent。

### 专业 Agent

- 合同 Agent；
- 文案 Agent；
- 人力 Agent；
- 纠纷 Agent；
- 知产 Agent。

### 支持能力

- 检索能力/复杂检索 Agent；
- 回复 Agent；
- 学习 Agent。

## 4. 正式设计文档

从 [docs/design/README.md](./docs/design/README.md) 开始阅读：

- [总体系统设计](./docs/design/SYSTEM_DESIGN.md)
- [核心数据模型](./docs/design/DATA_MODEL.md)
- [统一 Agent 协议](./docs/design/AGENT_PROTOCOL.md)
- [API 与事件契约](./docs/design/API_CONTRACTS.md)
- [Docker 部署与可靠性](./docs/design/DEPLOYMENT.md)
- [实施计划](./docs/design/IMPLEMENTATION_PLAN.md)
- [关键架构决策](./docs/design/DECISIONS.md)

## 5. 当前实现

当前前端包含：

- 今日工作台；
- AI 收件箱；
- 任务中心；
- 任务详情；
- 法务事项库；
- Agent 中心；
- 数据与权限页面；
- 无依赖静态预览 `preview.html`。

当前限制：

- 页面使用 Mock 数据；
- `Task` 仍是过渡 ViewModel；
- 未使用 React Router；
- 无后端、数据库和持久化；
- 无真实飞书、Codex 和向量数据库；
- 页面操作大多为演示状态；
- 无自动化测试。

## 6. 当前技术栈

- React 18；
- TypeScript；
- Vite；
- Ant Design；
- Day.js。

目标后端与运行环境：

- TypeScript BFF/API；
- PostgreSQL；
- Redis；
- Qdrant；
- Docker Compose；
- 本地 Codex Runtime。

## 7. 本地运行前端原型

```bash
npm install
npm run dev
```

检查：

```bash
npm run typecheck
npm run build
```

Node.js 要求：20 或更高版本。

## 8. 推荐开发顺序

1. 重构领域类型：`MessageCandidate/LegalMatter/WorkItem/ReviewPackage`；
2. 实现候选消息确认、事项关联和优先级确认弹窗；
3. 实现审核包 UI 和模拟发送门禁；
4. 建立 TypeScript 后端、PostgreSQL、Redis、Qdrant 和 Docker Compose；
5. 接入飞书受控消息范围；
6. 实现 Codex Runtime 和核心 Agent；
7. 建设本地知识库；
8. 跑通合同审核端到端闭环；
9. 建立学习与评测；
10. 逐步接入其他专业 Agent。

详细验收标准见 [实施计划](./docs/design/IMPLEMENTATION_PLAN.md)。

<!-- bootstrap-pr-trigger-2 -->
