# GitHub 与 Claude Code / Codex 协作流程

## 默认分支

- 默认分支：`main`；
- 开发分支：`feat/<scope>`、`fix/<scope>`、`docs/<scope>`或`agent/<scope>`。

## 分支保护

仓库稳定后为`main`启用：

- 必须通过`CI / frontend`、`CI / backend`和`CI / compose`；
- 必须通过Pull Request合并；
- 禁止force push和删除默认分支；
- 数据库迁移、飞书权限、外发、删除、Agent工具权限和敏感字段改动必须人工审阅。

## Agent开发任务

每次任务应包含：用户问题、领域对象、不变量、不做什么、迁移要求、验收、测试和Draft PR要求。首次实现任务使用`docs/CODEX_START_PROMPT.md`。

## 合并前检查

- 设计与代码一致；
- Alembic升级可执行且有回滚/前向修复策略；
- API和Agent契约已版本化；
- 幂等、并发、失败和审计已覆盖；
- 无真实敏感数据和密钥；
- 外发仍保留人工审核；
- CI全部通过。
