# Codex / Claude Code 项目交接说明

更新日期：2026-08-01

## 1. 当前阶段

仓库现有代码是 React 高保真原型，正式系统设计已落在 [`docs/design/`](./design/README.md)。下一阶段应先实现本地领域闭环，不应直接连接生产飞书或同时开发全部 Agent。

## 2. 已实现

| 模块 | 状态 |
|---|---|
| 今日工作台 | 静态/Mock 原型 |
| AI 收件箱 | 静态/Mock 原型 |
| 任务中心 | 列表原型，其他视图占位 |
| 任务详情 | 静态/Mock 原型 |
| 法务事项库 | 概念原型 |
| Agent 中心 | 概念原型 |
| 数据与权限 | 概念原型 |
| 正式设计文档 | 已完成 |

## 3. 尚未实现

- React Router 和统一请求层；
- MessageCandidate、LegalMatter、WorkItem 等正式模型；
- 状态机、审计、版本和幂等；
- 审核包和发送门禁；
- 后端、PostgreSQL、Redis、Qdrant；
- Docker Compose 和主机守护；
- 飞书真实接入；
- Codex Runtime；
- 核心/专业 Agent；
- 知识库、学习和评测；
- 自动化测试。

## 4. 关键技术债

1. `App.tsx` 使用本地 state 切换页面；
2. 页面直接导入 Mock；
3. `Task` 混合事项和行动任务；
4. Inbox 操作不持久化；
5. Agent 输出是字符串；
6. 无 ReviewPackage/ReviewRecord/Communication；
7. 无异常、重试、发送回执和版本冲突流程；
8. `preview.html` 与 React 源码独立；
9. 无 lockfile 和自动化测试。

## 5. 下一迭代

只实现以下前端本地闭环：

```text
Mock 飞书消息
→ MessageCandidate
→ 人工确认新建/关联/更新/知悉/忽略
→ LegalMatter + WorkItem
→ 优先级和完成时间确认
→ Mock Agent DraftArtifact
→ ReviewPackage
→ 修改后通过
→ 模拟 Communication
```

不得在此迭代接真实飞书、真实公司资料或自动发送。

## 6. 交付要求

- 先阅读 `docs/design/`；
- 使用正式对象，不继续扩展旧 Task 模型；
- 保留过渡 ViewModel 时明确映射关系；
- 为状态机、重复提交、优先级确认和审核门禁添加测试；
- PR 说明设计对应、数据影响、未覆盖范围和验证结果。
