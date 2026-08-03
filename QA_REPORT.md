# QA Report

更新日期：2026-08-03

## 本轮范围

验证主闭环：

```text
FeishuEvent → FeishuMessage → 附件下载/正文提取
→ Celery Worker → ContextSnapshot → AgentRun
→ CodexCliRuntime/FakeAgentRuntime → MessageCandidate → 人工确认
```

同时覆盖未知 Outbox 事件、前端重试幂等键、认证边界和真实飞书配置 fail-closed。

## 阶段一增量结果：飞书本地消息接入

- **已实现**：官方 `lark-oapi` SDK 长连接和现有 Webhook 共用 `IngestFeishuEventHandler`；长连接支持启动、SDK 心跳、内部重连、外层 `1/2/4/8/16/30` 秒退避和优雅退出；
- **已实现**：`integration_connections`、`feishu_message_versions`、`feishu_attachments` 及迁移 `20260801_0005`；连接错误、事件时间、重连次数和补偿结果不再只存在内存；
- **已实现**：text/post/file/image、回复、线程、编辑、撤回和 unsupported 标准化；unsupported 可见但不写分析 Outbox；
- **阶段一当时已实现**：附件受控下载、大小上限、权限化路径、SHA-256 和默认 `authorized_for_analysis=false`；正文解析由阶段五补齐，OCR仍不实现；
- **已实现**：`GET status`、`POST reconnect`、`POST reconcile`；写接口要求后端认证 Actor、Idempotency-Key、Correlation ID 并写审计；
- **已通过模拟验证**：15 个飞书新增针对性测试，长连接失败两次后按 1/2 秒退避并在成功时保持连接；全量后端测试 76 passed、2 skipped；
- **已通过真实 PostgreSQL 验证**：临时数据库从空库升级到 `20260801_0005`，执行 `downgrade -1 → upgrade head` 成功；两条数据库集成测试 `2 passed`；
- **尚未真实集成验证**：当前环境未提供飞书 App ID/Secret、租户和授权群聊，未连接真实飞书。远端补偿是配置群聊的时间窗查询，不承诺租户全量零遗漏；加密 Webhook 仍拒绝。

## 已实现并验证

- `message_judgement` 输出使用 Pydantic 2 严格 Schema，禁止额外字段，置信度限制为 0–1；
- ContextSnapshot 定长、定序、SHA-256 去重且持久化；
- AgentRun 状态迁移、乐观锁、心跳、超时、尝试次数、失败码和 Correlation ID；
- Runtime 不在数据库长事务内执行；完成前后分两次短事务落库；
- 有效相关结果创建唯一活跃 Candidate；无关结果不创建；低置信度不跳过人工确认；
- Outbox 未注册事件会以 `UNSUPPORTED_OUTBOX_EVENT` 失败，按指数退避重试并死信；
- HttpOnly 会话解析 Actor；只有 `local/development` 签发本地 Session，非本地环境要求显式 Secret，Compose 端口仅绑定本机；
- `ENABLE_REAL_FEISHU=false` 时 Webhook 直接返回 503；启用时缺少 Verification Token 会在配置加载阶段失败，仅 Encrypt Key 也不能启动真实模式；
- 前端显示 Agent 版本、状态、理由、置信度、已确认事实、推断、期限候选和缺失信息；
- 一次前端业务操作在自动网络重试和用户再次点击间，通过 `sessionStorage` 复用同一 `Idempotency-Key`，直到明确响应、请求内容变化或用户取消。

## 阶段二增量结果：Codex 消息解析加固

- **已实现**：CLI 存在性、固定版本、隔离认证和运行目录可写检查，健康状态区分 `available/unauthenticated/version_mismatch/misconfigured/unreachable`，不把“已安装”当作可推理；
- **已实现**：ContextSnapshot v2 将当前/父/根/线程消息、参与者、附件元数据与授权片段、消息版本、Builder/选择策略版本、内容哈希和截断指标持久化，创建后不可修改；
- **已实现**：AgentRun 的 `queued → preparing → running → validating → completed/failed` 每次迁移追加状态事件，并记录 Worker、租约、Runtime/Agent/Prompt 版本、校验错误、修复次数和可用时的 Token 用量；
- **已实现**：飞书正文被标记为不可信业务证据；Prompt 明确禁止执行消息命令、Shell、环境变量读取、未授权文件读取、数据库修改、飞书回复和自动建 Matter；
- **已实现**：JSON、Pydantic 和业务规则失败后最多使用同一快照修复一次；第二次失败不创建 Candidate，禁止正则或手工拼接修 JSON；
- **已实现**：`candidate_revisions` 保存每次分析 Payload、Run、修订号和 superseded 关系；重新分析不再无痕覆盖；
- **已实现**：PostgreSQL 恢复服务扫描无活动 Run 的排队消息、陈旧 queued Run 和过期 preparing/running 租约，通过 Outbox 重派，耗尽后进入 `dead_letter`；
- **已通过模拟验证**：11 类消息 Fake Runtime 冒烟全部成功；闲聊、仅供知悉和 Prompt 注入不创建 Candidate，其他合法请求均完成严格校验；
- **已通过真实 PostgreSQL 验证**：迁移 `20260801_0005 → 0006 → 0005 → 0006` 成功；集成测试验证状态历史与 Candidate revision 均落库；
- **阶段二当时尚未真实集成验证**：当时宿主 CLI `0.146.0-alpha.9.2` 与配置 `0.145.0-alpha.9` 不匹配；该历史差异已由阶段四消除，但隔离 Worker 仍没有 Codex 认证，未发起真实模型推理请求。

## 数据库与运行时验证

- PostgreSQL 18 独立测试数据库上执行最新迁移往返，当前版本为 `20260803_0012 (head)`；
- 在 `20260801_0003` 插入两个历史重复 ContextSnapshot 和一个历史 Candidate 外部 Agent UUID 后执行升级/降级，快照没有被合并删除，历史 UUID 可完整恢复；
- PostgreSQL 集成测试验证 `FeishuMessage → ContextSnapshot → AgentRun → MessageCandidate`，结果为 `2 passed, 62 deselected`；
- Worker 镜像按唯一 `CODEX_CLI_VERSION=0.146.0` 构建成功，与当前宿主 `codex-cli 0.146.0` 精确一致；
- 镜像内已创建专用 `codex-agent` UID/GID 10001；
- Runtime 的完整 `--strict-config`、只读 sandbox、工具禁用和输出 Schema 参数通过当前 CLI 无联网参数解析检查；
- 普通单元测试使用 `FakeAgentRuntime`，不调用真实 Codex。
- Runtime 测试验证即使工具全部禁用，stdin 仍包含唯一授权消息内容；重分析测试验证待确认 Candidate 更新/作废语义。

## 阶段三增量结果：可运营工作台

- **已实现**：React Router 与 TanStack Query 接管 `/inbox`、消息详情、Candidate 跳转、AgentRun 列表/详情、系统状态和 Matter 路由；核心页面不读取 Mock 状态；
- **已实现**：AI 收件箱按待分析、排队、分析中、待确认、已处理、忽略、失败和死信分类，并支持正文、分类、时间和群聊筛选；
- **已实现**：消息详情左右分栏显示原文/线程/附件/编辑撤回历史，以及 Agent 状态、版本、建议、已确认事实、AI 推断、缺失信息和分析修订；人工可创建、关联、登记更新、仅供知悉、忽略或重新分析；
- **已实现**：Agent 运行中心显示状态历史、ContextSnapshot、实际来源、版本、租约、Worker、校验错误、受限输出和 Candidate，并提供取消与重试；
- **已实现**：系统状态页读取 FastAPI/PostgreSQL/Redis/Celery/Feishu/Codex/队列/死信真实健康值，危险恢复操作二次确认；Outbox 死信重入队增加 Actor、幂等、Correlation ID 和审计；
- **已实现**：SSE 区分 `system.health`、`message.ingested`、`agent-run.updated`、`candidate.created` 和 `outbox.failed`；连续失败后回退到 15 秒轮询；
- **已通过自动化验证**：前端测试覆盖收件箱状态映射、消息详情、事实与推断视觉分离、Agent 状态刷新、SSE 退避/轮询、幂等键复用、结构化错误和 Candidate 人工动作请求头；
- **部分实现**：SSE 当前使用数据库健康快照差异检测，不是 PostgreSQL LISTEN/NOTIFY；列表为上限分页而非游标分页；前端生产包仍有大 chunk 警告；
- **尚未真实集成验证**：因缺飞书凭证和隔离 Codex 认证，真实消息→真实模型→人工确认的现场演示未执行；Fake Runtime + PostgreSQL 闭环是本轮可重复验证基线。

## 阶段四增量结果：Codex 版本统一与 Attempt fencing

- **已实现**：部署只读取 `CODEX_CLI_VERSION`；Dockerfile 不再保留第二个默认版本，Compose 将同一值传给镜像构建和后端运行环境；2026-08-03 实测宿主与新构建 Worker 镜像均为 `codex-cli 0.146.0`；
- **已实现**：新增 `agent_run_attempts` 和迁移 `20260803_0007`，每个 Attempt 持久化 `attempt_number`、不可预测 `lease_token`、Worker、租约、心跳、终态和失败码，历史行不原地复用；
- **已实现**：心跳、成功和失败提交都必须同时匹配 `run_id + attempt_number + lease_token + running`；Candidate 创建只在同一事务内条件完成当前 Attempt 后发生；
- **已实现**：PostgreSQL 恢复先把过期 Attempt 标记为 `expired`，再通过 Outbox 重派；迟到 Worker 的成功结果返回 `STALE_AGENT_ATTEMPT`，不能覆盖新 Attempt 或创建 Candidate；
- **已通过自动化验证**：Attempt 领域、消息分析、租约恢复、Codex Runtime、SQLAlchemy 模型和真实 PostgreSQL fencing 共 38 个针对性测试通过；开启 PostgreSQL 集成后全量后端 104 个测试通过；Ruff 和 mypy 通过；
- **已通过真实 PostgreSQL 验证**：独立测试库从空库升级到 `20260803_0007`，执行 `0007 → 0006 → 0007` 成功；真实条件更新验证旧 token 被拒绝而新 Attempt 保持 `running`；
- **未执行**：按本轮用户指示，真实飞书测试消息和官方长连接验收后置；Worker 未提供 Codex 认证，未执行真实推理，不声称真实 Codex 冒烟通过。

## 阶段五增量结果：附件正文提取与可审计引用

- **已实现**：迁移 `20260803_0008` 原地保留并重命名附件表，新增 `document_versions`、`document_extractions`、`document_segments`、`storage_quota_reservations`，ContextSnapshot 持久化纳入/排除片段；
- **已实现**：文本型 PDF、DOCX、UTF-8 TXT 和 Markdown 提取；图片、扫描 PDF、宏文档和其他格式进入 `body_unavailable` 并在页面显示“正文暂不可解析”，不做 OCR；
- **已实现**：路径穿越/符号链接防护、文件名清理、单文件上限、PostgreSQL 总配额预约、私有原子写、解析超时、输出上限、DOCX 解压上限和无应用凭证子进程；不执行宏、PDF脚本或自动打开文件；
- **已实现**：附件下载和解析均不在外部工作期间持有数据库事务；解析 Outbox 重投对终态结果幂等，重复任务不重复写 Extraction/Segment；
- **已实现**：附件正文默认不授权给 Codex，人工授权接口写幂等与审计；ContextSnapshot 对片段数量、单段字符和总字符限界，并保存 `included_segments`、`excluded_segments` 和截断原因；
- **已实现**：`message_judgement@2.1.0` 的每条确认事实只能引用一条授权消息或一个精确附件片段；附件引用必须匹配附件 ID、文件名、页码、段落号和内容哈希，每个纳入片段另存真实哈希 `AgentRunSource`；前端引用可跳转到对应附件元数据，API 不返回本地路径；
- **已通过真实 PostgreSQL 验证**：专用测试库从空库升级到 `0008`，执行 `0008 → 0007 → 0008` 成功；实际保存 1 个文档版本、1 个幂等解析结果、2 个正文片段并构建含引用的 ContextSnapshot；
- **已通过自动化验证**：开启 PostgreSQL 集成后后端 `132 passed`；Ruff、mypy、Compose 配置、Worker 镜像重建、前端 typecheck/build 和 6 个测试文件共 11 个测试全部通过；镜像内 `pypdf`/`python-docx` 可导入且 Codex 仍为 `0.146.0`，Vite 仍只有已知大 chunk 警告；
- **未执行**：真实飞书测试消息和官方长连接继续按用户指示后置；隔离 Worker 未配置 Codex 认证，附件事实的真实 Codex 模型输出未执行，不以 Fake Runtime 或 Schema 测试冒充真实推理。

## 阶段六增量结果：Candidate 到 Matter 更新建议

- **已实现**：迁移 `20260803_0009` 增加 `matter_update_proposals`；Candidate 的 `update_existing` 必须创建待人工审核 Proposal，通用 resolve 接口不能把更新直接写入 Matter；
- **已实现**：后端从受控 Matter/Candidate 数据生成当前值、消息提取值和 AI 建议值，浏览器只选择字段；审核页逐字段填写法务最终值；
- **已实现**：Proposal 与 Matter 双版本乐观锁；批准/部分批准把 Matter 字段、新 WorkItem、规范化 Deadline、审计、Outbox 和幂等记录在同一事务提交，冲突时不静默覆盖；
- **已通过真实 PostgreSQL 验证**：实际创建 Proposal、人工批准标题/优先级/期限/WorkItem 并读取持久化结果，Matter 版本从 1 增至 2。

## 阶段七增量结果：WorkItem 全生命周期

- **已实现**：迁移 `20260803_0010` 增加 `paused`、暂停/取消原因和依赖解决人；全新数据库升级及 `0010 → 0009 → 0010` 往返通过；
- **已实现**：`start/pause/wait/block/resume/complete/cancel/reopen/change_owner/change_deadline/change_next_action/add_dependency/resolve_dependency` 全部进入领域层，禁止 API 直接改状态字符串；
- **已实现**：等待必须存在开放依赖，恢复等待项和完成前必须先解决依赖；状态切换原子清除不再生效的暂停/等待/阻塞字段；
- **已实现**：每次写操作校验 `If-Match`，WorkItem 与 Dependency 各自版本递增；业务记录、审计、Outbox 和幂等回放同事务提交；
- **已实现**：事项详情页提供全部合法状态、负责人、计划完成时间、下一步行动、建依赖和解决依赖操作，终态操作受限；
- **已通过真实 PostgreSQL 验证**：执行 `开始 → 建依赖 → 等待 → 解决依赖 → 恢复 → 完成`，最终 WorkItem 版本 7、Dependency 版本 2，并验证 6 条审计、6 条 Outbox 和完成动作唯一幂等记录；
- **已通过自动化验证**：默认后端 `160 passed, 7 skipped`，开启 PostgreSQL 集成后 `167 passed`；Ruff、mypy、前端 typecheck、6 个测试文件共 13 个测试和生产构建通过。Vite 仍只有已知大 chunk 警告。

## 阶段八增量结果：今日工作台真实队列

- **已实现**：`GET /api/v1/dashboard/today` 从 Candidate、最新失败 AgentRun/Message、开放 Matter/WorkItem、有效 Deadline、待审外发 ReviewPackage、Outbox 死信、持久化集成状态和实时健康快照生成八类队列；
- **已实现**：队列严格按硬期限、逾期、法律风险、人工确认优先级、等待时长、创建时间和稳定 ID 排序；AI 建议优先级只单独展示，不参与覆盖人工值；
- **已实现**：Deadline 查询只限定当前 Actor 相关 WorkItem/Matter，WorkItem 和 Matter 期限共同取最早值，避免无关全库期限挤占读取上限；健康探针异常返回脱敏系统异常项，不拖垮业务队列；
- **已实现**：React 根路由进入今日工作台，八类标签、真实计数、加载/空/失败/Correlation ID/重试、30 秒刷新和真实对象链接全部接入；待审外发链接可直接打开指定审核包；
- **已清理**：删除 `data/mock.ts`、`services/adapters.ts`、旧 `types/domain.ts` 及仅服务于原型的 AI 助手/任务表格/状态标签组件；运行代码未发现上述 Mock 引用；
- **已通过真实 PostgreSQL 验证**：独立 `legal_workbench_dashboard_test` 从空库升级到 `20260803_0010 (head)`，实际保存 Matter、WorkItem 及 Matter/WorkItem 两级 Deadline 后读取投影，验证硬期限合并、确定性排序、逾期分组和真实路由；
- **已通过自动化验证**：默认后端 `166 passed, 8 skipped`，开启 PostgreSQL 集成后 `174 passed`；Ruff、mypy、前端 typecheck、7 个测试文件共 16 个测试和生产构建通过。Vite 仍只有已知大 chunk 警告；
- **未执行**：真实飞书测试消息与官方长连接继续按用户指示后置；本阶段没有将本地 PostgreSQL 测试描述为真实飞书联调。

## 阶段九增量结果：Matter 审核与 WorkItem 操作界面

- **已实现**：Matter 更新建议页固定展示当前值、消息提取值、AI 建议值和法务最终值，逐字段显式批准/拒绝；拒绝字段不会把 AI 值当作正式值提交；
- **已实现**：审核请求使用稳定幂等上下文；后端返回 409 时刷新 Proposal 与当前 Matter、明确显示“未修改 Matter”，并保留法务逐字段决定和最终值草稿；
- **已实现**：WorkItem 控件按服务器状态派生可用操作，覆盖开始、暂停、等待、阻塞、恢复、完成、取消、重开、负责人、计划完成时间、下一步行动、建依赖和解决依赖；后端仍负责最终状态机和版本判断；
- **已实现**：成功操作刷新 Matter、WorkItem、Matter 列表和今日工作台；创建待审外发审核包后同步刷新今日队列；
- **已通过自动化验证**：前端 `10` 个测试文件、`24` 个测试全部通过，覆盖四类值分离、部分批准、加载/失败/Correlation ID/重试、全部 WorkItem 状态操作映射、权限禁用和 409 草稿保留；TypeScript 检查和生产构建通过，Vite 仍只有已知大 chunk 警告；
- **未执行**：真实飞书测试消息和官方长连接继续按用户指示后置；本阶段不改变其验收状态。

## 阶段十增量结果：消息研判质量评估

- **已实现**：迁移 `20260803_0011` 新增不可变版本化 `evaluation_cases`、`evaluation_runs`、`evaluation_results`；同一 Suite/Case/Version 内容变化会返回稳定冲突，不覆盖历史；
- **已实现**：11 类合成非敏感中文 Fixture 覆盖合同、劳动、知产、闲聊、仅供知悉、事项更新、明确期限、模糊期限、Prompt 注入、超长消息和附件，不含真实聊天、合同或个人数据；
- **已实现**：聚合法务相关性、分类、期限、消息角色、事实、事实引用、推断误报、缺失信息、无关消息误建 Candidate、Schema 首次通过、平均耗时、失败率和重试率；每个结果保留 AgentDefinition/Runtime 版本、输出、逐维分数和失败码；
- **已实现**：`POST /api/v1/evaluations/runs` 默认 Fake，认证 Actor、幂等键、Correlation ID 和审计均已接入；相同请求键不重复执行。真实运行必须同时满足 `allowRealRuntime=true` 和服务端真实 Codex 门禁；API 不实例化 Codex Runtime，真实认证只提供给专用 CLI Runner；
- **已通过真实 PostgreSQL 验证**：独立 `legal_workbench_evaluation_test` 从空库升级到 `20260803_0011 (head)`，执行 `0011 → 0010 → 0011` 成功；实际持久化 11 个 Case/Result、1 个 Run、2 条审计及全部聚合指标；
- **已通过自动化验证**：默认后端 `176 passed, 9 skipped`，开启 PostgreSQL 集成后 `185 passed`；Ruff 和 mypy 通过。Fake CLI 结果 11/11、`failureRate=0`、`realInferenceExecuted=false`；该满分只验证评估管线，不作为真实模型质量结论；
- **未执行**：隔离 Runner 未配置 Codex 认证，真实 Codex 评估未执行；真实飞书测试消息与官方长连接仍按用户指示后置。

## 阶段十一增量结果：首次配置与隔离检查向导

- **已实现**：迁移 `20260803_0012` 新增 `system_settings`、`integration_credentials`、`integration_scopes` 和只追加 `integration_check_runs`；专用测试库执行 `0012 → 0011 → 0012` 成功；
- **已实现**：本地 `SecretProvider` 使用目录 `0700`、文件 `0600`、`fsync` 和原子替换；数据库和 API 只保存/返回 `secret_ref`、配置标记和掩码，测试验证随机 Secret 未进入 PostgreSQL；
- **已实现**：六个 `/api/v1/setup/*` 接口和九步 `/setup` 页面；加载、失败、重试、精确状态、稳定错误码、可读说明和 Correlation ID 均可见，写入型 Secret 输入提交后立即清空；
- **已实现**：Codex 验证/真实冒烟请求与 Outbox 同事务写入，隔离 Worker 执行健康检查或合成非敏感推理后写回；API、Web、Redis、飞书连接器和 Agent 输入不获得 Codex 认证；
- **明确延后**：飞书 validate/start/stop 不保存新 Secret、不建立连接，统一返回 `not_executed / REAL_FEISHU_PHASE_DEFERRED`；测试消息、官方长连接和个人未读人工验收仍未执行，页面不会显示为成功；
- **已通过自动化验证**：默认后端 `187 passed, 10 skipped`，开启 PostgreSQL 集成后 `197 passed`；Setup 后端 11 个单元/API 测试和 1 个 PostgreSQL 测试通过，前端 Setup 3 个测试、typecheck 和生产构建通过；Ruff 与 mypy 通过。Vite 仍只有已知大 chunk 警告；
- **未执行**：当前 Worker 未提供 Codex 认证，真实 Codex Setup 冒烟只完成安全排队与实现，没有运行成功结果，不声称真实推理通过。

## 阶段十二增量结果：飞书群聊授权范围

- **已实现**：`GET/POST/PATCH /api/v1/settings/feishu-scopes` 和补偿记录接口；未知群只能以 `unapproved/disabled` 登记，允许 @机器人、允许指定群全部消息、排除、暂停和恢复全部由领域状态机执行；
- **已实现**：每次决定校验 `If-Match`、认证 Actor、幂等键与 Correlation ID，并把范围版本和追加审计写入同一 PostgreSQL 事务；旧版本返回 409，不能覆盖新人工决定；
- **已实现**：`/settings/feishu-scopes` 展示已知群、最近消息、最近同步错误、最近补偿、状态与版本，支持人工登记和全部范围操作；加载、空、失败、重试与精确错误证据均可见；
- **真实 PostgreSQL 已验证**：登记、允许全部消息、旧版本拒绝、延后补偿、范围版本和 3 条审计记录均实际持久化；
- **明确未执行**：补偿按钮只保存 `not_executed / REAL_FEISHU_PHASE_DEFERRED`，未调用飞书远端；真实测试消息和官方长连接继续按用户要求后置。

## 阶段十三增量结果：Mac 常驻运维与系统状态

- **已实现**：单一主机运维脚本提供安全启动/停止、睡眠唤醒自检、PostgreSQL custom dump 原子备份与保留期、Codex 运行目录安全清理、附件磁盘配额和脱敏诊断包；Worker 默认并发仍为 1；
- **已实现**：停止先写接入暂停标记，再停飞书连接器、等待活动事务、停止 Worker/Scheduler 和其余 Compose 服务；事务检查失败或未排空时失败关闭，不继续停库。唤醒只拉起基础服务，在 API/PostgreSQL/Redis/Worker/Scheduler/磁盘正常后调用 PostgreSQL 恢复接口，不启动延后的飞书连接；
- **已实现**：系统状态 API/页面显示磁盘、附件用量/配额、最近备份、最近唤醒和待恢复任务；待恢复口径不会把无飞书消息来源或仍持有有效未来租约的 Run 误报为可恢复任务；SSE 正常时不再额外每 10 秒扫描附件目录；
- **已实现**：Supervisor 登录后及每 5 分钟自检、每日 03:15 备份的 launchd 模板；运维 JSONL 日志按 5 MiB 滚动，全部 Compose 服务按 10 MiB × 3 文件轮转，launchd stdout/stderr 不单独无限增长；失败只输出错误类型，不回显异常正文；
- **本机已实测**：真实 PostgreSQL `pg_dump --format=custom` 已生成 177306 字节私有备份，`pg_restore --list` 识别为 PostgreSQL 18.4 custom archive；脱敏诊断包仅含 5 个状态文件、权限 `0600`，未包含 `.env` 或当前本地 Secret；新版镜像唤醒自检完成，基础组件、磁盘和备份正常，恢复计数为 0，因 Codex 未认证诚实标记为 `degraded`，自动恢复审计为 `mac-supervisor / local_supervisor`；
- **组件冒烟已通过**：真实 PostgreSQL、隔离 Redis DB 清空恢复、迟到 Worker fencing 和 11 类合成消息通过，报告 `verificationScope=component_integration`、`hostOperationalAcceptance=false`、`realInferenceExecuted=false`、`singleObjectEndToEnd=false`，并把脚本未执行的宿主运维步骤逐项标为 `not_executed`；
- **尚未人工安装/验收**：未改写用户 `~/Library/LaunchAgents`，真实 Mac 睡眠/唤醒和独立临时库恢复演练未执行；当前未跟踪 `.env` 尚缺 `CODEX_CLI_VERSION`，launchd 安装前必须补为 `0.146.0`；
- **明确未执行**：真实飞书测试消息和官方长连接继续为 `not_executed / REAL_FEISHU_PHASE_DEFERRED`；隔离 Worker 无 Codex 认证，真实 Codex 推理仍未执行。

## 最终验证命令

提交前以本节记录的最终结果为准。宿主 `.venv` 为 Python 3.14.6，生产镜像按项目基线使用 Python 3.12.13：

```bash
git diff --check
cd <repository-root>
.venv/bin/python -m compileall apps/backend/src
.venv/bin/python -m ruff check apps/backend/src apps/backend/tests scripts
.venv/bin/python -m mypy --config-file apps/backend/pyproject.toml \
  apps/backend/src scripts/legal_workbench_ops.py \
  scripts/smoke_test_codex_triage.py scripts/smoke_test_downstream_loop.py
.venv/bin/python -m pytest apps/backend/tests --disable-warnings
# 227 passed, 13 skipped（默认不启用 PostgreSQL/Redis 集成）

export LEGAL_WORKBENCH_TEST_DATABASE_URL="${LOCAL_TEST_DATABASE_URL}"
export LEGAL_WORKBENCH_TEST_REDIS_URL="redis://127.0.0.1:6379/15"
RUN_POSTGRES_INTEGRATION_TESTS=1 RUN_REDIS_INTEGRATION_TESTS=1 \
  .venv/bin/python -m pytest apps/backend/tests --disable-warnings
# 240 passed

.venv/bin/python scripts/smoke_test_codex_triage.py \
  --runtime fake --allow-database-write
# 11/11 success；realInferenceExecuted=false

.venv/bin/python scripts/smoke_test_downstream_loop.py \
  --runtime fake --allow-database-write --allow-redis-flush
# component_integration passed；11 cases；realInferenceExecuted=false
# hostOperationalAcceptance=false；飞书两项 not_executed

cd apps/web
npm install
npm run typecheck
npm run test
npm run build
# 13 test files / 31 tests passed；构建成功
cd ../..
CODEX_CLI_VERSION=0.146.0 docker compose config --quiet
CODEX_CLI_VERSION=0.146.0 docker compose build api worker scheduler web
CODEX_CLI_VERSION=0.146.0 .venv/bin/python scripts/legal_workbench_ops.py wake-check
CODEX_CLI_VERSION=0.146.0 .venv/bin/python scripts/legal_workbench_ops.py backup
CODEX_CLI_VERSION=0.146.0 .venv/bin/python scripts/legal_workbench_ops.py diagnostics
docker compose ps
# API/PostgreSQL/Redis/Worker/Scheduler/disk/backup normal
# Codex 0.146.0 exact match；authentication=unauthenticated；wake=degraded

LEGAL_WORKBENCH_DATABASE_URL="${LOCAL_TEST_DATABASE_URL}" \
  .venv/bin/python -m alembic -c apps/backend/alembic.ini upgrade head
LEGAL_WORKBENCH_DATABASE_URL="${LOCAL_TEST_DATABASE_URL}" \
  .venv/bin/python -m alembic -c apps/backend/alembic.ini downgrade -1
LEGAL_WORKBENCH_DATABASE_URL="${LOCAL_TEST_DATABASE_URL}" \
  .venv/bin/python -m alembic -c apps/backend/alembic.ini upgrade head
# 20260803_0012 (head)

cd ../..
docker compose run --rm --no-deps --entrypoint codex worker --version
# codex-cli 0.146.0
docker compose run --rm --no-deps --entrypoint id worker codex-agent
# uid=10001(codex-agent) gid=10001(codex-agent) groups=10001(codex-agent)
```

结果：截至 Mac 常驻运维阶段，`git diff --check`、Ruff、mypy、227 个默认后端测试（另 13 个 PostgreSQL/Redis 测试跳过）、240 个含 PostgreSQL 和隔离 Redis 清空恢复的后端测试、0012 迁移往返、前端 typecheck/13 文件 31 测试/build、Compose 静态配置、镜像构建、launchd plist 校验、真实主机备份/诊断/唤醒自检均通过。Vite 构建产生单个约 `1,477 kB`（gzip约 `462 kB`）chunk 警告，不影响构建成功。

`npm audit` 返回 `2 high`：两项均源自 React Router 的 RSC Action CSRF 公告 `GHSA-qwww-vcr4-c8h2`。当前 Registry 最新 `react-router-dom` 为 `7.18.2`，公告要求 `>=8.3.0`，暂无可安装修复版本；本项目是纯 Vite SPA，不启用 RSC/Server Actions，但该上游告警仍明确保留，未通过降级或强制安装掩盖。

## 故障注入与恢复

- **已通过隔离集成验证**：专用 loopback Redis DB 15 在确认空库后写入唯一临时投递标记并执行 `FLUSHDB`，标记消失但 PostgreSQL queued 消息仍存在；恢复服务重新生成持久 Outbox 事件。测试拒绝远端、带凭证、DB 0/1/14 和非空 DB 15，未清空当前业务 Broker；CI 另提供独立 Redis Service 执行同一清空恢复用例；
- **已通过模拟验证**：停止/恢复 Worker，系统状态由降级恢复正常；停止/恢复 API，HTTP 由不可达恢复 200；
- **已通过模拟验证**：终止无网络隔离容器中的实际 `codex exec` 进程，退出码为 137；AgentRun 租约超时、重派与死信路径由自动化测试覆盖。因缺真实认证，这不是一次真实模型运行中的故障；
- **已通过模拟验证**：飞书连接器在 `ENABLE_REAL_FEISHU=false` 时持久化为 `disabled`，人工重连返回 HTTP 409 `INVALID_STATE_TRANSITION`；长连接断线按 `1/2/4/8/16/30` 秒退避测试通过；
- **修复并回归**：故障演练发现 Celery Beat 任务复用了跨事件循环异步 Redis 客户端，已改为每次任务使用独立同步客户端并增加回归测试；系统页 Worker 探测阈值由 0.5 秒调整为 1 秒，减少单 Worker Mac 的瞬时误报。

## 页面可视化验证

浏览器基于 Compose 实例和真实 API 数据完成检查，控制台 `error/warning` 为 0：

![AI 收件箱](screenshots/ai-inbox.png)

![消息详情与人工确认](screenshots/message-detail.png)

![Agent 运行中心](screenshots/agent-run-center.png)

![系统状态](screenshots/system-health.png)

## 部分实现与未验证项

- 已完成真实 Codex CLI 二进制、版本、特性注册表及严格参数解析检查；当前环境未向容器提供 Codex 认证，因此未发起真实模型推理请求，也不声称真实模型调用通过；
- 宿主机模式依赖 Codex CLI 只读 sandbox 和工作目录约束，不是可证明的完整文件读取白名单；
- Agent 可控 Web/浏览器/MCP 工具已关闭，但模型传输仍需要服务端出网；当前 Compose 尚未配置目的地址 allowlist 或代理级 egress 限制；
- 飞书长连接、Verification Token Webhook 和配置群聊时间窗补偿代码已实现并通过模拟/数据库验证；真实凭证联调和加密 Webhook 尚未完成；
- 生产认证的外部登录/会话签发器尚未实现；本轮只建立可扩展的后端会话边界；
- Candidate 的“更新已有 Matter”已进入逐字段人工 Proposal 审核；尚未实现批量 Proposal 队列和更细的字段权限策略；
- SSE 当前基于 PostgreSQL 快照差异，不提供跨重启事件游标；前端路由包仍需做按页分包。
