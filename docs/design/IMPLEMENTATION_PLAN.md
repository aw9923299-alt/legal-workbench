# 实施计划与开发顺序

## 1. 原则

- 先固定领域模型、审核门禁和 Agent 协议，再扩展页面和 Agent；
- 先完成一条合同审核垂直闭环，再复制到其他专业领域；
- 前端逐步从当前 Mock 原型迁移，不进行无业务价值的一次性目录重写；
- 每个阶段必须可运行、可测试、可演示并可回滚。

## 2. 目标仓库结构

建议演进为 TypeScript monorepo：

```text
legal-workbench/
├─ apps/
│  ├─ web/                 React + TypeScript + Ant Design
│  ├─ api/                 Fastify/NestJS application service
│  ├─ codex-runner/        Codex execution sandbox
│  └─ watchdog/            health and local notifications
├─ packages/
│  ├─ domain/              entities, state machines, policies
│  ├─ contracts/           OpenAPI/Zod/JSON Schema
│  ├─ agent-sdk/           AgentDefinition and runtime protocol
│  ├─ feishu-adapter/      Feishu mapping and client
│  ├─ knowledge/           indexing and hybrid search
│  └─ test-fixtures/       desensitized fixtures
├─ agents/                 versioned Agent configs and prompts
├─ infra/                  Docker Compose and scripts
├─ docs/
└─ package.json
```

初期可保留现有 `src/`，在完成 P1 后再移动到 `apps/web`。

## 3. 阶段 0：设计基线与工程健康

### 交付

- 本目录设计文档；
- README、AGENTS、架构和路线图同步；
- 明确当前原型与目标能力差距；
- CI 继续执行前端 typecheck/build。

### 验收

- 文档不存在多模型、万能管家、单一 Task 状态等冲突；
- 新开发任务可映射到明确领域对象和接口。

## 4. 阶段 1：前端本地领域闭环

### 目标

不接真实飞书和 Codex，先使用本地 Mock API 验证模型和审核交互。

### 开发内容

1. 引入 React Router；
2. 将页面直接导入 Mock 改为应用服务；
3. 增加以下领域类型：
   - MessageCandidate；
   - LegalMatter；
   - WorkItem；
   - ReviewPackage；
   - ReviewRecord；
   - Communication；
4. 实现消息候选确认：
   - 新建事项；
   - 关联事项；
   - 更新事项；
   - 补充材料；
   - 仅供知悉；
   - 忽略；
5. 实现优先级/完成时间确认弹窗；
6. 实现事项详情和 WorkItem 状态；
7. 实现审核包页面和修改后通过；
8. 使用 IndexedDB 或 Mock Server 保持刷新后状态。

### 验收

- 一条消息可创建多个 WorkItem；
- 多条消息可关联同一事项；
- 人工确认值不会被重新分析覆盖；
- 没有 ReviewRecord 不能生成“已发送”状态；
- 核心状态机具备单元和组件测试。

## 5. 阶段 2：后端、数据库和 Docker 基础

### 开发内容

- 建立 monorepo 和 API；
- PostgreSQL migration；
- Redis 队列和 Outbox；
- Qdrant 服务；
- Docker Compose；
- healthcheck、日志轮转、备份脚本；
- OpenAPI 和前端客户端；
- SSE 状态更新；
- AuditEvent 和乐观锁。

### 验收

- `docker compose up -d` 可启动全部基础服务；
- 容器异常退出后自动恢复；
- 数据在重启后保留；
- 重复 API 请求不产生重复事项或发送；
- 数据库备份和恢复脚本通过演练。

## 6. 阶段 3：飞书受控接入

### 范围

- 机器人私聊；
- 指定群聊 @消息；
- 法务手动转发消息；
- 测试群全量消息（可选）。

### 开发内容

- 飞书应用授权；
- 长连接或事件订阅；
- 事件幂等落库；
- 消息、线程和附件解析；
- 群/私聊策略配置；
- 断线重连和补偿同步；
- 回复发送和回执；
- 权限撤销、消息编辑和撤回处理。

### 验收

- 同一事件重复到达不会重复创建候选；
- Mac 网络中断恢复后可补偿；
- 附件版本和哈希可追溯；
- 发送结果不确定时不会重复发送；
- 未授权会话不入库。

## 7. 阶段 4：Codex Runtime 与核心 Agent

### 开发内容

- `codex-runner`；
- AgentDefinition 注册；
- 每次运行独立工作目录；
- 输入/输出 Schema 校验；
- 工具和目录权限；
- 消息研判、事项归并、任务规划、优先级建议 Agent；
- 结果汇总 Agent；
- 重试、死信和运行日志；
- 工作台人工确认节点。

### 验收

- Agent 无法访问未授权文件；
- 非法输出不会进入领域对象；
- 高/紧急或模糊期限会触发人工确认；
- 事项关联显示依据并可拒绝；
- 多事项消息可拆分；
- AgentRun 可重放并保持幂等。

## 8. 阶段 5：本地知识库

### 开发内容

- 指定目录监听；
- PDF/Word/文本等解析；
- 版本和哈希；
- 元数据编辑和审批；
- PostgreSQL 全文 + Qdrant 向量混合检索；
- 正式制度、模板、历史事项、审核样例分域；
- 生效/失效和删除同步；
- 引用跳转和检索审计。

### 验收

- 失效文件不作为正式依据；
- 不同公司主体资料不会交叉误用；
- 删除文件后全文和向量索引均失效；
- 每个 Agent 结论可定位到资料位置；
- 工作草稿默认不能作为正式规则来源。

## 9. 阶段 6：合同审核垂直闭环

### 完整链路

```text
飞书合同请求
→ MessageCandidate
→ LegalMatter + WorkItem
→ Priority confirmation
→ Contract Agent plan
→ Knowledge Search
→ Contract Agent
→ Result Synthesizer
→ Reply Agent
→ ReviewPackage
→ Legal review
→ Feishu send
→ LearningRecord
→ Daily report
```

### 合同 Agent 输出

- 合同基本信息；
- 主体、期限、金额和交付；
- 付款和验收；
- 知识产权；
- 保密和数据；
- 违约和解除；
- 争议解决；
- 缺失条款；
- 风险清单；
- 修改建议；
- 待业务确认问题；
- 回复业务草稿输入。

### 验收

- Agent 分析绑定明确文件版本；
- 关键结论有引用；
- 缺少合同或主体不明时停止并请求补充；
- 法务可查看完整审核包和修改原因；
- 发送正文只能来自批准版本；
- 审核差异进入 LearningRecord；
- 日报显示真实结构化数据。

## 10. 阶段 7：学习和评测

### 开发内容

- 审核差异结构化；
- 法律内容和表达风格分离；
- 审核样例检索；
- RuleCandidate 审批；
- 固定评测集；
- Agent 版本试运行、激活和回滚；
- 质量仪表盘。

### 验收

- 单次特例不会自动形成全局规则；
- 规则启用前必须评测；
- 重大内容修改与轻微表达修改分开统计；
- 新 Agent 版本可回滚；
- 高风险遗漏有明确门槛。

## 11. 阶段 8：扩展专业 Agent

按以下顺序建议：

1. 文案 Agent；
2. 人力 Agent；
3. 纠纷 Agent；
4. 知产 Agent。

每个 Agent 必须：

- 注册 Definition；
- 提供 Schema；
- 提供测试集；
- 定义停止条件；
- 通过试运行；
- 复用审核包和发送门禁。

## 12. 推荐的近期开发任务

### 任务 1：重构前端领域类型

- 新增 `MessageCandidate/LegalMatter/WorkItem/ReviewPackage`；
- 保留当前 Task 作为过渡 ViewModel；
- 页面不直接导入 Mock；
- 补充状态机测试。

### 任务 2：实现候选消息确认和优先级弹窗

- 创建/关联/更新/忽略；
- 优先级建议理由；
- 完成时间确认；
- 人工覆盖记录。

### 任务 3：实现审核包 UI

- 背景、事实、依据、理由、风险、草稿；
- 修改后通过；
- 版本哈希和模拟发送门禁。

完成这三项后，再开始后端和 Docker 基础，不建议先继续新增更多展示页面。
