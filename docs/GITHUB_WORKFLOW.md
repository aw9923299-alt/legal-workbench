# GitHub 与 Codex 协作流程

## 1. 默认分支

- 默认分支：`main`；
- 功能分支：`feat/<scope>`；
- 修复分支：`fix/<scope>`；
- 文档分支：`docs/<scope>`。

## 2. 分支保护建议

仓库稳定后建议为 `main` 启用：

- 必须通过 `CI / frontend`；
- 必须通过 Pull Request 合并；
- 禁止 force push；
- 禁止删除默认分支；
- 至少一名人工审阅者批准高风险改动；
- 涉及飞书权限、外发、删除、Agent 写回或敏感字段时必须人工复核。

## 3. Codex 工作方式

每次只给 Codex 一个清晰迭代目标。任务中应包含：

- 具体用户问题；
- 领域规则；
- 不做什么；
- 验收标准；
- 需要运行的检查；
- 交付方式为 Draft PR。

首次任务可使用 `docs/CODEX_START_PROMPT.md`。

## 4. 推荐标签

- `enhancement`
- `bug`
- `documentation`
- `security`
- `permissions`
- `feishu`
- `ai-evaluation`
- `agent`
- `legal-domain`
- `needs-human-review`

## 5. 合并前检查

- CI 通过；
- PR 描述完整；
- 无真实敏感数据和密钥；
- AI/权限/审计影响已说明；
- 新增功能有测试；
- 页面有截图或录屏；
- 文档与代码行为一致；
- 高风险动作仍保留人工审批。
