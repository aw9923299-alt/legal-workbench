# 测试与质量要求

## 测试分层

### Python单元测试

重点覆盖领域状态机、候选幂等确认、事项与任务不变量、优先级规则、人工覆盖、审核门禁、乐观锁、Outbox和知识过滤。

### Python集成测试

使用临时PostgreSQL/Redis环境验证：

- Alembic从空库升级；
- Repository和事务；
- 唯一幂等键；
- version冲突；
- Outbox发布和Celery重投；
- health/readiness；
- API错误码和OpenAPI契约。

### 前端组件测试

覆盖候选确认、优先级弹窗、事项详情、审核包、冲突、补充材料以及加载/空/失败/无权限状态。

### 端到端测试

```text
候选消息
→ 创建事项和两个WorkItem
→ 确认优先级
→ 生成测试 DraftArtifact
→ 审核包修改后通过
→ 模拟发送
→ 时间线和审计记录
```

## 必测异常

- 同一事件或API请求重复到达；
- 创建超时但服务端已成功；
- version冲突；
- 一条消息涉及多个事项；
- 已关闭事项重新开启；
- 文件版本替代和权限撤销；
- Codex超时、非法输出和越权；
- Agent结论冲突；
- 发送结果未知；
- 审核后事实变化；
- 失效制度进入候选；
- Mac断网、容器重启、队列重投和死信重放。

## Agent评测

检查事实准确率、关键问题覆盖、高风险遗漏、引用覆盖、无依据推断、过期资料、缺失信息识别、重大修改率和越权次数。不得只看执行成功率或文本编辑距离。

## 提交前命令

```bash
npm install
npm run typecheck
npm run build

python -m pip install -e 'apps/backend[dev]'
python -m ruff check apps/backend/src apps/backend/tests
python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
python -m pytest apps/backend/tests

docker compose config
```

Matter 更新建议的真实 PostgreSQL 映射可单独验证：

```bash
RUN_POSTGRES_INTEGRATION_TESTS=1 \
LEGAL_WORKBENCH_TEST_DATABASE_URL='postgresql+psycopg://.../legal_workbench_test' \
python -m pytest apps/backend/tests/test_postgres_matter_update_proposals.py -q
```

该测试覆盖 Candidate 生成待审 Proposal、人工批准字段、新增 WorkItem、Deadline、审计和版本持久化；不调用真实飞书或真实 Codex。

WorkItem 状态机与 PostgreSQL 事务可单独验证：

```bash
python -m pytest apps/backend/tests/test_work_item_lifecycle.py -q
RUN_POSTGRES_INTEGRATION_TESTS=1 \
LEGAL_WORKBENCH_TEST_DATABASE_URL='postgresql+psycopg://.../legal_workbench_test' \
python -m pytest apps/backend/tests/test_postgres_work_item_lifecycle.py -q
```

集成测试执行开始、建依赖、等待、解决依赖、恢复和完成，检查 WorkItem/Dependency 版本、审计、Outbox 与幂等回放。

今日工作台可单独验证：

```bash
.venv/bin/python -m pytest \
  apps/backend/tests/test_dashboard_queue.py \
  apps/backend/tests/test_postgres_dashboard_queue.py -q
npm run test --workspace @legal-workbench/web -- --run DashboardPage
```

PostgreSQL 投影集成测试需要显式设置 `RUN_POSTGRES_INTEGRATION_TESTS=1` 和独立测试数据库 URL。测试固定验证硬期限优先、风险/人工优先级/等待时间排序、AI 建议不覆盖排序、八类对象链接、健康探针脱敏降级、HTTP 契约及前端加载/空/失败/Correlation ID/重试状态。

Matter 更新审核与 WorkItem 操作页可单独验证：

```bash
npm run test --workspace @legal-workbench/web -- --run \
  MatterUpdateComparison WorkItemActions MatterUpdateProposalPage
```

组件测试覆盖四类值的视觉边界、逐字段部分批准、全部状态下的合法 WorkItem 操作，以及后端返回 409 时刷新当前 Matter 但保留法务决定和最终值草稿。后端仍是状态迁移和版本校验的唯一权威。

消息研判质量评估可单独验证：

```bash
.venv/bin/python -m pytest \
  apps/backend/tests/test_evaluations.py \
  apps/backend/tests/test_postgres_evaluations.py -q

.venv/bin/python scripts/run_message_judgement_evaluation.py \
  --database-url postgresql+psycopg://.../legal_workbench_evaluation_test \
  --runtime fake \
  --allow-database-write
```

默认 API 和 CLI 均使用合成非敏感 Fixture 与 Fake Runtime；CLI 输出必须显示 `realInferenceExecuted=false`。Fake 的满分只证明 Fixture、Schema、评分、持久化和聚合管线可重复，不代表真实模型质量。真实运行还必须同时设置服务端 `LEGAL_WORKBENCH_ENABLE_REAL_CODEX=true` 和 CLI `--allow-real-runtime`，且只在持有认证的专用 Runner 执行。API 进程不实例化 Codex Runtime。评估只记录结果和反馈，不自动训练或改 Prompt。

涉及数据库或Compose时还应执行：

```bash
docker compose up -d postgres redis
alembic -c apps/backend/alembic.ini upgrade head
curl http://localhost:8000/api/v1/health/live
```
