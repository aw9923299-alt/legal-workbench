# Legal Workbench 系统级产品升级最终报告

完成日期：2026-08-04
设计方向：**安静的法务运营控制台**
代码状态：未提交、未推送；保留任务开始前所有既有修改

## 1. 审查页面

本轮完整审查并实施当前仓库实际存在的全部逻辑页面：

1. `/today` 今日工作台；
2. `/inbox`、`/inbox/:candidateId` 待确认消息；
3. `/matters` 法务事项中心；
4. `/matters/:matterId` 事项详情；
5. `/reviews`、`/reviews/:reviewPackageId` 审核中心；
6. `/templates` 事项模板（演示）；
7. `/files` 合同与文件未接入；
8. `/system/agent-runs`、`/:runId` Agent 执行记录；
9. `/system/data-boundaries` 数据边界；
10. `/system/about` 系统信息未接入；
11. `/` 重定向、未知路径、桌面/折叠/移动应用壳与导航。

投诉、知识产权、咨询、诉讼/争议在当前仓库中是事项分类或演示模板，不是独立 route。本轮保留为 `/templates` → `/matters?category=…` 的真实筛选入口，没有凭空新增大型业务模块。

## 2. Figma 文件与实际交付

Figma：[Legal Workbench Design](https://www.figma.com/design/Dj6mMELyo2xq1kSocHDNxW/Legal-Workbench-Design?node-id=0-1)

Figma MCP 已读取目标文件、既有页面/节点、变量、组件和席位。首次正式写入在执行前被 Figma Starter plan 的 MCP tool call limit 拒绝，因此本轮 **没有** 创建 `00 Current Audit` 至 `07 Handoff` 页面、Variables、Components、Variants、Auto Layout、流程连线或 Ready for development 标记，也没有修改既有设计。限制、计划页面结构、Screen/Component/Variable/State 映射已完整写入 `03-figma-design-map.md` 和 `04-design-system.md`；before/after PNG 可在配额恢复后回填，但当前不称为原生 Figma 图层。

## 3. 最终设计方向

- 行动先于统计：今日工作台首屏是下一步工作队列；
- 证据先于 AI：Inbox 先展示来源、快照、附件覆盖，再展示 AI 提取与推断；
- 人工决定可辨认：AI 建议、人工确认、确定性系统状态使用不同标签和表面；
- 状态必须可证实：删除未验证的连接、同步、在线、成功和数量；
- 桌面高密度、移动重组任务：390 不再缩小桌面表格；
- 统一复用既有主色 `#315f8f`、正文 `#17243a`、次要文字 `#657083`、边框 `#d8dee8` 和 6px 圆角；
- 复用 Ant Design 5，没有引入平行 UI 框架。

## 4. 页面与流程改进

- 应用壳：分为“工作 / 资料与模板 / 系统与审计”；删除死状态、AI/通知/暗色控件；全局搜索进入真实 Matter URL；移动导航完整可用。
- URL：所有页面、Candidate、Matter、ReviewPackage、AgentRun 均有真实路径；深链、刷新、浏览器后退和详情返回可恢复。
- Dashboard：行动队列先于次要信息，演示来源和 AI 建议边界稳定可见。
- Inbox：队列/详情/确认三阶段清楚；证据、推断、缺失材料与人工字段分离；处理延迟响应、409、retry、dirty close、validation 和重复提交。
- Matters：真实关键词和四类筛选、active filters、逐项/全部清除、未知 query 保留；桌面表格、1024 紧凑记录、390 卡片。
- Matter detail：风险/状态/负责人/目标/阶段先行；移动首屏显示下一步、计划时间、等待对象、阻塞原因和最近硬期限；期限和依赖有独立加载/空/错/权限/陈旧/重试；四类表单具备验证、dirty、重复门禁和视口内 footer。
- Reviews：固定证据阅读顺序；显示 `replyToMessageId/receiveId` 真实外发目标，未知目标阻止批准；显示最新审核决定与最终正文；返回事项同样受 dirty guard 保护；只有 approved 可入队，queued 不冒充 sent。
- AgentRuns：中文业务状态与原始码并列；completed 不冒充法律确认；JSON 局部滚动。
- Templates：明确演示目录；只有分类查看真实生效，新建/配置安全禁用。
- Data boundaries：静态“正常/成功/授权数量/日志”和假 Switch 全部移除，改为“已落实约束 / 尚需后端支持”。
- Files/About：分别说明目的、限制、后端缺口和当前安全替代路径。

## 5. 修改文件

任务开始前已经 dirty 的文件和目录详见 `00-system-inventory.md`。最终工作树中，UI 升级涉及：

```text
apps/web/src/App.tsx
apps/web/src/navigation.ts
apps/web/src/main.tsx
apps/web/src/styles/global.css
apps/web/src/components/{AiAssistant,MetricStrip,StatusTags,TaskTable}.tsx
apps/web/src/components/{PageHeader,DataBoundaryBanner,ResponsiveCollection,StatePanel,UnavailableState}.tsx
apps/web/src/pages/{DashboardPage,InboxPage,TaskCenterPage,TaskDetailPage}.tsx
apps/web/src/pages/{ReviewCenterPage,AgentCenterPage,LibraryPage,SecurityPage}.tsx
apps/web/src/services/apiLabels.ts
apps/web/src/services/{apiFailure,communicationTarget}.ts
apps/web/e2e/{dashboard,inbox,navigation,matters,reviews-agents,data-boundaries}.spec.ts
playwright.config.ts
docs/ui-upgrade/00-system-inventory.md ... 07-final-report.md
artifacts/ui-upgrade/{before,after}/
```

`AGENTS.md`、`package.json`、`package-lock.json`、既有 E2E/Playwright/skill/artifact 目录在任务开始前已处于修改或未跟踪状态；本轮没有 reset、checkout、commit 或 push。未修改后端源代码、数据库迁移、审核/发送/权限门禁。

## 6. 复用组件

- Ant Design：Layout、Menu、Button、Input/Search、Select、Tabs、Tag、Alert、Card、Table、List、Drawer、Modal、Form、DatePicker、Descriptions、Collapse、Empty/Result；
- 项目组件：TaskTable、MetricStrip、AiAssistant、StatusTags；
- 既有 API client、React 本地 state/effect、History API 和当前 theme token。

## 7. 新增公共组件

- `PageHeader`：统一页面标题、说明、元数据和主动作；
- `DataBoundaryBanner`：demo/api/pending/unavailable/stale 可信边界；
- `ResponsiveCollection<T>`：桌面/紧凑/移动集合 renderer；
- `StatePanel`：loading/empty/filtered-empty/error/permission/unavailable；
- `UnavailableState`：目的、限制、后端缺口与安全替代路径；
- `navigation.ts`：受控 URL parse/build/navigate/popstate，不新增 Router 依赖。

## 8. 修复的功能问题

- 死全局搜索、死顶栏控制、死模板按钮和假安全开关；
- URL 恒为 `/`、无法深链、刷新/后退丢失；
- Matter 假/弱筛选、active filter 不可见、返回丢 query；
- Matter 缺少稳定排序、分页和返回滚动恢复；现已实现前端 12 项分页，并明确只处理 API 前 100 项；
- Inbox 延迟响应串 Candidate、人工修改可能被旧响应干扰；
- 子资源失败被误显示为空；
- 依赖表单可提交空业务对象；
- 审核中心把最旧 ReviewRecord 当最新；
- Agent completed 缺少移动端法律确认边界；
- 未声明 fixture method/path 未 fail closed；
- 390 表格裁切、模板逐字换行、未接入按钮溢出；
- Card 旧 API、DOM nesting、Descriptions span、useForm 连接警告；
- 进入外发队列被误读为已发送、Agent 技术完成被误读为法律确认的语义风险；
- 审核中心无法核对真实外发目标、返回事项绕过未保存保护、驳回/补充信息可无理由提交；
- 缺失材料没有承接到首个任务，Matter 首屏缺等待/阻塞/硬期限；
- Deadline/Dependency 的 401/403/409 被混成普通错误；
- 长审核 Dialog 在 1440×900 下裁切 footer。

## 9. 响应式结果

- 1440：228px 常驻侧栏和高密度语义表格；
- 1024：72px 折叠侧栏，队列改为紧凑记录；
- 390：移动顶栏和导航 Drawer，Matter/Review/Agent 使用卡片，Inbox 分步，Dialog/Drawer 接近全屏；
- Playwright MCP 逐一记录 30 个 page/viewport 组合：页面级 overflow 0；
- after 额外保留移动导航、Inbox 详情/Drawer/validation、Matter 两类 Dialog、Review/Agent 详情证据。

## 10. 无障碍结果

- 图标按钮和显式记录入口具有可读 label；
- 主操作与移动触控目标至少 44px；
- 风险/错误/选中/禁用不只依赖颜色；
- `focus-visible` 明确，Tab 导航测试通过；
- 390 validation/footer 可达，JSON 只在局部滚动；
- Drawer dirty-close 测试验证焦点恢复。

限制：未新增 axe 依赖，尚未进行屏幕阅读器人工实机和完整 WCAG 2.2 审计。

## 11. 测试命令与真实结果

```text
npx playwright test --reporter=line
85 passed (33.7s)

npm run typecheck
passed

npm run build
passed

.venv/bin/python -m ruff check apps/backend/src apps/backend/tests
passed

.venv/bin/python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
passed; 69 source files

PYTHONPATH=apps/backend/src .venv/bin/python -m pytest apps/backend/tests
63 passed, 2 skipped, 281 warnings

git diff --check
passed
```

仓库未配置 npm lint 或独立 frontend unit 脚本。后端 pytest 的直接命令受到本地 editable `.pth` 指向旧 worktree 的环境污染；明确当前仓库 `PYTHONPATH` 后通过。本轮未修改虚拟环境。

## 12. Before / After 截图

- Before：`artifacts/ui-upgrade/before/`，38 个文件；
- After：`artifacts/ui-upgrade/after/`，38 个文件；
- 核心格式：`<route-name>/{1440,1024,390}.png`；
- 详细状态清单见 `06-functional-qa.md`。

## 13. Bundle 变化

| 指标 | 基线 | 最终 | 说明 |
|---|---:|---:|---|
| 首个/唯一 JS | 1,308.32 kB / gzip 411.75 kB | entry 675.64 kB / gzip 217.91 kB | 主入口 gzip 约下降 47%，页面按 route 懒加载 |
| 全部 JS | 1,308.32 kB / gzip 411.75 kB | 1,379.09 kB / gzip 约 453.20 kB | 功能和状态覆盖增加；总 gzip 约增加 10% |
| CSS | 21.76 kB / gzip 4.89 kB | 39.39 kB / gzip 约 7.69 kB | 全页面响应式、公共状态和长 Dialog 视口约束增加 |
| JS chunks | 1 | 25 | Dashboard/Inbox/Matters/Detail/Reviews/Agent/Templates/Security 与共享状态 helper 动态 chunk |

仍有共享 entry 675.64 kB > 500 kB 的 Vite 警告，主要来自 React/Ant Design 共享运行时。本轮没有证据支持手工 vendor 分包，未引入不必要的 `manualChunks`；没有新增运行时依赖或大图片/字体资源。

## 14. 未解决的低优先级问题

- Figma Starter MCP 配额阻止原生设计系统和最终 Frames 写入；需配额恢复后按 03/04 文档回填；
- 共享 entry 仍大于 500 kB；需要后续用真实加载 profile 决定是否拆 vendor；
- 当前 `.venv` editable-install `.pth` 指向旧 worktree；建议单独重建或重新 editable install，但本轮未获授权修改环境；
- Python 3.14 下 pytest 产生 Starlette/pytest-asyncio deprecation warnings；不影响本轮 UI 结果；
- 未进行 axe、屏幕阅读器实机、真实触控设备和生产数据规模性能测试；
- 后端当前没有正式的服务端排序/分页契约；界面只提供明确标注的客户端排序与分页，并限定在 API 返回的前 100 项；
- 审核队列和系统页仍保留部分技术原码/技术 ID；后续可移入技术信息折叠区；
- Matter 详情桌面仍有局部卡片嵌套；不影响核心流程；

## 15. 尚需后端支持

- Files 的存储、检索、附件权限和版本；
- 系统版本、连接、运行状态、授权范围、同步/队列健康、审计事件和留存策略接口；
- Inbox 中关联/更新、补充材料、仅作信息、忽略、暂缓、合并等正式处置；
- 真实 Communication 发送结果、失败重试和回执展示；
- 全列表权限、stale/version、排序/分页契约的统一接口；
- 生产级 Feishu/Codex 联调、数据库并发和多用户权限验收。

## 完成门槛核对

代码、浏览器和自动化层面的完成门槛已满足：全部现有 route 已盘点与升级，关键工作流可完成或安全禁用，三视口无页面级溢出，无虚假在线/同步状态，typecheck/build/85 条 Playwright/diff-check 通过，before/after 证据完整。最终 UX/IA 为 0 blocker / 0 high / 0 核心 medium；独立视觉 QA 为 0 blocker / 0 high / 0 核心 medium，30/30 基础截图和 6/6 稳定 Overlay 已复核。Figma 原生交付未完成是已明确记录的外部配额限制；本报告不把该限制伪装为完成。
