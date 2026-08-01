## 用户问题

<!-- 本次改动解决什么具体的法务工作问题？ -->

## 改动范围

- [ ] Web页面与交互
- [ ] Python API/Application/Domain
- [ ] PostgreSQL模型或Alembic迁移
- [ ] 飞书/Codex/知识库集成
- [ ] 审核、权限、审计或敏感数据
- [ ] Docker/运行可靠性
- [ ] 测试与文档

## 领域与架构影响

<!-- 涉及哪些对象、不变量、状态机、Agent协议或审核门禁？ -->

## 数据库迁移

<!-- 是否有Alembic迁移？升级、回滚、数据回填和锁表风险是什么？ -->

## 幂等、并发与失败处理

<!-- Idempotency-Key、version冲突、重试、Outbox、死信或发送结果未知如何处理？ -->

## AI、权限与数据影响

<!-- Codex可访问什么？是否新增文件、字段、权限或外部发送？ -->

## 验证结果

```text
npm run typecheck
npm run build
python -m ruff check apps/backend/src apps/backend/tests
python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
python -m pytest apps/backend/tests
docker compose config
```

## 界面/API证据

<!-- 截图、录屏、OpenAPI示例或“不适用”。 -->

## 未覆盖范围与回滚

<!-- 明确后续任务和回滚方式。 -->
