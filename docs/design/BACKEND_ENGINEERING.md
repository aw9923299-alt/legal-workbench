# Python 后端工程设计

## 1. 目标

后端采用 Python 3.12 模块化单体，以一个代码库承载领域、应用、API、基础设施、飞书适配和Agent运行能力，再通过不同进程角色隔离运行负载。该方案比首期拆分微服务更容易保持事务一致性、降低本地部署复杂度，同时为未来拆分保留清晰边界。

## 2. 技术基线

- FastAPI：HTTP、OpenAPI和依赖注入边界；
- Pydantic v2：请求、响应、事件和Agent契约校验；
- SQLAlchemy 2：关系模型和事务；
- Psycopg 3：PostgreSQL驱动；
- Alembic：Schema迁移；
- Celery + Redis：长任务、重试和调度；
- structlog：结构化技术日志；
- pytest、Ruff、mypy：测试和静态质量。

## 3. 模块边界

```text
legal_workbench/
├─ api/              HTTP契约和认证
├─ application/      用例、事务、编排、权限和审核门禁
├─ domain/           实体、值对象、状态机、策略和不变量
├─ agents/           AgentDefinition、Codex Runtime、Schema校验
├─ integrations/     飞书、本地文件和外部适配器
├─ infrastructure/   SQLAlchemy、Redis、Celery、日志、加密
└─ workers/          异步任务入口
```

依赖方向：

```text
api/integrations/workers → application → domain
infrastructure → application/domain定义的端口
agents → application定义的Agent端口和domain快照
```

`domain`不得导入FastAPI、SQLAlchemy、Redis、Celery或飞书SDK。

## 4. 应用用例

每个写用例采用以下结构：

1. 校验操作者和权限；
2. 读取聚合并校验version；
3. 执行领域方法；
4. 保存聚合；
5. 写入AuditEvent；
6. 在同一事务写入OutboxEvent；
7. 提交事务；
8. 由Worker异步处理Outbox。

示例用例：

- `ConfirmMessageCandidate`；
- `CreateLegalMatter`；
- `AddWorkItem`；
- `ConfirmPriority`；
- `CreateReviewPackage`；
- `RecordReviewDecision`；
- `RequestCommunicationSend`。

## 5. 数据访问

Repository接口由`application`或`domain`定义，SQLAlchemy实现位于`infrastructure`。不得在FastAPI路由中直接执行ORM查询。

查询列表和工作台可以使用独立Query Service，以投影模型提高读取效率；写入仍经过领域用例。

## 6. 事务和并发

- PostgreSQL是唯一业务事实库；
- 聚合根使用整数`version`乐观锁；
- 幂等写入使用`idempotency_key`唯一约束；
- 外部发送请求与Outbox在同一事务；
- Celery任务至少一次投递，消费者必须幂等；
- 长Agent任务使用租约、心跳和超时，不持有数据库事务。

## 7. 错误模型

API统一返回：

```json
{
  "error": {
    "code": "ENTITY_VERSION_CONFLICT",
    "message": "The matter was changed by another operation.",
    "details": {},
    "correlationId": "..."
  }
}
```

领域错误映射为明确HTTP状态：

- 400：输入或状态迁移不合法；
- 401/403：认证或权限；
- 404：资源不存在或不可见；
- 409：幂等、version或状态冲突；
- 422：结构校验；
- 503：依赖服务不可用。

## 8. 进程角色

同一后端镜像通过不同命令运行：

- API：短请求和SSE；
- Worker：Celery任务；
- Feishu Connector：长连接、事件入库和发送回执；
- File Indexer：本地文件扫描、解析和索引；
- Codex Runner：隔离Codex执行；
- Scheduler：日报、提醒、重试和保留策略。

在这些角色达到独立伸缩或安全隔离需求前，不拆独立代码库。

## 9. 安全

- 服务端凭证只从环境变量或系统密钥管理加载；
- 原始载荷、合同正文和私聊不得写入普通日志；
- Codex Runner使用独立工作目录和最小只读挂载；
- 数据库账号按运行角色分权；
- API默认只监听本机；
- 所有外发经过ReviewRecord和版本一致性检查。

## 10. 依赖和锁定

`apps/backend/pyproject.toml`声明运行依赖和`dev` dependency group，`apps/backend/uv.lock`是唯一Python锁文件。开发与CI使用`uv sync --locked`，运行命令使用`uv run --locked`；生产镜像使用`uv sync --locked --no-dev --no-editable`，不得在构建期间改写锁文件。uv固定为`0.12.3`，Python仅支持`3.12.*`。任何依赖或工具链升级必须同步更新锁文件，并通过单独PR、迁移演练和回归测试。
