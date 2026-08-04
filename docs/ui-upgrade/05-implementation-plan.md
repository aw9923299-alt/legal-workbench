# Legal Workbench System UI Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前所有可达前端页面升级为专业、克制、可信、响应式且不伪造业务状态的法务运营控制台。

**Architecture:** 保留 React 18、Vite 与 Ant Design 5，不新增路由或 UI 依赖；以受控 History API 提供真实 URL 路径与 query 恢复，以公共页面/状态/响应式集合组件统一各页。现有 API 契约、审核门禁和人工确认值保持不变，API 失败不得回退 mock。

**Tech Stack:** React 18.3, TypeScript 5.7, Vite 6, Ant Design `^5.24.0`（resolved 5.29.3）, Playwright, CSS variables.

## Global Constraints

- 不丢弃、不覆盖、不重置任务开始前已有修改；禁止 `git reset --hard`。
- 不提交、不推送。
- 不安装新 UI 框架，不建立与 Ant Design 平行的设计系统。
- Codex 仍是唯一 AI 核心；不改变审核、发送、权限、幂等或正式状态门禁。
- 不访问真实生产数据；浏览器测试只用确定性安全夹具。
- 未实现功能必须禁用、标演示/未接入或提供安全导航，不得伪造成功。
- API 失败不得无提示切换到 mock。
- 每个任务都先补 Playwright/组件可观察行为，再实现，再运行相关测试。
- 用户明确禁止提交，因此以测试检查点替代 writing-plans 模板中的 commit 步骤。

---

## 文件结构

计划新增：

- `apps/web/src/navigation.ts`：URL 路径/query 解析、构造和 History API 导航。
- `apps/web/src/components/PageHeader.tsx`：统一标题、说明、来源和操作区。
- `apps/web/src/components/DataBoundaryBanner.tsx`：演示/API/待核验/未接入/陈旧状态。
- `apps/web/src/components/StatePanel.tsx`：loading/empty/error/permission/unavailable 状态。
- `apps/web/src/components/ResponsiveCollection.tsx`：桌面表格与移动卡片切换壳。
- `apps/web/src/components/UnavailableState.tsx`：Files/About 专属未接入页面。
- `apps/web/e2e/navigation.spec.ts`：URL、返回、移动导航、死控件与状态语义。
- `apps/web/e2e/matters.spec.ts`：搜索、筛选、详情、局部状态和表单。
- `apps/web/e2e/reviews-agents.spec.ts`：审核、Agent 与移动卡片。
- `apps/web/e2e/data-boundaries.spec.ts`：不显示虚假在线/同步/成功状态。

计划修改：`App.tsx`、全部现有 page、必要 shared component、`main.tsx`、`global.css`、Playwright 配置和现有 E2E 测试。后端文件不在本轮范围。

### Task 1: URL 导航与应用壳

**Files:**
- Create: `apps/web/src/navigation.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/styles/global.css`
- Test: `apps/web/e2e/navigation.spec.ts`

**Interfaces:**
- Produces: `AppRoute`, `parseLocation(location)`, `buildPath(route)`, `navigate(path, options?)`, `useAppLocation()`。
- Consumes: 现有页面 callback；不新增 Router 依赖。

- [ ] 写 URL 导航测试：`/` 映射 `/today`，各导航项产生真实路径，浏览器返回恢复 `/matters?…`，刷新详情仍在同一 Matter。
- [ ] 运行 `npx playwright test apps/web/e2e/navigation.spec.ts`，确认旧实现因 URL 恒为 `/` 而失败。
- [ ] 实现 History API 导航与 `popstate` 订阅，映射 `today/inbox/matters/reviews/templates/files/system/*`。
- [ ] 重构侧栏为“工作 / 资料与模板 / 系统与审计”分组；保留移动 Drawer。
- [ ] 删除或禁用无行为的待核验、AI、通知控制；把全局搜索缩为真实事项搜索入口；去掉未完成暗色切换。
- [ ] 运行 navigation spec、typecheck，并检查三视口 `scrollWidth`。

### Task 2: Theme 与公共组件

**Files:**
- Modify: `apps/web/src/main.tsx`
- Modify: `apps/web/src/styles/global.css`
- Create: `apps/web/src/components/PageHeader.tsx`
- Create: `apps/web/src/components/DataBoundaryBanner.tsx`
- Create: `apps/web/src/components/StatePanel.tsx`
- Create: `apps/web/src/components/ResponsiveCollection.tsx`
- Create: `apps/web/src/components/UnavailableState.tsx`
- Modify: `apps/web/src/components/StatusTags.tsx`
- Test: `apps/web/e2e/navigation.spec.ts`

**Interfaces:**
- Produces: `PageHeader`, `DataBoundaryBanner`, `StatePanel`, `ResponsiveCollection<T>`, `UnavailableState`。
- Consumes: 既有 token `#315f8f/#17243a/#657083/#d8dee8/6px`。

- [ ] 添加公共状态、44px 触控、focus-visible、API/AI/人工语义的 Playwright 断言。
- [ ] 运行相关测试，确认公共状态与 focus 断言在旧实现失败。
- [ ] 在 Ant Design ConfigProvider 中补齐 success/warning/error/bg/token，不改主色基线。
- [ ] 实现五个公共组件并使用语义 props；禁止组件内部生成 mock 数据。
- [ ] 把 `Card bordered` 改为推荐 API，消除当前页面弃用警告。
- [ ] 运行 typecheck 与 Dashboard/Inbox E2E。

### Task 3: 今日工作台与未接入页面

**Files:**
- Modify: `apps/web/src/pages/DashboardPage.tsx`
- Modify: `apps/web/src/components/MetricStrip.tsx`
- Modify: `apps/web/src/components/TaskTable.tsx`
- Modify: `apps/web/src/components/AiAssistant.tsx`
- Modify: `apps/web/src/pages/LibraryPage.tsx`
- Modify: `apps/web/src/App.tsx`
- Test: `apps/web/e2e/dashboard.spec.ts`
- Test: `apps/web/e2e/navigation.spec.ts`

**Interfaces:**
- Consumes: `PageHeader`, `DataBoundaryBanner`, `ResponsiveCollection`, `UnavailableState`, navigation callbacks。
- Produces: `/today`、`/templates`、`/files`、`/system/about` 的完整演示/未接入状态。

- [ ] 扩展测试：Dashboard 主行动可达、演示来源明确、消息条目有真实导航；模板筛选可进入 `/matters?category=…`；无后端的新建/配置禁用并有原因。
- [ ] 运行测试并确认旧死按钮/占位文案断言失败。
- [ ] 保持下一步队列为首要主体，统计降级，AI 建议后置并明确待人工确认。
- [ ] 把 Library 改为“事项模板（演示）”紧凑目录；只保留真实可执行查看入口。
- [ ] 为 Files/About 使用不同 `UnavailableState`，列明目的、限制、安全替代路径和后端缺口。
- [ ] 运行 Dashboard/navigation specs 与三视口视觉检查。

### Task 4: 待确认消息路由与表单安全

**Files:**
- Modify: `apps/web/src/pages/InboxPage.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/styles/global.css`
- Modify: `apps/web/e2e/inbox.spec.ts`

**Interfaces:**
- Consumes: `/inbox/:candidateId` route、`PageHeader`、`DataBoundaryBanner`、现有 API 与确认门禁。
- Produces: URL 可恢复选择、390 队列/详情返回、dirty close guard、创建后 Matter 深链。

- [ ] 新增测试：candidate 深链、390 队列/详情、修改 AI 提取字段、validation、取消与 unsaved confirm、重复提交保护、成功后进入 `/matters/:id`。
- [ ] 运行 Inbox spec，确认新增场景失败而既有证据边界测试仍通过。
- [ ] 仅把人工可编辑字段作为表单真值；重新分析或 409 不得覆盖已编辑值。
- [ ] 390 保持单任务流程；Drawer 全屏且 footer 不遮挡 validation；关闭恢复焦点。
- [ ] 非 `create_matter` 动作继续安全阻止，不能为了完整流程虚构关联/忽略 API。
- [ ] 运行 Inbox spec、typecheck。

### Task 5: 事项队列搜索、筛选与移动卡

**Files:**
- Modify: `apps/web/src/pages/TaskCenterPage.tsx`
- Modify: `apps/web/src/services/apiLabels.ts`
- Modify: `apps/web/src/styles/global.css`
- Test: `apps/web/e2e/matters.spec.ts`

**Interfaces:**
- Consumes: `ResponsiveCollection<LegalMatter>`、URL query、`listMatters`。
- Produces: 真实关键词/分类/风险/状态/负责人筛选，active filter，详情返回恢复。

- [ ] 编写固定 API 夹具，断言关键词、分类、风险、状态筛选真实改变结果，active filter 可清除，返回保留 query。
- [ ] 新增 1440/1024/390 断言：桌面表格、紧凑集合、390 MatterCard；无页面溢出。
- [ ] 运行 matters spec，确认移动表格和假筛选问题在旧实现失败。
- [ ] 实现 URL 驱动筛选和清除；只使用 `LegalMatter` 当前字段，不伪造期限、等待对象或下一步。
- [ ] 事项标题作为可聚焦打开入口；风险不只靠颜色；删除冗余打开列。
- [ ] 运行 matters spec、typecheck。

### Task 6: 事项详情局部状态与响应式表单

**Files:**
- Modify: `apps/web/src/pages/TaskDetailPage.tsx`
- Modify: `apps/web/src/styles/global.css`
- Test: `apps/web/e2e/matters.spec.ts`

**Interfaces:**
- Consumes: Matter route、现有四类写 API 与 shared states。
- Produces: WorkItems/Deadlines/Dependencies 独立 loading/error/empty，响应式 Dialog，dirty/repeat guards。

- [ ] 添加测试：标题、返回、priority、deadline、dependency、review package Dialog；局部 API 失败不能显示为空；验证和取消可用。
- [ ] 运行测试，确认旧实现静默吞子请求错误。
- [ ] 重排首屏为风险/状态/负责人/目标/当前阶段，再显示任务、期限、依赖；减少 Card 嵌套。
- [ ] 分离子资源 loading/error/empty；英文原码仅放技术详情。
- [ ] 响应式 Modal 390 近全屏；提交中禁用；dirty close 二次确认。
- [ ] 运行 matters spec、typecheck。

### Task 7: 审核中心与 Agent 执行记录

**Files:**
- Modify: `apps/web/src/pages/ReviewCenterPage.tsx`
- Modify: `apps/web/src/pages/AgentCenterPage.tsx`
- Modify: `apps/web/src/services/apiLabels.ts`
- Modify: `apps/web/src/styles/global.css`
- Test: `apps/web/e2e/reviews-agents.spec.ts`

**Interfaces:**
- Consumes: Review/Communication 与 AgentRun API、`ResponsiveCollection`。
- Produces: ReviewCard/RunCard、中文业务状态、全屏移动详情、真实外发门禁。

- [ ] 写测试：审核列表、决定、最终正文、只有 approved 可外发入队；“入队”不显示成“已发送”；Agent completed 不显示成法律结论确认。
- [ ] 写 390 测试：无被裁切表格，Modal/JSON 可读且局部滚动。
- [ ] 运行 spec，确认旧移动表格和原码问题失败。
- [ ] 重构审核为全宽队列 + 详情层；保持审核包阅读顺序和批准版本一致门禁。
- [ ] Agent 归入系统与审计；中文状态 + 技术原码；390 使用 RunCard。
- [ ] 运行 spec、typecheck。

### Task 8: 数据边界页面去伪状态

**Files:**
- Modify: `apps/web/src/pages/SecurityPage.tsx`
- Modify: `apps/web/src/styles/global.css`
- Test: `apps/web/e2e/data-boundaries.spec.ts`

**Interfaces:**
- Consumes: `PageHeader`, `DataBoundaryBanner`, static architecture facts。
- Produces: `/system/data-boundaries` 的只读能力矩阵与待核验状态。

- [ ] 写测试禁止出现“正常”“在线”“同步成功”“42 个群聊”等未经证实事实，禁止可操作 Switch 与死按钮。
- [ ] 写 390 断言：定义列表/AuditRow 可读，无表格横向裁切。
- [ ] 运行 spec，确认旧 Security 页面失败。
- [ ] 删除伪状态和假开关；按“已在代码中实现的原则 / 状态接口未接入 / 后端缺口”分区。
- [ ] 保留真实架构安全原则，但不呈现生产健康度。
- [ ] 运行 data-boundaries spec、typecheck。

### Task 9: 路由懒加载、完整回归与文档

**Files:**
- Modify: `apps/web/src/App.tsx`
- Modify: `playwright.config.ts`（仅在现有配置缺口确实阻塞测试时）
- Modify: `docs/ui-upgrade/06-functional-qa.md`
- Modify: `docs/ui-upgrade/07-final-report.md`
- Test: `apps/web/e2e/*.spec.ts`

**Interfaces:**
- Consumes: 全部 route、共享组件和安全 API 夹具。
- Produces: 路由级 lazy chunks、完整 before/after 证据、真实验证报告。

- [ ] 用 `React.lazy`/`Suspense` 按页面拆包；共享 Ant Design vendor 不做无证据的手工拆包。
- [ ] 对十个逻辑页面在 1440×900、1024×768、390×844 保存 `artifacts/ui-upgrade/after/<route>/<viewport>.png`。
- [ ] 使用 Playwright 检查主操作、搜索、筛选、排序（存在时）、Tab、表格/卡片、表单、Drawer、Dialog、返回、焦点、console 与网络失败。
- [ ] 运行 `npm run typecheck`、`npm run build`、`npx playwright test`、`git diff --check`；仓库未配置 lint/unit 脚本时明确记录。
- [ ] 比较 build chunk 与基线 JS 1,308.32 kB / gzip 411.75 kB、CSS 21.76 kB / gzip 4.89 kB。
- [ ] 完成 `06-functional-qa.md` 与 `07-final-report.md`，如实记录 Figma Starter MCP 配额限制和残余后端缺口。

## 自审

- Spec 覆盖：所有十个逻辑页面、应用壳、导航、三视口、主要表单/Drawer/Dialog、关键流程、状态边界、无障碍、bundle 和工程命令均有对应任务。
- 明确不在范围：真实 Feishu/Codex/外发/文件/系统状态后端能力；没有用 UI 假装实现。
- 类型一致：导航统一由 `AppRoute` 和 URL 构造；集合统一由 `ResponsiveCollection<T>`；状态统一由 `StatePanel`/`DataBoundaryBanner`。
- 不提交：全部任务使用测试检查点，不含 commit/push 步骤。
