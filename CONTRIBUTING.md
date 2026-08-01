# 贡献指南

## 开发流程

1. 阅读 `AGENTS.md` 和相关 `docs/` 文档；
2. 从最新默认分支创建功能分支；
3. 以一个明确用户问题为提交范围；
4. 完成代码、测试、文档和 Mock 更新；
5. 运行类型检查和构建；
6. 在 PR 中说明权限、数据和 AI 行为变化。

## 分支建议

- `feat/<scope>`：新功能；
- `fix/<scope>`：缺陷修复；
- `docs/<scope>`：文档；
- `refactor/<scope>`：不改变业务行为的重构。

## Commit 建议

使用简洁的祈使语句，例如：

- `feat: add inbox confirmation flow`
- `fix: validate waiting fields on status change`
- `docs: add Codex handoff guide`

## PR 必填内容

- 用户问题与解决方案；
- 改动页面或接口；
- AI、权限和敏感数据影响；
- 验证命令与结果；
- 截图或录屏；
- 未覆盖范围和后续工作。

## 禁止提交

- `.env`、访问令牌和任何密钥；
- 真实聊天、合同、主播或员工敏感数据；
- `node_modules`、`dist` 和本地日志；
- 未说明来源和许可的第三方素材。
