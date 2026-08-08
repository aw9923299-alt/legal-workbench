# Legal Workbench 系统与功能盘点

更新时间：2026-08-04
盘点基线：`main` / `5662476`，工作区存在用户既有未提交修改
盘点方式：仓库只读检查、Figma MCP 只读检查、Playwright MCP 安全演示夹具

## 1. 任务开始前状态

任务开始前 `main` 落后 `origin/main` 5 个提交。下列内容已经处于修改或未跟踪状态，本轮不得丢弃、重置或覆盖其原意：

- 已修改：`AGENTS.md`、`package.json`、`package-lock.json`；
- 已修改前端：`App.tsx`、`AiAssistant.tsx`、`MetricStrip.tsx`、`TaskTable.tsx`、`DashboardPage.tsx`、`InboxPage.tsx`、`apiLabels.ts`、`global.css`；
- 已存在但未跟踪：`.agents/skills/`、`apps/web/e2e/`、`playwright.config.ts`、`artifacts/`、`docs/superpowers/`、`docs/ui-review/`。

本轮以该工作树为真实起点，未执行 reset、checkout、提交或推送。

## 2. 技术与运行基线

| 项目 | 当前实现 | 结论 |
|---|---|---|
| 包管理 | npm workspaces | 根脚本代理到 `apps/web` |
| 前端 | React 18.3 + TypeScript 5.7 + Vite 6 | 单页应用 |
| UI | Ant Design declared `^5.24.0`、resolved `5.29.3` + `@ant-design/icons` 5.6 | 应继续复用，不引入平行框架 |
| 导航 | `App.tsx` 内存状态 | 只有 URL `/`；没有真实路由、深链或返回恢复 |
| 样式 | 单一 `global.css` + Ant Design theme token | 无 CSS Modules / styled-components |
| 状态 | React 本地 state/effect | 无集中状态库 |
| API | `services/api.ts` fetch 封装 | HttpOnly session、幂等键、相关 ID、明确错误；无静默 mock 回退 |
| Mock | `data/mock.ts`、`services/adapters.ts` | Dashboard、事项库、数据与权限仍以演示数据为主 |
| 测试 | Playwright 夹具测试（既有未提交） | Dashboard 与 Inbox 有覆盖，其他页面未覆盖 |
| 构建 | `npm run typecheck` / `npm run build` | 基线均通过 |
| Bundle | 单 JS 1,308.32 kB / gzip 411.75 kB | Vite 报 >500 kB；无路由级懒加载 |

## 3. 主题与应用壳

### Theme token

- 主色：`#315f8f`；
- 正文：`#17243a`；
- 次要文字：`#657083`；
- 边框：`#d8dee8`；
- 圆角：6px；
- 语义色：success `#31735d`、warning `#9c672c`、error `#a84949`；
- 字体：Inter、苹方、微软雅黑、system-ui。

### 应用壳

- 桌面：228px 侧栏，1024 宽度自动折叠为 72px；
- 移动：侧栏隐藏，使用左侧 Drawer；
- 顶栏：导航折叠、全局搜索、待核验状态、深色切换、AI、通知、头像；
- 可信边界：侧栏显示“本地演示”，但数据与权限页仍存在未经证实的“正常”状态；
- 可疑控制：全局搜索、待核验、AI 图标、通知图标没有实际业务行为或明确禁用原因；
- 导航缺口：合同与文件、系统设置只有同一占位页；投诉/知识产权/咨询/争议是事项库模板，不是独立可访问业务页。

## 4. 可达页面清单

当前并不存在前端 URL 路由。下表“逻辑路由”是 `page` state / 详情 state，对应唯一浏览器 URL `/`。

| 逻辑路由 | 页面 | 目的与主要用户 | 主要任务与操作 | 数据来源 / 状态 | 主要组件与 API | 状态覆盖 | 移动端与已知风险 |
|---|---|---|---|---|---|---|---|
| `dashboard` | 今日工作台 | 法务查看今日优先事项 | 进入待确认、切换队列 Tab、打开事项 | 全部 `mock.ts`；明确演示 | MetricStrip、TaskTable、AiAssistant；无 API | 无加载/错误/权限；有静态演示提示 | 390 使用任务卡；很长；消息卡按钮无行为；统计仍较突出 |
| `inbox` | 待确认消息 | 法务核对证据、修订 AI 提取、人工确认 | 选 Candidate、看来源/证据边界、重新分析、打开确认 Drawer | Live API；测试使用拦截夹具 | `listCandidates`、`getMessageAnalysis`、`retryMessageAnalysis`、`confirmCandidate` | loading / empty / list error / forbidden / detail error / running / stale retry / validation | 390 队列与详情分步；Drawer 全屏；当前能力最完整 |
| `matters` | 法务事项中心 | 法务检索并进入事项 | 搜索、分页、打开详情、刷新 | Live API | `listMatters` | loading / empty / error；无 permission/stale | 390 仍是桌面表格，列逐字换行，不可用；无筛选、排序和 active filter |
| `matter-detail` | 事项详情 | 法务处理事项、任务、期限、依赖、审核包 | 返回、确认优先级、添加期限/依赖、创建审核包 | Live API | `getMatter`、`listWorkItems`、`listDeadlines`、`listDependencies`、四类写 API | loading / error / empty work item / form validation；子请求失败被静默吞掉 | 390 信息顺序尚可但操作拥挤；Modal 固定宽度；状态值混用英文原码 |
| `reviews` | 审核中心 | 法务审核外发内容 | 打开审核 Modal、选择决定、编辑最终内容、外发入队 | Live API | `listReviewPackages`、`reviewPackage`、`queueCommunication` | loading / empty / list error / submit error | 390 卡片可读；无搜索/筛选；状态和类型显示原码；详情层级弱 |
| `library` | 法务事项库 | 查看事项类型模板 | 新建、配置模板、查看事项 | 全部静态 mock | Row/Card；无 API | 无 loading / empty / error / permission | 三类按钮全部无行为；“可配置”易被理解为已实现；移动端卡片过长 |
| `files` | 合同与文件占位 | 说明模块未接入 | 无 | 无数据 | 通用占位 div | 仅占位 | 明确未实现，但与 settings 共用同一泛化文案，无后续路径 |
| `agents` | Agent 中心 | 查看受控 AgentRun 与授权来源 | 刷新、查看详情 Modal | Live API | `listAgentRuns`、`getAgentRun` | loading / empty / error | 390 桌面表格被裁切；细节 JSON 不适配小屏；状态为英文原码 |
| `security` | 数据与权限 | 展示数据边界、安全策略、审计 | 暂停同步、调整授权、切换策略 | 全部静态 mock | Descriptions、Switch、Table；无 API | 无 loading / error / permission | “正常”“42 个群聊”“成功”伪装成实时事实；所有动作无行为；390 表格不可读 |
| `settings` | 系统设置占位 | 说明模块未接入 | 无 | 无数据 | 通用占位 div | 仅占位 | 同 files；没有系统状态、版本或后端缺口清单 |

## 5. 主要组件清单

| 组件 | 用途 | 数据与行为 | 风险 |
|---|---|---|---|
| `TaskTable` | Dashboard 任务队列 | mock；桌面表格、1024 紧凑列表、390 卡片 | 仅从 mock 打开事项中心，不能打开真实 Matter ID |
| `MetricStrip` | 演示摘要 | mock 计算 | 指标单元具有按钮样式语义但无明确跳转语义 |
| `AiAssistant` | 演示建议 | mock | 已改为浅色并标注人工确认；内容仍为静态建议 |
| `StatusTags` | 任务 mock 状态 | 标签映射 | 与 Live API 的 `apiLabels` 是两套术语来源 |
| Inbox 内部组件 | Candidate 队列、证据、AI、人工确认 | Live API，严格冻结条件 | 685 行单文件，后续维护成本高 |
| Task Detail 内部组件 | WorkItem 卡、四类 Modal | Live API | 子资源错误静默，Card 嵌套，响应式不足 |

## 6. API 与 mock 边界

### Live API 页面

- Inbox：Candidate、消息分析、重新分析、人工确认创建事项；
- Matters：事项列表与详情；
- WorkItem：优先级确认、期限、依赖；
- Reviews：审核包、审核记录、Communication 入队；
- Agents：AgentRun 列表与详情。

`services/api.ts` 在 API 失败时抛出 `ApiError`，没有静默 fallback 到 mock，符合安全规则。

### 演示页面

- Dashboard、Library、Security 使用 `mock.ts` 或页面内静态数组；
- `services/adapters.ts` 提供 mock gateway/repository，但当前主要 Live 页面没有使用它回退；
- Dashboard 有演示声明；Library 和 Security 的声明不足，Security 甚至显示未验证的绿色成功状态。

## 7. 搜索、筛选、排序与导航

- 全局搜索：可输入但无行为，是死输入；
- Matters 搜索：真实过滤事项编号、标题、负责人；没有 active filter、清空按钮、排序或筛选；
- Dashboard Tabs：真实过滤内存 mock；
- 其他 Live 页面：缺少面向实际队列的搜索、筛选与排序；
- 返回：事项详情的页面内按钮有效，但浏览器返回、刷新恢复和深链无效；
- 占位导航：入口可达但只显示通用占位，不应呈现为成熟模块。

## 8. 无障碍与兼容性初查

- Inbox 的按钮命名、Drawer label、错误与 validation 基础较好；
- 移动导航有 `aria-label="主导航"`；
- 顶栏通知、AI 等图标按钮缺少明确 aria-label；
- 表格行点击依赖鼠标，事项标题缺少独立链接语义；
- 风险大多同时有文字，未只依赖颜色；
- 多个 Modal 使用 Ant Design 默认 focus trap，但触发器焦点恢复未系统验证；
- 390 下 Matters、Agents、Security 的表格视觉不可用；
- Console 存在 Ant Design `Card bordered` 弃用警告；
- favicon 404；不影响主流程，但应作为低优先级清理。

## 9. Figma 现状

文件：[Legal Workbench Design](https://www.figma.com/design/Dj6mMELyo2xq1kSocHDNxW/Legal-Workbench-Design?node-id=0-1)

- Figma MCP 已验证当前账号为 Starter plan 的 `View` 席位；
- 文件当前只有空白 `Page 1`（node `0:1`，0×0）；
- 首次正式写入在执行前触发 Starter plan MCP tool call limit；本轮无法创建页面、Variables、Components、Variants、Auto Layout 或 Ready for development 标记；
- 后续设计以仓库文档和 Playwright 截图为可审计交付，不伪称已写入原生 Figma 图层。
