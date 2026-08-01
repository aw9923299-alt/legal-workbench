# Codex / Claude Code 首轮开发指令

以下内容可直接作为下一次开发任务的起始指令。

```text
你正在继续开发 GitHub 仓库 aw9923299-alt/legal-workbench。

项目名称：法务工作台。
当前状态：React 高保真前端原型 + 正式系统设计文档。

开始前必须阅读：
1. AGENTS.md
2. README.md
3. docs/design/README.md
4. docs/design/SYSTEM_DESIGN.md
5. docs/design/DATA_MODEL.md
6. docs/design/AGENT_PROTOCOL.md
7. docs/design/API_CONTRACTS.md
8. docs/design/IMPLEMENTATION_PLAN.md
9. docs/CODEX_HANDOFF.md
10. docs/TESTING.md

本轮目标：完成“消息候选 → 法务事项 → 行动任务 → 优先级确认 → 审核包 → 模拟外发”的前端本地闭环。

必须遵守：
- Codex 是唯一 AI 核心，但本轮不接真实 Codex；
- 暂不接真实飞书、公司资料、数据库或消息发送；
- 不继续扩展旧 Task 作为唯一领域对象；
- 新增 MessageCandidate、LegalMatter、WorkItem、ReviewPackage、ReviewRecord、Communication；
- 页面不得直接读取 src/data/mock.ts，应经过应用服务；
- 使用 React Router 建立稳定 URL；
- 消息支持新建事项、关联事项、更新事项、补充材料、仅供知悉和忽略；
- 优先级和完成时间在高风险、低置信度或模糊期限时要求人工确认；
- 所有模拟外发必须有 ReviewRecord，且批准版本和待发版本一致；
- 人工确认值不得被重新分析静默覆盖；
- 所有异步操作具备加载、空、失败、重试和无权限状态；
- 不提交密钥、真实聊天、合同或个人敏感数据。

建议实现：
- React Router；
- 应用服务 + localStorage/IndexedDB Mock repository；
- Zod 或明确的运行时校验；
- 领域状态机；
- 乐观锁/版本字段和幂等创建；
- Vitest + Testing Library；
- 至少一条端到端主流程测试。

验收标准：
1. 候选消息可查看依据、置信度和不确定点；
2. 可新建、关联、更新、知悉或忽略；
3. 一条消息可生成多个 WorkItem；
4. 同一候选重复提交不重复创建；
5. 优先级弹窗保存系统建议、人工决定和覆盖原因；
6. 事项详情展示 WorkItem、来源和独立状态；
7. 审核包展示背景、事实、依据、理由、风险和拟发送内容；
8. 没有审核记录时模拟发送服务拒绝；
9. 刷新后本地状态可恢复；
10. typecheck、build 和测试通过；
11. 更新相关文档和 Mock；
12. 提交 Draft PR，说明领域映射、测试、未覆盖范围和后续迁移。

不要进行无关的大规模目录重构。先输出简短实施计划，再直接开发、验证并提交 Draft PR。
```
