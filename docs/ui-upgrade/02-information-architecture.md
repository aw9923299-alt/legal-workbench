# Legal Workbench 信息架构与产品设计裁决

更新时间：2026-08-04
输入：仓库、Playwright baseline、Figma MCP、`product_ui_designer` 与 `ux_information_architect` 两份独立报告

## 1. 裁决结论

系统应收敛为“安静的法务运营控制台”，而不是展示 AI 能力的 Dashboard。Inbox 的“来源证据 → 证据边界 → AI 提取/推断 → 缺失材料 → 人工决定”是现有最成熟范式，应扩展到其他页面。

本轮裁决顺序严格遵循：法务工作安全 → 实际任务效率 → 信息可扫描性 → 现有业务逻辑 → Ant Design/技术约束 → 无障碍 → 响应式 → 审美。

核心决策：

1. 只设计和实施当前真实页面与 API 能力；
2. 消除未经验证的在线、同步、连接、成功和配置状态；
3. 以真实 URL 路径和 query 恢复导航、刷新、返回和搜索上下文；
4. 移动端不缩小桌面表格，统一使用结构化记录卡；
5. 一页一个主动作；行动、风险、期限、负责人、等待对象和下一步优先于统计；
6. AI 建议、人工确认和确定性系统状态使用稳定的独立语义；
7. 没有后端支持的动作禁用并解释，不能伪造成功；
8. 保留现有 token 和 Ant Design，不引入 Material/Simple DS 或第二套 UI 框架。

## 2. 实际闭环与能力边界

当前能够由真实 API 表达的闭环：

```text
待确认消息
→ 核对原始消息、证据快照和 AI 提取
→ 人工编辑
→ 确认创建 LegalMatter + 首个 WorkItem
→ 确认优先级 / 添加期限 / 添加依赖
→ 创建 ReviewPackage
→ 人工审核
→ Communication 入队
```

当前不能伪装实现：

- 关联/更新已有事项、补充材料、仅作信息、忽略、暂缓、合并；
- WorkItem 开始、等待、阻塞、完成、取消状态迁移；
- Matter 解决、关闭、重开、归档；
- 专业合同/纠纷/知产 Agent；
- 真实合同与文件管理；
- 全局跨实体搜索；
- 真实飞书连接、同步和权限状态；
- Communication 实际发送和回执闭环。

页面流程必须在真实能力边界处停止，并明确后端缺口。

## 3. 导航与路径

### 工作

- 今日工作台：`/today`；
- 待确认消息：`/inbox`、`/inbox/:candidateId`；
- 法务事项：`/matters`、`/matters/:matterId`；
- 审核中心：`/reviews`、`/reviews/:reviewPackageId`。

### 资料与模板

- 事项模板（演示）：`/templates`；
- 合同与文件（未接入）：`/files`。

### 系统与审计

- Agent 执行记录：`/system/agent-runs`、`/system/agent-runs/:runId`；
- 数据边界：`/system/data-boundaries`；
- 系统信息（未接入）：`/system/about`。

兼容要求：`/` 重定向或映射到 `/today`；本轮可用受控 History API 实现，不强制新增 Router 依赖。

列表 query 示例：

```text
/matters?q=直播&risk=high&status=in_progress&owner=ou_legal&sort=openedAt_desc
```

打开详情后浏览器返回应恢复 query、页码和筛选上下文。

## 4. 页面模板

| 模板 | 固定结构 | 对应页面 |
|---|---|---|
| 工作台 | PageHeader → DataBoundary → 今日关注 → 主行动队列 → 期限/待确认 → 次级统计 | Today |
| 工作队列 | PageHeader → Search/Filter → Active filters → Desktop Table / Mobile Cards → Pagination | Matters、Agents、Reviews |
| 研判 | Candidate Queue → Source/Evidence → AI/Uncertainty → Human Decision | Inbox |
| 详情 | Matter Header → 风险/状态/负责人 → 下一步与任务 → 事实/审计侧栏 | Matter Detail |
| 审核 | Review Queue → 审核包正文 → 决定/版本/外发门禁 | Reviews |
| 表单 | Context summary → Form sections → Validation → Impact preview → Footer | Inbox confirm、期限/依赖/审核包 |
| 系统边界 | Capability boundary → Source/verification → Limitations → Read-only audit | Data Boundaries |
| 未接入 | Purpose → Current limitation → Safe alternative → Backend gap | Files、About |

## 5. 页面裁决

### 今日工作台

- 下一步行动队列保持第一主体；
- 摘要必须来自同一演示数据并明确快照口径；
- 期限与待确认消息是次级行动区；
- AI 建议后置、弱化，不能使用在线语义；
- 390 下折叠周统计，减少长页面认知负担。

### 待确认消息

- 页面名称使用“待确认消息”，AI 是内容来源，不是页面身份；
- 1440 使用队列 + 证据研判 + 人工决定；1024 收敛为队列 + 主区；390 队列和详情分步；
- 置信度是普通元数据，并明确不能替代证据；
- 只有 `create_matter` 且证据/状态门禁满足时才能打开正式确认；
- 未接入动作保持禁用并解释；
- 成功后进入新事项详情，返回路径清楚。

### 法务事项

- 真实前端筛选仅使用当前 `LegalMatter` 字段：关键词、分类、风险、工作状态、负责人、开启时间；
- 当前 API 不返回期限、等待对象和下一步摘要，因此本轮不得在列表伪造；
- 标题本身是可聚焦的打开操作，删除冗余“打开”列；
- 显示 active filters、逐项清除和清除全部；
- 390 使用 MatterCard。

### 事项详情

- 首屏顺序：风险/状态 → 计划完成或硬期限 → 负责人 → 下一步 → 等待/阻塞 → 背景/目标；
- 扁平化 `Card → List → Card` 嵌套；
- Deadline/Dependency 必须区分 loading、empty 与 error；
- 英文状态只在技术详情出现；
- Dialog 在移动端接近全屏，footer 不遮挡 validation；
- 未保存表单关闭时需要保护。

### 审核中心

- 从散落卡片改为全宽审核队列；
- 突出状态、标题、事项、提交时间、等待时长、目标和版本；
- 阅读顺序固定：背景 → 已确认事实 → 未确认事实 → 理由 → 风险 → 替代方案 → 依据 → 拟发送内容；
- “外发入队”仅在 approved 时启用，并明确不等于已发送；
- 390 使用 ReviewCard + 全屏审核 Drawer/Modal。

### 事项模板

- 改名并明确“演示”；
- 从八张重复大卡收敛为紧凑目录；
- 新建/配置无后端时禁用并说明；
- 查看事项可以真实导航并应用分类筛选。

### Agent 执行记录

- 归入系统与审计；
- 中文状态 + 技术原码；
- 390 使用 RunCard；
- JSON 只在详情折叠区展示并允许横向滚动；
- `completed` 仅表示运行结束，不表示法律结论已确认。

### 数据边界

- 删除绿色“正常”、42 个群聊、成功审计和可切换 Switch；
- 没有状态 API 时显示“状态查询未接入 / 待核验”；
- 静态安全原则使用只读能力矩阵；
- 暂停同步、调整授权无后端时禁用并解释；
- 390 使用定义列表/AuditRow，不使用桌面表格。

### 合同与文件 / 系统信息

- 使用各自专属 `UnavailableState`；
- 说明目的、当前限制、当前可用替代路径和后端缺口；
- 不使用同一泛化“模块已预留”。

## 6. 术语体系

| 技术词 | 界面词 |
|---|---|
| AI 收件箱 | 待确认消息 |
| Candidate | 待确认消息；技术区可显示消息候选 |
| FeishuMessage | 来源消息 |
| ContextSnapshot | 证据快照 |
| confirmed facts | 消息中明确陈述，待法务确认 |
| inferred facts | AI 推断 |
| LegalMatter | 法律事项 |
| WorkItem | 行动任务 |
| plannedCompleteAt | 计划完成时间，不称法律期限 |
| Deadline | 期限 |
| ReviewPackage | 审核包 |
| ReviewRecord | 审核记录 |
| Communication queued | 已进入外发队列 |
| AgentRun | Agent 执行记录 |
| AgentRun completed | 运行完成，不等于法律结论已确认 |

## 7. 状态与错误策略

### 数据来源标签

- 演示：Dashboard、事项模板；
- 实时 API：Inbox、Matters、Detail、Reviews、Agents，但不称“实时同步”；
- 未接入：Files、System About；
- 待核验：没有状态接口的数据边界信息。

### 权限

- 401：会话未验证，不暴露业务详情；
- 403：无权访问，不展示缓存摘要；
- 权限撤销：冻结来源、附件和 Agent 操作并说明影响范围。

### 陈旧与并发

- 只有真实时间戳才能显示“最后更新”；
- 409/版本冲突阻止提交、重新加载，不能覆盖人工确认值；
- 重新分析期间冻结旧结果正式确认；
- 保留上次成功数据时必须标“可能不是最新”。

### 错误

- 顶层错误：说明、重试、关联 ID；
- 局部错误：保留在局部并提供重试，不能显示为空；
- 筛选空、真空、权限空、未接入、错误空必须使用不同文案；
- API 失败禁止 fallback 到 mock。

## 8. 响应式任务顺序

### 1440

- 常驻侧栏；
- 高密度队列表格；
- Inbox 可三栏；
- Detail 主区 + 事实侧栏；
- Review 队列 + 审核详情。

### 1024

- 折叠导航；
- 减少次要列但保留风险、负责人和主操作；
- Inbox 保留窄队列 + 主详情；
- Detail 单列，侧栏信息后移；
- Review 使用列表 + Drawer。

### 390

- 导航 Drawer；
- 所有数据表格改为结构化卡片；
- 每屏一个主要任务；
- Inbox 队列/详情分步；
- 长表单/审核使用全屏 Overlay；
- 风险、期限、负责人、下一步不隐藏；
- 触控目标至少 44px。

## 9. 共享组件方向

- `PageHeader`
- `DataBoundaryBanner`
- `StatusTag`
- `RiskIndicator`
- `DeadlineIndicator`
- `HumanReviewIndicator`
- `EvidencePanel`
- `AiSuggestionPanel`
- `QueueToolbar`
- `ActiveFilterBar`
- `ResponsiveCollection`
- `MobileRecordCard`
- `StatePanel`
- `FormSection`
- `ResponsiveModal`
- `DecisionRail`
- `UnavailableState`

这些组件必须映射到现有 Ant Design primitives，不建立平行 UI 框架。

## 10. 设计自审门槛

- 导航和页面身份不以 AI 为中心；
- 行动在统计之前；
- 每页一个主操作；
- 无无意义卡片嵌套；
- 风险、状态不只靠颜色；
- 移动端不是桌面缩小版；
- 不存在未核验在线/同步/成功；
- 启用控制均有真实行为；
- 未接入能力禁用并解释；
- AI 不直接创建正式状态或外发；
- 页面有深链、刷新恢复和返回；
- 状态术语一致；
- 入队不写成已发送；
- 解决、关闭、归档不混用。

## 11. 分歧解决记录

| 议题 | Product UI 倾向 | UX/IA 约束 | 最终裁决 |
|---|---|---|---|
| Matters 展示期限/下一步 | 为扫描效率应前置 | 当前列表 API 不返回聚合数据 | 本轮不伪造；后端聚合后再加入 |
| Figma UI kit | 可建立组件体系 | 不能与 Ant Design 平行 | 只建映射 Ant Design 的本地规范，不导入 M3/SDS 视觉语言 |
| Dashboard 密度 | 继续收敛 | 行动优先、统计后置 | 桌面保留摘要，移动折叠周统计 |
| 完整事项闭环 | 设计完整状态 | 后端缺少状态迁移/关闭/归档 | 流程图标注后端缺口，不生成可执行按钮 |
