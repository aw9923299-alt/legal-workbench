# 真实飞书到 Matter 可运营闭环设计

**日期：** 2026-08-03
**状态：** 已获用户批准
**目标分支：** `agent/real-feishu-codex-operational-loop`
**基线：** `origin/main@56d4af4`

## 1. 目标与边界

本轮把现有演示性闭环完善为单台 Mac 上可长期运行、可人工控制、可审计和可恢复的工作系统：

```text
真实飞书测试消息
→ 官方长连接接收
→ PostgreSQL 幂等落库
→ 授权附件下载与正文提取
→ 限界 ContextSnapshot
→ 受控真实 Codex 研判
→ MessageCandidate
→ 法务人工确认
→ 创建 LegalMatter 或提交 MatterUpdateProposal
→ 创建和管理 WorkItem
→ 今日工作台持续跟踪
```

本轮不新增专业 Agent，不实现 OCR、外部 Embedding、向量数据库、自动飞书回复或自动创建正式 Matter。个人飞书客户端、个人账号已读状态和个人全部私聊始终不在系统权限范围内。

## 2. 设计原则

1. PostgreSQL 是业务事实、配置元数据、审计、队列恢复依据和查询投影的唯一权威存储。
2. Redis 仅作为 Celery Broker 和临时协调；清空 Redis 后由 PostgreSQL 恢复未完成任务。
3. Codex 是唯一推理和生成 AI；确定性 Python 服务负责状态、权限、期限、幂等、租约和恢复。
4. 外部调用不占用数据库事务。飞书验证、附件下载、正文解析和 Codex 推理均采用准备事务、外部执行、结果事务。
5. Agent 只产生建议和 Candidate，不直接修改 Matter、WorkItem 或正式外发记录。
6. 所有浏览器写操作从后端 Session 解析 Actor，并携带 Idempotency-Key、Correlation ID 和版本条件。
7. 所有外部输入都视为不可信数据。消息或附件中的指令不能扩大工具、文件、网络或数据库权限。
8. 真实凭证缺失时允许完成代码、Fake 集成和显式联调脚本，但文档和界面必须显示未执行或受阻。

## 3. 交付策略

采用单一分支和单一 Draft PR，按纵向闭环分阶段提交：

1. 本地配置与集成向导；
2. 飞书授权范围和真实连接控制；
3. Codex 版本、认证、冒烟与 Attempt fencing；
4. 附件下载、解析、片段和引用；
5. Candidate、MatterUpdateProposal 和 WorkItem 生命周期；
6. 今日工作台、评测和 Mac 常驻可靠性。

每个阶段都包含迁移、回滚、自动测试、文档和独立提交。阶段之间只通过明确的数据模型、应用端口和 API 契约连接。

## 4. 首次配置与凭证边界

### 4.1 持久化模型

新增：

```text
system_settings
integration_credentials
integration_scopes
integration_check_runs
```

`system_settings` 保存非敏感全局配置，包括飞书事件源、单聊策略、群聊@策略、指定群全量策略、附件上限、磁盘配额、Codex 期望版本和服务期望状态。每行保存 `key`、类型化 `value`、版本、修改人和修改时间。

`integration_credentials` 只保存：

```text
provider
credential_kind
secret_ref
configured
masked_hint
last_validated_at
last_validation_status
last_error_code
version
```

实际 Feishu App Secret 和 Codex 认证内容不写 PostgreSQL。Secret 保存在 Git 忽略的本地专用目录中，目录权限 `0700`、文件权限 `0600`。API 永不返回 Secret，只返回 `configured`、掩码和最近验证结果。Secret 目录不挂载进 Codex 运行目录。

`integration_scopes` 保存每个群聊的 `chat_id`、可显示名称、授权状态、同步模式、最近消息时间、最近错误和最后补偿结果。未知群首次出现时状态为 `unapproved`。

`integration_check_runs` 以只追加方式保存验证/冒烟的请求、状态、错误码、Correlation ID、开始和结束时间，不保存 Secret 或完整测试正文。

### 4.2 SecretProvider

`application` 依赖 `SecretProvider` 端口；`infrastructure` 实现本地 Secret 文件适配器。写入采用临时文件、`fsync` 和原子替换，确保进程崩溃不会留下半写文件。日志只能输出 Secret 类型和配置状态。

`POST /setup/feishu/validate` 接受 App ID 和可选的新 App Secret。提供新 Secret 时，API 仅在内存中完成凭证/权限验证，验证成功后才通过 `SecretProvider` 原子保存；验证失败不覆盖既有 Secret。未提供 Secret 时使用已经配置的 `secret_ref` 重新验证。App ID 作为非敏感设置保存，响应只返回掩码。

Codex Secret 目录只挂载给 Worker。API 的 Codex 验证与冒烟请求写入 PostgreSQL/Outbox，由 Worker 执行并持久化脱敏结果。Web、API 响应、PostgreSQL、Redis、飞书连接器和 Agent 输入均不获得 Codex 认证内容。

### 4.3 Setup API

实现：

```http
GET  /api/v1/setup/status
POST /api/v1/setup/feishu/validate
POST /api/v1/setup/feishu/start
POST /api/v1/setup/feishu/stop
POST /api/v1/setup/codex/validate
POST /api/v1/setup/codex/smoke-test
```

`start/stop` 修改 PostgreSQL 中的期望连接状态；常驻连接器观察状态并连接或断开，不让 API 直接操作 Docker。耗时验证返回 `202` 和 `checkRunId`，前端通过 `/setup/status` 或检查详情轮询。

状态码统一覆盖：

```text
not_configured
invalid_credentials
permission_missing
connected
disconnected
cli_missing
version_mismatch
unauthenticated
authenticated
runtime_unreachable
ready
```

每个失败同时返回稳定错误码、中文可读说明和 Correlation ID。

### 4.4 Setup 页面

`/setup` 使用九步向导：基础服务、飞书凭证、飞书权限、群聊范围、长连接、Codex 版本、Codex 认证、测试消息、完成状态。刷新后完全从后端恢复状态，不在浏览器持久化 Secret。

## 5. 飞书接入与授权策略

### 5.1 支持范围

只支持：

- 机器人单聊；
- 群聊中 @机器人 的消息；
- 人工授权测试群的全部消息。

不读取个人账号全部私聊，不模拟个人登录，不打开 Mac 飞书会话，不调用个人已读接口。

### 5.2 ScopePolicy

新增确定性 `FeishuScopePolicy`，在完整正文持久化和附件下载前作出：

```text
accept_bot_dm
accept_group_mention
accept_allowed_group_all
reject_excluded
reject_paused
reject_unapproved
reject_unsupported_scope
```

未知或敏感群默认 `unapproved`。系统只保存群聊标识、事件 ID、载荷哈希、时间和拒绝原因，不保存正文、附件或完整原始载荷。已允许消息才进入标准消息、版本、附件和分析 Outbox。

### 5.3 数据与幂等

保留并完善：

```text
event_id
message_id
tenant_key
chat_id
chat_type
thread_id
root_message_id
parent_message_id
sender
message_type
current_version
raw_payload
received_at
edited_at
recalled_at
```

事件唯一约束使用 `(tenant_key, event_id)`；消息唯一约束使用 `(tenant_key, message_id)`。编辑和撤回追加不可变 MessageVersion。同一消息的重复事件不创建重复 Outbox、附件版本或 Candidate。

### 5.4 群聊授权页面

`/settings/feishu-scopes` 支持查看已知群聊、允许、排除、暂停、恢复、最近消息、最近错误和手动补偿。所有变更使用乐观锁、审计和幂等键。

页面使用以下 API：

```http
GET  /api/v1/settings/feishu-scopes
PATCH /api/v1/settings/feishu-scopes/:scopeId
POST /api/v1/settings/feishu-scopes/:scopeId/reconcile
```

补偿同步只查询明确允许的群聊和时间窗。飞书接口不能保证租户级全量补拉时，结果必须标记 `partial`，列出不可覆盖窗口。

### 5.5 人工未读验收

新增人工验收记录：测试账号 A 发送消息、工作台收到、用户 B 不打开会话、A 侧确认 B 仍显示未读。系统只展示 `pending/manual_passed/manual_failed`，不得自动写成成功。

## 6. Codex Runtime 与迟到 Worker 防护

### 6.1 单一版本来源

新增唯一 `CODEX_CLI_VERSION=0.146.0-alpha.9.2`。Compose 将该值同时传入 Worker 镜像构建参数和运行环境；Settings、健康检查、文档和冒烟脚本读取同一值。Dockerfile 不维护第二个版本默认值。

仓库提供宿主 CLI 的 `--check` 与显式 `--install` 脚本，两者都读取同一变量。启动自检同时核对宿主和 Worker 镜像版本；两者任一不一致即显示 `version_mismatch`。正式 Runtime 仍只在 Worker 执行，宿主登录态不会被自动复制进容器。

版本不一致时健康状态为 `version_mismatch`，正式 AgentRun 在创建外部进程前失败关闭。

### 6.2 Worker 独占认证

Codex 认证目录或 API Key 只提供给 Worker。健康状态明确区分：

```text
cli_missing
version_mismatch
unauthenticated
authenticated
runtime_unreachable
ready
```

健康检查不得把“CLI 已安装”当成“可执行真实推理”。stdout/stderr、诊断包和运行目录继续执行凭证脱敏。

### 6.3 Attempt fencing

新增 `agent_run_attempts`：

```text
id
run_id
attempt_number
lease_token
lease_expires_at
worker_id
status
started_at
heartbeat_at
finished_at
failure_code
created_at
```

`(run_id, attempt_number)` 唯一。每次重试生成新的随机 `lease_token`。心跳、成功和失败提交必须同时匹配：

```text
run_id
attempt_number
lease_token
当前 Attempt 状态
```

Repository 使用条件更新并检查受影响行数。匹配失败返回 `STALE_AGENT_ATTEMPT`，只追加审计，不修改 AgentRun、Candidate 或 Message。恢复任务令旧 Attempt 过期后创建新 Attempt，迟到 Worker 因 token 不匹配无法覆盖。

### 6.4 真实冒烟

真实冒烟使用固定非敏感样例，覆盖合同审核请求、劳动咨询、知识产权、闲聊、仅供知悉、事项更新、明确期限、模糊期限、Prompt 注入、超长消息和附件消息。保存 AgentRun、Definition/Runtime 版本、时间、耗时、Attempt、Schema 结果、Candidate 和失败码。

普通 CI 只使用 Fake Runtime。真实冒烟需要显式环境开关和已配置 Worker 认证。

## 7. 附件下载、正文提取和引用

### 7.1 数据模型

将现有附件表演进为 `message_attachments`，并新增：

```text
document_versions
document_extractions
document_segments
storage_reservations
```

附件至少保存文件名、MIME、大小、SHA-256、本地路径、下载/提取状态、Extractor 版本、页数、字符数、错误码和时间。DocumentSegment 保存页码、段落号、起止偏移、正文和内容哈希。

迁移必须保留现有 `feishu_attachments` 数据；降级时恢复原表名和兼容字段。

### 7.2 格式与状态

首批支持：

- 文本型 PDF；
- DOCX；
- TXT；
- Markdown。

图片和没有可提取文本的扫描 PDF 保留元数据并标记 `body_unavailable`，页面显示“正文暂不可解析”。本轮不调用 OCR。

### 7.3 安全执行

- 路径必须 `resolve()` 后仍位于附件根目录；
- 文件名只作为显示和安全化目标名，不参与目录选择；
- 单文件大小、租户/全局配额在下载前预留并在失败后释放；
- 下载和解析均有独立超时；
- 解析在独立低权限子进程执行，父进程只传单个授权路径和输出上限；
- DOCX 只读取 ZIP/XML 正文，不运行宏；
- PDF 库只提取页面文本，不执行 JavaScript、附件或启动动作；
- Codex 只接收选中的片段 JSON，不读取附件目录。

### 7.4 ContextSnapshot 与引用

Snapshot 新增：

```text
included_segments
excluded_segments
truncated
truncation_reason
```

片段按当前附件、页码、段落稳定排序，并受片段数、单片段字符和总字符限制。每条附件事实引用必须包含：

```text
attachment_id
file_name
page_number
paragraph_number
content_hash
```

业务校验确认引用片段属于当前 Snapshot 且哈希一致；无效引用导致 Agent 输出失败，不创建或更新 Candidate。

## 8. Candidate 到 Matter 的人工闭环

### 8.1 Candidate 操作

保留创建新 Matter、关联已有 Matter、仅供知悉、忽略和重新分析。重新分析创建新 AgentRun/Attempt 并追加 CandidateRevision，不覆盖历史。

`update_existing` 改为创建 `MatterUpdateProposal`，不直接写 Matter。

### 8.2 MatterUpdateProposal

字段：

```text
id
candidate_id
matter_id
base_matter_version
proposed_changes
reason
status
created_by
reviewed_by
created_at
reviewed_at
version
```

状态：`pending/approved/partially_approved/rejected/superseded`。允许建议标题、分类、优先级、截止时间、负责人、当前状态、下一步行动和新增 WorkItem。

Proposal 的 `proposed_changes` 保存消息提取值和 AI 建议值；审核请求保存法务最终值和逐字段决定。页面按字段展示当前值、消息提取值、AI 建议值和法务最终值。

批准事务同时校验 Proposal 版本和 `base_matter_version`。Matter 已变化时返回 `409 ENTITY_VERSION_CONFLICT`，Proposal 保持待处理，不能静默覆盖。部分批准只应用明确选择的字段；新增 WorkItem、审计和 Outbox 在同一事务提交。

## 9. WorkItem 领域状态机

WorkItem 增加 `paused` 状态和领域方法：

```text
start
pause
wait
block
resume
complete
cancel
reopen
change_owner
change_deadline
change_next_action
add_dependency
resolve_dependency
```

规则：

- `start`：`todo/paused → in_progress`；
- `pause`：`in_progress → paused`，必须记录原因；
- `wait`：进入 `waiting` 时必须创建或引用开放依赖；
- `block`：必须记录 blocker 和责任人；
- `resume`：`paused/waiting/blocked → in_progress`，等待/阻塞原因同步关闭或清除；
- `complete`：存在开放依赖时拒绝；
- `cancel`：任何未完成状态可取消并记录原因；
- `reopen`：`done/cancelled → todo`，必须记录原因；
- 所有字段修改和状态迁移必须校验版本并追加审计。

API 只能调用应用用例，不能直接赋值状态字符串。

对应写接口均要求 `If-Match`、Idempotency-Key、认证 Actor 和 Correlation ID：

```http
POST  /api/v1/work-items/:id/start
POST  /api/v1/work-items/:id/pause
POST  /api/v1/work-items/:id/wait
POST  /api/v1/work-items/:id/block
POST  /api/v1/work-items/:id/resume
POST  /api/v1/work-items/:id/complete
POST  /api/v1/work-items/:id/cancel
POST  /api/v1/work-items/:id/reopen
PATCH /api/v1/work-items/:id/owner
PATCH /api/v1/work-items/:id/deadline
PATCH /api/v1/work-items/:id/next-action
POST  /api/v1/work-items/:id/dependencies
POST  /api/v1/work-items/:id/dependencies/:dependencyId/resolve
```

## 10. 今日工作台

首页改为 PostgreSQL 查询投影，展示：

```text
今日必须处理
已逾期
待确认 Candidate
分析失败
等待他人
即将到期
待审核外发
系统异常
```

每个条目返回对象类型、对象 ID、标题、原因、排序事实和可跳转 URL。排序键固定为：硬期限、逾期、风险等级、人工确认优先级、等待时长、创建时间。Codex 建议单独展示，不能覆盖人工值。

删除 Dashboard 对 `data/mock.ts` 和 Mock adapters 的运行时依赖。与本轮无关而尚未实现的页面显示明确“尚未实现”状态，不使用看似真实的业务数据。

## 11. AI 质量评估

采用 PostgreSQL 运行记录加版本化非敏感 Fixtures：

```text
evaluation_cases
evaluation_runs
evaluation_results
```

评估 legal_relevance、category、deadline、message_role、facts、inferences、missing_information 和 schema_compliance，并汇总准确率、误报率、一次 Schema 通过率、耗时、失败率和重试率。

人工确认和修改可以形成反馈记录，但不会自动训练、自动改 Prompt 或自动发布 AgentDefinition。

## 12. Mac 常驻、备份与恢复

### 12.1 launchd

提供可安装的 launchd 模板和脚本，负责登录后启动 Compose、周期健康检查、睡眠唤醒后的自检和每日 PostgreSQL 逻辑备份。Worker 并发保持 1。

唤醒恢复顺序：

```text
Docker 可用性
→ PostgreSQL/Redis/API/Worker/Scheduler
→ 飞书重连
→ 授权群时间窗补偿
→ PostgreSQL AnalysisRecovery
→ 过期 Attempt fencing
→ 磁盘/备份状态
```

### 12.2 运维能力

- PostgreSQL 每日备份、保留周期和最近成功时间；
- Redis 清空后从 PostgreSQL 恢复 Outbox、queued Run 和过期 Attempt；
- Codex 运行目录按状态和保留期清理；
- 附件总磁盘配额和低空间告警；
- JSON 日志滚动；
- 脱敏诊断包；
- 一键安全停止：先停止接收，等待短事务结束，再停止 Worker 和 Compose。

系统状态页展示 API、PostgreSQL、Redis、Worker、Scheduler、飞书连接、Codex认证、Codex版本、磁盘、最近备份、最近消息、最近成功 AgentRun、待恢复任务和死信数量。

## 13. 错误处理与可观测性

所有 API 错误采用统一结构：

```json
{
  "error": {
    "code": "STABLE_ERROR_CODE",
    "message": "可读说明",
    "details": {},
    "correlationId": "..."
  }
}
```

技术日志记录 Correlation ID、对象 ID、状态和错误码，不记录完整敏感正文、Secret 或未脱敏 Codex 输出。外部错误在适配层转换为内部稳定错误码。未知异常不向前端暴露堆栈。

## 14. 测试与验收

### 14.1 自动测试

覆盖：凭证失败、权限不足、allowlist、重复消息、编辑、撤回、线程、路径穿越、大文件、磁盘配额、下载/解析超时、附件引用、Codex 版本/认证、Fake Runtime、迟到 Worker、Matter 版本冲突、WorkItem 状态机、Redis 恢复和睡眠恢复逻辑。

每个新行为遵循 Red-Green-Refactor：先写会因能力缺失而失败的测试，再写最小实现，并在阶段结束运行受影响测试和全量回归。

### 14.2 真实联调

真实联调脚本必须显式启用，并输出结构化、脱敏报告。存在凭证时执行飞书测试群到 WorkItem 的完整链路；凭证缺失时报告 `not_executed` 和阻塞项，不把 Fake 或数据库测试写成真实通过。

个人已读状态验收永远是人工步骤。

### 14.3 完成验证

最终执行：

```bash
npm run typecheck
npm run test --workspace @legal-workbench/web -- --run
npm run build
python -m ruff check apps/backend/src apps/backend/tests
python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
python -m pytest apps/backend/tests
```

并完成迁移 `upgrade → downgrade → upgrade`、Compose 构建/健康、Redis 清空恢复、过期 Attempt、附件解析、诊断包、备份和安全停止验证。GitHub Actions 全部成功后才把 Draft PR 标记为具备完整自动化验收证据。

## 15. 明确不在本轮范围

- 合同、人力、知识产权等专业 Agent；
- OCR 或扫描件识别；
- 外部 Embedding、Qdrant 或其他模型；
- 自动飞书回复或自动外发；
- 自动创建或自动修改正式 Matter；
- 个人飞书客户端自动化和个人已读状态操作；
- 生产级多用户身份提供方；
- 与本闭环无关的大规模前后端重构。

## 16. 成功判定

只有当初始化、配置状态、授权接入、附件解析、真实或明确受阻的 Codex、Candidate 人工闭环、Matter 提案审批、WorkItem 生命周期、真实数据首页、Redis/租约恢复、Mac 自检、迁移往返、完整 CI、推送分支和 Draft PR 均有对应证据时，才宣称本轮完成。任何未执行的真实飞书、真实 Codex 或人工未读验收必须单独列为未完成内容。
