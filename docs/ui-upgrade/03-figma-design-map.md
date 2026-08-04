# Legal Workbench Figma 设计映射

更新时间：2026-08-04
Figma 文件：[Legal Workbench Design](https://www.figma.com/design/Dj6mMELyo2xq1kSocHDNxW/Legal-Workbench-Design?node-id=0-1)

## 1. Figma 交付状态

本轮已经通过 Figma MCP 读取目标文件、账号席位、页面、已有节点、本地变量、组件与订阅库。文件当前包含：

- `Page 1`（node `0:1`，空白）；
- `00 MCP Test`，其中 `Legal Workbench MCP Test` frame 为既有写入验证资产；
- 无本地 Variables、Components 或 Component Sets；
- 订阅库包括 Material 3 与 Simple Design System，但与现有 Ant Design 技术基线不一致，本轮不引入。

首次正式变量写入在执行前被 Figma 服务拒绝：Starter plan 的 MCP tool call limit 已达到。因此本轮没有向 Figma 写入页面、Variables、Components、Variants、Auto Layout、连接线或 Ready for development 标记，也没有删除或修改既有页面。以下内容是可执行的设计映射和 Figma 回填规范，不伪称已经形成原生图层。

## 2. 计划页面结构

配额恢复后，按以下顺序在原文件中新建独立页面；保留 `Page 1` 和 `00 MCP Test`：

| 页面 | 内容 | 主要来源 |
|---|---|---|
| `00 Current Audit` | 当前应用壳、工作台、待确认、事项、详情、表单、Drawer、Dialog、空/错状态 | `artifacts/ui-upgrade/before/` |
| `01 Foundations` | 色彩、字体、间距、圆角、边框、阴影、栅格、断点、语义状态 | `04-design-system.md` |
| `02 Components` | Ant Design 映射组件、状态与响应式 variants | 现有组件 + 公共组件计划 |
| `03 Desktop Screens` | 1440×900 的全部现有逻辑路由 | before/after desktop 截图 |
| `04 Tablet Screens` | 1024×768 紧凑桌面/平板 | before/after compact 截图 |
| `05 Mobile Screens` | 390×844 的核心流程与所有页面 | before/after mobile 截图 |
| `06 User Flows` | 消息转事项、事项处理、搜索筛选、移动端处理 | `02-information-architecture.md` |
| `07 Handoff` | 组件映射、token、交互规则、后端缺口、验收链接 | 本目录全部文档 |

## 3. Screen → route → React 映射

| Figma screen | URL | React 页面 | 数据边界 |
|---|---|---|---|
| Today / default | `/today` | `DashboardPage` | 安全演示数据 |
| Inbox / queue | `/inbox` | `InboxPage` | API；失败不回退 mock |
| Inbox / selected | `/inbox/:candidateId` | `InboxPage` | API；选择需可深链恢复 |
| Matters / queue | `/matters` | `TaskCenterPage` | API + 客户端筛选 |
| Matter / detail | `/matters/:matterId` | `TaskDetailPage` | API；子资源独立状态 |
| Reviews / queue | `/reviews` | `ReviewCenterPage` | API |
| Templates / demo | `/templates` | `LibraryPage` | 演示目录 |
| Files / unavailable | `/files` | 专属 unavailable view | 未接入 |
| Agent runs / queue | `/system/agent-runs` | `AgentCenterPage` | API |
| Agent run / detail | `/system/agent-runs/:runId` | `AgentCenterPage` | API |
| Data boundaries | `/system/data-boundaries` | `SecurityPage` | 静态原则；状态待核验 |
| System about | `/system/about` | 专属 unavailable view | 未接入 |

`/` 映射到 `/today`。列表筛选使用 URL query；从详情返回时保留 query 与页码。

## 4. Component → Ant Design → repository 映射

| Figma component | Ant Design 基础 | repository 映射 | 约束 |
|---|---|---|---|
| Button / Icon Button | `Button` | 主题 token + shared class | 图标按钮必须有 aria-label；无行为则禁用并说明 |
| Input / Search | `Input`, `Input.Search` | `QueueToolbar` | Enter/清除必须真实改变 URL 或列表 |
| Select / Filter | `Select` | `QueueToolbar` | 显示 active filters；可逐项清除 |
| Date Picker | `DatePicker` | 详情表单 | 移动端宽度 100%；有验证 |
| Tabs / Segmented | `Tabs`, `Segmented` | Dashboard/Inbox | 不依赖颜色表达 selected |
| Tag / Badge | `Tag`, `Badge` | `StatusTag`, `RiskIndicator` | 中文标签 + 语义文本；技术原码仅在详情 |
| Alert | `Alert` | `DataBoundaryBanner`, local errors | 区分演示、待核验、错误、权限、陈旧 |
| Card | `Card` | `MobileRecordCard`, panels | 避免 Card 嵌套；使用 `variant` 推荐 API |
| Table | `Table` | desktop collections | 只在可读宽度显示；标题用可聚焦按钮/链接 |
| Task/Matter/Review/Run Card | Card + Typography | `ResponsiveCollection` card renderer | 390 保留风险、期限/状态、负责人、下一步 |
| Empty/Loading/Error | `Empty`, `Skeleton`, `Alert`, `Result` | `StatePanel` | 真空、筛选空、错误、无权限、未接入不可混用 |
| Drawer | `Drawer` | Inbox/mobile nav | 390 全屏；关闭后焦点回到触发器 |
| Dialog | `Modal` | `ResponsiveModal` | 390 近全屏；验证内容不被 footer 遮挡 |
| Form Section | `Form`, `Space`, `Divider` | `FormSection` | 标题、解释、字段和影响预览同组 |
| Timeline | `Timeline` | matter/audit | 仅显示真实时间戳 |
| AI Suggestion Panel | `Alert`/custom surface | `AiSuggestionPanel` | 明确“AI 建议，待人工确认” |
| Evidence Panel | `Descriptions`/custom surface | `EvidencePanel` | 来源、快照、附件元数据与解析边界分开 |
| Page Header | `Typography`, `Space` | `PageHeader` | 一页一个标题和一个主要动作 |
| Sidebar / Topbar | `Layout`, `Menu` | `App.tsx` shell | 分组导航；删除死状态和无行为图标 |

## 5. Variable → theme token 映射

| Figma variable | 值 | Ant Design / CSS |
|---|---:|---|
| `color/primary-500` | `#315f8f` | `colorPrimary`, `--primary` |
| `color/text-primary` | `#17243a` | `colorText`, `--text` |
| `color/text-secondary` | `#657083` | `colorTextSecondary`, `--text-secondary` |
| `color/border` | `#d8dee8` | `colorBorder`, `--border` |
| `color/canvas` | `#edf1f5` | `colorBgLayout`, `--canvas` |
| `color/success-500` | `#31735d` | `colorSuccess` |
| `color/warning-500` | `#9c672c` | `colorWarning` |
| `color/danger-500` | `#a84949` | `colorError` |
| `radius/md` | `6` | `borderRadius`, `--radius` |
| `space/1..8` | `4,8,12,16,24,32` | 4px spacing rhythm |
| `size/touch-min` | `44` | mobile minimum target |

具体状态、字体、阴影和响应式规则见 `04-design-system.md`。

## 6. State → React/API 映射

| Figma state | React/API 条件 | 界面行为 |
|---|---|---|
| loading | 首次请求未完成 | Skeleton/Spin + 语义文案，不展示旧成功状态 |
| refreshing | 已有数据，重取中 | 保留内容并标刷新，不重复提交 |
| empty | 200 且数据集合为空 | 说明当前无记录 |
| filtered empty | 数据存在但条件无结果 | 显示 active filters 与清除条件 |
| error | `ApiError` / network failure | 错误原因、重试、correlation id；不 mock 回退 |
| permission denied | 401/403 | 隐藏敏感摘要，显示会话/权限说明 |
| stale | 409 或版本不一致 | 阻止提交并要求刷新，人工确认值不被覆盖 |
| unsaved changes | 表单 dirty 且尝试关闭 | 二次确认放弃 |
| destructive confirmation | 有真实破坏性动作 | 明确对象、影响和不可逆性；当前无支持则不呈现 |
| AI suggestion | Agent output 未人工确认 | 紫灰弱表面 + 固定说明 |
| human confirmed | Review/confirmation 记录存在 | 显示确认人、时间、版本 |
| system state | 确定性 API 状态 | 蓝/中性；不得与 AI 结论混用 |

## 7. 流程到测试映射

| 流程 | Playwright 入口 | 验收点 |
|---|---|---|
| 消息转事项 | `/today` → `/inbox/:id` → confirm | 证据、AI、缺失材料、人工编辑、验证、创建后进入详情 |
| 事项处理 | `/matters` → detail → dialogs | 风险、任务、局部错误、表单取消、审核包门禁 |
| 搜索筛选 | `/matters?q=...` | active filters、清除、详情返回恢复 |
| 移动端 | 390 导航 → queue → detail | 44px、无页面溢出、表格卡片化、返回路径 |
| 审核 | `/reviews` → review modal | 决定、最终正文、外发入队不等于已发送 |
| 系统边界 | `/system/data-boundaries` | 无在线/同步/成功伪状态、无可操作假开关 |

## 8. Current Audit 参考资产

基线截图完整保存在：

```text
artifacts/ui-upgrade/before/<route-name>/1440.png
artifacts/ui-upgrade/before/<route-name>/1024.png
artifacts/ui-upgrade/before/<route-name>/390.png
```

覆盖 route-name：`dashboard`、`inbox`、`matters`、`matter-detail`、`reviews`、`library`、`files`、`agents`、`security`、`settings`。另有 Inbox Drawer/validation、Matter Dialog、Review Dialog、Agent Dialog、移动导航与 console/network 状态截图。

配额恢复后，这些 PNG 可作为 `00 Current Audit` 的图像参考；除非经过网页捕获或手工重建，不应称为可编辑原生图层。
