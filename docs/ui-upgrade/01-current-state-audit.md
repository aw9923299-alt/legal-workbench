# Legal Workbench 当前状态审计

更新时间：2026-08-04
目标 URL：`http://127.0.0.1:4173/`
浏览器：Playwright MCP / Chromium
数据：显式 `X-Safe-Demo-Fixture: true` 安全演示夹具；所有非 GET 请求返回 409，未访问生产数据

## 1. 审计范围与证据

已遍历全部 10 个可达逻辑页面/状态：Dashboard、Inbox、Matters、Matter Detail、Reviews、Library、Files placeholder、Agents、Security、Settings placeholder。

每个页面均在以下视口保存截图：

- 1440×900：`artifacts/ui-upgrade/before/<route>/1440.png`；
- 1024×768：`artifacts/ui-upgrade/before/<route>/1024.png`；
- 390×844：`artifacts/ui-upgrade/before/<route>/390.png`。

附加状态证据：

- 移动导航：`before/navigation/390-drawer.png`；
- Inbox 移动详情、确认 Drawer、validation；
- Matter Detail 优先级 Modal、审核包 Modal；
- Review 审核 Modal；
- AgentRun 详情 Modal；
- Console 与 Network 记录。

共保存 40 份 baseline 文件。

## 2. 总体评价

当前界面已有明确的企业法务语义和相对克制的蓝灰色基础；Inbox 对“来源证据、AI 推断、缺失材料、人工确认”的分层已经明显优于普通 AI Dashboard。主要问题不在颜色，而在系统完整性：页面没有真实 URL 路由，多个页面仍是静态 mock 或死控制，移动端表格不可用，安全页存在未经验证的成功事实，页面模板与状态术语不一致。

## 3. Findings

### Blocker

基线未发现整个应用无法启动、页面级横向溢出或核心 Inbox 完全不可用的 blocker。

### High

#### UI-BASE-H01 — 安全页把 mock 当成已验证运行事实

- Route / viewport：`security`，全部视口；390 证据：`before/security/390.png`；
- 区域：连接状态、授权会话、审计日志、安全策略；
- 观察：显示绿色“正常”、42 个群聊、7 个私聊、“成功”，且 Switch 默认开启；页面没有演示声明或数据来源；
- 期望：没有真实系统状态 API 时只能显示“未接入 / 待核验 / 演示规则”，不能用绿色成功；
- 建议：改为能力边界与静态策略说明，所有不可执行动作明确禁用并解释后端缺口。

#### UI-BASE-H02 — 390 宽度下三个关键数据页面不可读

- Route / viewport：`matters`、`agents`、`security`，390×844；
- 证据：`before/matters/390.png`、`before/agents/390.png`、`before/security/390.png`；
- 观察：桌面表格列被压成逐字换行或裁切，负责人、状态、操作不可扫描；
- 期望：移动端使用任务卡/结构化列表，保留事项、风险、期限、负责人和下一步；
- 建议：提供共享 ResponsiveList / MobileRecordCard，表格仅用于桌面。

#### UI-BASE-H03 — 无真实路由、深链或浏览器返回语义

- Route / viewport：全部；
- 证据：所有页面 URL 始终为 `/`；
- 观察：导航、列表详情和 AgentRun 详情只改变内存 state；刷新丢失位置，浏览器返回不能回到队列上下文；
- 期望：页面可深链，返回保留搜索与筛选；
- 建议：在不新增 UI 框架的前提下建立确定性 pathname/history 路由层，或引入现有批准的轻量 router。

#### UI-BASE-H04 — 启用状态的死控制过多

- Route：应用壳、Dashboard、Library、Security；
- 证据：源码与浏览器点击核对；
- 观察：全局搜索、待核验状态、AI 图标、通知、Dashboard 消息行、Library 新建/配置/查看、Security 暂停/授权/Switch 均无行为；
- 期望：每个控制有真实行为，或明确禁用、标注演示和说明原因；
- 建议：能安全导航的接真实导航；无后端支持的禁用并显示原因；不要保留伪交互。

### Medium

#### UI-BASE-M01 — 页面模板与信息密度不一致

- Route：Dashboard、Reviews、Library、Detail；
- 观察：Dashboard 很长且信息密集，Reviews 只有一张小卡片，Library 每类一张重复大卡；
- 期望：工作台、工作队列、详情、设置、审核使用稳定模板；
- 建议：统一 PageHeader、FilterBar、QueueSurface、DetailRail、StatePanel。

#### UI-BASE-M02 — 状态和类型直接显示后端英文原码

- Route：Matters、Reviews、Agents、Detail；
- 观察：`in_progress`、`pending_review`、`external_message`、`completed` 与中文术语混排；
- 期望：展示层统一中文标签，保留原码只用于技术详情；
- 建议：集中 status dictionary，避免页面内零散判断。

#### UI-BASE-M03 — Matters 只有关键词搜索，没有完整队列控制

- Route：`matters`；
- 观察：关键词过滤真实有效，但没有风险、状态、负责人、期限筛选，没有排序，没有 active filter 和清空；
- 期望：队列可按真实法律工作维度筛选，返回后保留上下文；
- 建议：实现本地可验证筛选与 URL query state；不宣称后端全量搜索。

#### UI-BASE-M04 — 子资源错误被静默吞掉

- Route：`matter-detail`；
- 观察：期限/依赖请求 `.catch(() => undefined)`，用户不知道信息缺失；
- 期望：局部错误有明确提示和重试，不把失败误解为空；
- 建议：WorkItemCard 记录 deadline/dependency loading/error，并提供局部重试。

#### UI-BASE-M05 — 事项库将未实现能力写成可配置

- Route：`library`；
- 观察：静态模板显示“可配置”，按钮处于可点击状态；
- 期望：明确这是演示模板目录或后端缺口；
- 建议：保留真实存在的模板样例，但禁用创建/配置；“查看事项”可以真实跳转并带分类筛选。

#### UI-BASE-M06 — Dialog / Drawer 内容与移动宽度未系统统一

- Route：Inbox、Matter Detail、Reviews、Agents；
- 证据：附加 state screenshots；
- 观察：Inbox Drawer 已适配 390；其他 Modal 使用固定 760/900 宽度，内容表格/JSON 在窄屏风险高；
- 期望：所有 Modal/Drawer 使用共享响应式宽度和可滚动内容区；
- 建议：统一 `ResponsiveModal` 约束与 footer 布局。

#### UI-BASE-M07 — Ant Design 弃用警告

- Route：Matters、Detail、Reviews、Library、Agents、Security；
- 证据：`before/console.log`；
- 观察：`[antd: Card] bordered is deprecated`；
- 期望：当前页面无影响渲染的弃用警告；
- 建议：统一改为 `variant="borderless"` 或明确边框 variant。

#### UI-BASE-M08 — 单包体积过大且无页面懒加载

- 证据：baseline build；
- 观察：JS 1,308.32 kB，gzip 411.75 kB，Vite chunk warning；
- 期望：系统页按页面懒加载，避免一次加载所有 Ant Design 页面；
- 建议：以页面级 `React.lazy` 分包，并测量前后差异。

### Low

#### UI-BASE-L01 — favicon 404

- 证据：浏览器 Console；
- 影响：不影响核心任务，但产生噪声；
- 建议：补充本地 favicon 或移除引用。

#### UI-BASE-L02 — Dashboard 全页过长

- Route / viewport：Dashboard 390；
- 证据：`before/dashboard/390.png`；
- 观察：核心队列之后仍堆叠节点、消息、AI、周概览；
- 建议：移动端优先保留行动队列，将次级模块折叠或后置。

#### UI-BASE-L03 — 顶栏部分图标无可访问名称

- Route：全局；
- 观察：通知、AI 图标主要依赖 icon/tooltip，读屏名称不稳定；
- 建议：所有 icon button 添加稳定 `aria-label`。

## 4. 关键流程基线

| 流程 | 基线结果 | 证据 / 缺口 |
|---|---|---|
| 今日工作台 → 待确认消息 | 可完成 | 主按钮进入 Inbox；URL 不变 |
| Inbox 队列 → 证据研判 | 可完成 | Desktop 双栏，Mobile 队列/详情分步 |
| 修改 AI 提取结果 | 可完成 | Drawer 可编辑并明确“AI 建议，可人工修改” |
| 人工确认 → 创建事项 | 未执行持久化写入 | 安全夹具阻止写入；现有 e2e 验证 validation/cancel，不声称真实后端写入通过 |
| Matters 搜索 | 可完成 | 关键词真实过滤；无筛选/排序/active filter |
| 列表 → 详情 → 返回 | 页面按钮可完成 | 浏览器返回与深链不成立 |
| Mobile navigation | 可完成 | Drawer 入口和关闭可用 |
| 表单验证 | 可完成 | Inbox 必填/日期 validation 可见 |
| Dialog / Drawer | 可打开、取消 | 其他页面小屏适配不足 |
| 未验证在线/同步状态 | 不通过 | Security 仍显示绿色正常和静态数量 |

## 5. 状态检查

- Loading：Inbox、Matters、Detail、Reviews、Agents 有；Dashboard/Library/Security 无异步状态；
- Empty：Live 列表基本有；文案普遍只写“暂无”，缺少恢复路径；
- Error：Live 页面有顶层错误；Detail 子资源错误静默；
- Permission denied：只有 Inbox 区分 401/403；
- Stale data：Inbox 有重试 freshness barrier；其他页面没有更新时间/陈旧状态；
- Disabled：Inbox 未接入处置动作有明确后端缺口；其他 mock 页面做得不足；
- Unsaved changes：长表单关闭时没有离开保护；
- Destructive confirmation：当前可见危险操作多为死按钮；正式写入 Modal 具备显式确认，但安全页“暂停全部同步”无确认且无行为。

## 6. Console 与 Network

- Console：1 个 favicon 404；1 个 Ant Design Card `bordered` 弃用警告；无页面崩溃；
- Network：安全夹具请求均 200；无生产访问；
- 开发模式 effect 请求通常出现两次，来源是 React StrictMode；必须在生产构建/自动化中区分 dev-only 重放与真实重复提交；
- 写请求：本次手工基线未发出；夹具会将任何非 GET 请求以 409 拦截。

## 7. 基线工程检查

| 命令 | 结果 |
|---|---|
| `npm run typecheck` | 通过 |
| `npm run build` | 通过；有单包体积警告 |
| `git diff --check` | 通过 |
| Playwright 全套 | 阶段 12 统一运行；当前已有 Dashboard/Inbox 夹具测试 |

## 8. 当前结论

当前版本可以作为 Inbox 研判与桌面工作台原型，但不能作为系统级产品完成版。实施优先级应为：消除虚假状态与死控制 → 建立真实路由和返回语义 → 修复移动数据视图 → 统一模板/状态组件/术语 → 补齐筛选、局部错误、响应式 Dialog → 最后处理懒加载和视觉细节。
