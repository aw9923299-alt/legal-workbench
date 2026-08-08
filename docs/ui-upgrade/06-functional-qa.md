# Legal Workbench 功能与浏览器验收

验收日期：2026-08-04
验收对象：当前未提交工作树；未连接生产数据
浏览器证据：Playwright MCP + 仓库 Playwright 测试；全部业务请求使用安全确定性夹具

## 1. 验收结论

十个现有逻辑页面及应用壳均已在 1440×900、1024×768、390×844 下复验。30 个 page/viewport 组合的 `documentElement.scrollWidth` 均未超过 viewport；最终 Playwright MCP 独立视觉审查完成 30/30 基础截图与 6/6 稳定 Overlay。主 Agent 的最终 MCP console 抽查只出现 React DevTools 开发环境 `INFO`，没有 warning/error。

专项交互检查先后发现并修复：模板页 heading 非法嵌套、Agent 详情 `Descriptions` span 警告、Matter 弹窗 `useForm` 未连接、390px 模板内容逐字换行、未接入页替代按钮超出卡片、真实外发目标未显示、审核返回事项绕过 dirty guard、缺失材料/等待阻塞跨页断点、子资源 401/403/409 混入普通错误，以及长审核 Dialog footer 超出视口。以上问题均有自动化回归或最终 MCP 复验。

本结论仅证明当前代码和安全夹具下的 UI 契约，不证明真实飞书连接、Codex 运行、生产权限、真实外发或实时系统健康。

## 2. 路由验收矩阵

| URL | 页面 | 关键检查 | 三视口结果 | 证据目录 |
|---|---|---|---|---|
| `/today` | 今日工作台 | 行动先于统计、Tabs、消息入口、AI/演示标识、焦点 | 通过；390 首条任务含风险与主操作 | `after/dashboard/` |
| `/inbox`, `/inbox/:candidateId` | 待确认消息 | 队列/详情、证据、AI 推断、缺失材料、重新分析、确认 Drawer、dirty/validation/409/重复提交 | 通过；390 队列→详情→全屏 Drawer 可返回 | `after/inbox/` |
| `/matters` | 事项中心 | 关键词、分类/风险/状态/负责人、active filters、排序、客户端分页、URL query、滚动恢复、空/错、详情返回 | 通过；1440 表格、1024 紧凑记录、390 MatterCard；明确仅处理 API 前 100 项 | `after/matters/` |
| `/matters/:matterId` | 事项详情 | 风险/状态/负责人/目标、等待/阻塞/期限/依赖、子资源 loading/error/permission/stale/empty、priority/deadline/dependency/review Dialog、dirty/validation/重复提交 | 通过；390 首屏决策摘要可见；长 Dialog footer 三视口可达 | `after/matter-detail/` |
| `/reviews`, `/reviews/:reviewPackageId` | 审核中心 | 真实外发目标、未知目标阻断、最新审核记录、固定阅读顺序、决定/最终正文、dirty/理由校验、approved-only 入队、queued≠sent、返回/后退 | 通过；1024/390 使用 ReviewCard | `after/reviews/` |
| `/templates` | 事项模板（演示） | 演示来源、分类入口真实生效、新建/配置安全禁用、无 DOM nesting 警告 | 通过；390 元数据和动作不再逐字换行 | `after/library/` |
| `/files` | 合同与文件未接入 | 目的、限制、后端缺口、安全替代路径 | 通过；替代按钮在 390 内换行 | `after/files/` |
| `/system/agent-runs`, `/:runId` | Agent 执行记录 | 中文语义+原码、completed≠法律确认、深链、JSON 局部滚动、返回 | 通过；1024/390 RunCard，无 `Descriptions` 警告 | `after/agents/` |
| `/system/data-boundaries` | 数据边界 | 无伪在线/连接/同步/成功/数量，无 Switch/死按钮，代码约束与接口缺口分离 | 通过；390 关键“不可验证”说明保持可见 | `after/security/` |
| `/system/about` | 系统信息未接入 | 目的、限制、后端缺口、安全替代路径 | 通过；390 操作不溢出 | `after/settings/` |

`/` 使用 replace 导向 `/today`；未知 URL 显示独立 unavailable 状态和安全返回入口。

## 3. 关键流程

### A. 消息转法律事项

`/today` → `/inbox` → Candidate → 证据/上下文/AI/缺失材料 → 人工修改 → validation → 确认创建 → `/matters/:id`。

- Dashboard 主操作和消息条目均进入真实 Inbox URL；
- Candidate ID 可深链、刷新恢复、浏览器后退；
- 延迟响应不会把旧 Candidate 证据混入当前确认；
- 人工编辑不会被 retry、409 或失败响应静默覆盖；
- 非 `create_matter` 建议继续阻止创建；未接入处置不伪造完成；
- 成功夹具证明只提交一次人工修改后的 payload，并进入返回的 Matter ID。

### B. 处理法律事项

`/matters` → detail → 风险/期限/依赖 → priority/deadline/dependency → review package → `/reviews` → 审核决定 → communication queued。

- WorkItem 子资源的加载、空、失败和重试彼此独立；
- 期限/依赖的 401、403、409 使用 permission/stale 语义，失败时不把期限写成“当前未记录”；
- 表单 dirty close 有二次确认，提交中同步 ref 阻止同帧重复；
- dependency 至少要求前置任务、等待对象或说明之一；
- review package 只创建待审核记录；
- 创建成功后直达审核详情；审核页可返回 Matter，dirty 返回同样受放弃确认保护；
- 只有 approved 包可请求外发入队，且 UI 始终写明“进入队列不等于已发送”。

### C. 搜索和筛选

Playwright MCP 实际操作结果：

```text
输入不存在 → /matters?source=final-qa&q=不存在 → 筛选空状态
清除全部 → /matters?source=final-qa
选择文案合规 → /matters?source=final-qa&category=copy_review
打开详情 → /matters/matter-demo-1
返回 → /matters?source=final-qa&category=copy_review
```

未知 query 参数在改变筛选、清除和详情返回时保持。Matter 列表提供稳定客户端排序、12 项分页、`sort/page` URL 与详情返回滚动恢复；界面明确该能力只作用于服务返回的前 100 项，不冒充服务端分页。Dashboard 的行动队列仍按既有优先级规则排序并有一致性测试。

### D. 移动端

- 移动导航 Drawer 可打开、关闭并进入全部现有页面；
- Inbox 采用队列→详情→全屏确认 Drawer，不把三栏桌面强行缩小；
- Matters/Reviews/AgentRuns 在 390 使用语义卡片；
- 主触控目标至少 44px，焦点 outline 可见；
- Dialog footer、validation、局部 JSON 滚动可达；
- 30 个规定 page/viewport 组合没有页面级横向溢出。

## 4. 状态、门禁与可信度

| 状态 | 验收结果 |
|---|---|
| loading / true empty / filtered empty | 使用独立 `StatePanel` 或页面状态；测试不允许旧数据冒充成功 |
| error / retry | API 页面显示错误和重试；不静默回退 mock |
| permission denied | Inbox 的 403 与普通错误分离；未获支持的页面不合成权限事实 |
| stale / conflict | Candidate 409 保留人工输入并要求重新核对 |
| unsaved changes | Inbox Drawer、Matter Dialog、Review Dialog 均有放弃确认 |
| duplicate submit | confirmation、priority、dependency、review、queue 均有同步 ref/disabled guard |
| AI suggestion | 明确“AI 建议/提取，待人工确认”，不冒充法律决定 |
| human decision | 审核决定、最终正文、版本与审核记录独立展示 |
| system state | AgentRun technical status、communication queued 与法律/发送结果分离 |
| unavailable | Files/About 明确目的、限制、后端缺口和安全替代路径 |

## 5. 无障碍与键盘

- 关键图标按钮具有可读 label；移动导航具有 `aria-label="主导航"`；
- 表格标题使用可聚焦按钮，不把整行鼠标点击作为唯一入口；
- 风险、错误、选中和禁用均含文字，不只依赖颜色；
- `focus-visible` 为 2px 主色 outline + 2px offset；
- Playwright 从 Tab 导航验证单一可见焦点；
- Drawer/Modal 使用 Ant Design focus trap；Inbox dirty-close 测试验证关闭后触发器焦点恢复；
- 390px validation 和 Modal footer 可见，未被遮挡。

低优先级边界：本轮没有引入 axe 等额外依赖；结论来自语义 locator、键盘测试、截图和人工检查，不等同于完整 WCAG 审计。

## 6. Console、网络与弃用

- 最终 Playwright MCP 全路由三视口巡检：console warning/error 0，requestfailed 0；
- 最终关键 Drawer/Dialog 巡检：console warning/error 0；
- 已修复 `Card bordered` 弃用、模板 heading DOM nesting、Agent `Descriptions` span、Matter `useForm` 连接警告；
- API fixture 默认 fail closed：未声明 path/method 返回 501，并在 afterEach 断言异常请求台账为空；
- 数据边界页额外证明它不会悄然访问未声明的健康状态接口。

## 7. 自动化与工程命令

| 命令 | 真实结果 |
|---|---|
| `npx playwright test --reporter=line` | 85 passed（33.7s，exit 0） |
| `npm run typecheck` | passed |
| `npm run build` | passed；保留一个共享 entry chunk >500 kB 警告 |
| `.venv/bin/python -m ruff check apps/backend/src apps/backend/tests` | passed |
| `.venv/bin/python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src` | passed，69 source files |
| `PYTHONPATH=apps/backend/src .venv/bin/python -m pytest apps/backend/tests` | 63 passed, 2 skipped |
| `git diff --check` | passed |
| lint | 仓库未配置 npm lint 脚本；后端 Ruff 已运行 |
| frontend unit | 仓库未配置独立前端 unit 脚本；行为由 Playwright 覆盖 |

直接运行 `.venv/bin/python -m pytest` 时，本地 editable-install `.pth` 指向另一个旧 worktree，错误导入旧代码并因其额外 `docx` 依赖而在收集阶段失败。用当前仓库明确 `PYTHONPATH=apps/backend/src` 后测试通过。本轮未改 `.venv`、未安装依赖；该环境漂移在最终报告列为低优先级维护项。

## 8. 截图清单

基线：`artifacts/ui-upgrade/before/`，38 个文件。
最终：`artifacts/ui-upgrade/after/`，38 个文件。

每个核心 route-name 均有 `1440.png`、`1024.png`、`390.png`：

```text
dashboard inbox matters matter-detail reviews library files agents security settings
```

额外 after 状态证据：

```text
navigation/390-drawer.png
inbox/390-detail.png
inbox/390-drawer.png
inbox/390-validation.png
matter-detail/1440-priority-dialog.png
matter-detail/1440-review-dialog.png
reviews/1440-dialog.png
agents/1440-dialog.png
```

## 9. 尚未由本轮证明

- 真实飞书授权范围、同步、消息覆盖和外发结果；
- 真实 Codex Runtime 运行与法律结论正确性；
- 生产权限、审计日志、健康度、留存和删除策略；
- Files、系统信息及未接入处置动作的后端能力；
- 真实多用户并发、网络抖动、生产数据库和外部服务性能。
