# Codex 首轮开发指令

以下内容可直接作为 Codex 新任务的起始指令。

```text
你正在继续开发 GitHub 仓库 aw9923299-alt/legal-workbench。

项目名称：法务工作台。
项目定位：以飞书消息为入口、以 AI 管家为核心、以法务任务闭环为主线的企业级法务工作系统。它不是普通待办软件，也不能让 AI 在低置信度下直接创建正式任务或覆盖人工确认信息。

开始前必须阅读：
1. AGENTS.md
2. README.md
3. docs/CODEX_HANDOFF.md
4. docs/ARCHITECTURE.md
5. docs/DOMAIN_MODEL.md
6. docs/INTEGRATIONS.md
7. docs/ROADMAP.md
8. docs/TESTING.md

本轮目标：完成“AI 收件箱候选消息 → 人工修改提取结果 → 创建新任务或关联已有任务 → 记录来源与人工确认 → 任务状态流转 → 审计时间线”的本地可操作闭环。

约束：
- 暂不接入真实飞书、真实模型或生产数据库；
- 页面不得直接读取 src/data/mock.ts，应经过统一服务层；
- 使用 React Router 建立稳定页面 URL；
- 低置信度候选项不得跳过人工确认；
- 人工确认字段不得被 AI 静默覆盖；
- 状态迁移必须校验下一步行动、行动责任人、等待对象和提醒字段；
- 所有异步操作要有加载、成功、失败、空和无权限状态；
- 不提交密钥、真实聊天、合同或个人敏感数据。

建议实现：
- React Router；
- 一个可替换的本地 Mock 服务或 localStorage repository；
- 明确的 InboxCandidate、Task、SourceReference、AuditEvent 模型；
- 状态机和幂等创建逻辑；
- Vitest + Testing Library；
- 至少一条 Playwright 主流程测试（如本轮引入 Playwright 成本过高，可先建立配置并在 PR 中说明）。

验收标准：
1. 候选消息可编辑 AI 建议字段；
2. 可选择创建任务、关联任务、仅记录或忽略；
3. 同一候选消息重复提交不会重复创建任务；
4. 新任务保留来源消息、AI 判断、置信度、确认人和确认时间；
5. 任务状态迁移遵守 docs/DOMAIN_MODEL.md；
6. 所有操作进入审计时间线；
7. 刷新后本地演示数据仍可恢复；
8. npm run typecheck、npm run build 和新增测试通过；
9. 更新 README、相关文档和 Mock；
10. 提交一个 Draft PR，说明用户问题、架构选择、测试结果、权限影响和未覆盖范围。

请先检查当前代码和文档，输出简短实施计划，然后直接开发、验证并提交 Draft PR。不要进行无关的大规模目录重构。
```
