# 贡献指南

## 开发流程

1. 阅读`AGENTS.md`和相关`docs/design/`文档；
2. 从最新默认分支创建功能分支；
3. 以一个明确用户问题或领域切片为提交范围；
4. 同步代码、迁移、测试、文档和Mock；
5. 运行前端、Python和Compose检查；
6. 在PR中说明数据、权限、AI、迁移和回滚影响。

## 分支与Commit

推荐分支：`feat/<scope>`、`fix/<scope>`、`docs/<scope>`、`refactor/<scope>`。

示例Commit：

- `feat: add candidate confirmation API`
- `fix: enforce review artifact version`
- `docs: define knowledge retrieval policy`

## PR必填

- 用户问题与解决方案；
- 涉及的领域对象、API和数据库迁移；
- AI、权限和敏感数据影响；
- 幂等、并发、失败和回滚策略；
- 验证命令和结果；
- 前端截图或API示例；
- 未覆盖范围。

## 检查

```bash
npm run typecheck
npm run build
python -m ruff check apps/backend/src apps/backend/tests
python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
python -m pytest apps/backend/tests
docker compose config
```

## 禁止提交

- `.env`、访问令牌和密钥；
- 真实聊天、合同、主播或员工敏感数据；
- `node_modules`、`dist`、`.venv`、缓存和本地运行数据；
- 未说明来源和许可的第三方素材；
- 绕过Alembic的手工数据库修改。
