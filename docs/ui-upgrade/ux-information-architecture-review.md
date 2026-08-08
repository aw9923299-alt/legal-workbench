# Legal Workbench UX / 信息架构终审与修复复审

更新时间：2026-08-04
审查角色：`ux_information_architect`
审查范围：最终前端实现、修复后代码、`artifacts/ui-upgrade/after/`、`docs/ui-upgrade/02-information-architecture.md`、现有 Playwright 用例
审查方式：只读；未修改应用源代码

## 1. 结论

当前实现已经把产品从展示型 Dashboard 收敛为较可信的“安静的法务运营控制台”，并完成了真实 URL、Matter 查询条件恢复、移动端记录卡、AI 与人工决定分离、API 错误不回退 mock、已批准后才能外发入队等关键基础。

最终复核确认原 **H1、M1-M6 全部关闭**，且本轮修复没有引入新的核心流程问题。后续独立视觉 QA 又补齐了移动导航稳定截图，因此当前未解决严重度为：**0 blocker / 0 high / 0 影响核心流程 medium / 3 low**。

从 UX / 信息架构代码和合约测试范围看，完成门槛已经达到。最终视觉放行仍由独立 `visual_qa_reviewer` 基于真实页面和最新截图决定；本报告没有使用 Playwright MCP，也不替代该视觉验收。

### 修复状态总表

| 原发现 | 最终状态 | 当前严重度 | 复审结论 |
|---|---|---|---|
| H1 外发目标不可核对 | 已关闭 | 无 | 真实 `replyToMessageId` / `receiveId` 已显示；未知目标阻止批准和入队。 |
| M1 审核包流程断点 | 已关闭 | 无 | 创建成功直达 `/reviews/:id`，并提供返回事项路径。 |
| M2 审核编辑保护与理由校验 | 已关闭 | 无 | “返回审核队列”和“返回事项”共用同一 dirty guard；理由校验继续生效。 |
| M3 缺失材料、等待与阻塞连续性 | 已关闭 | 无 | 缺失材料预填下一步并明确依赖需后补；详情展示等待/阻塞完整字段。 |
| M4 权限、陈旧与普通错误区分 | 已关闭 | 无 | 主列表、详情、Deadline 和 Dependency 均区分 401/403/409 并清空旧摘要。 |
| M5 390 首屏等待/阻塞语义 | 已关闭 | 无 | 行动任务前移到事项背景之前；风险、负责人、下一步、期限、等待和阻塞通过 viewport 断言。 |
| M6 排序、页码与滚动恢复 | 已关闭 | 无 | 在 API 前 100 项窗口内实现 URL 排序、分页和详情往返滚动恢复。 |

## 2. 证据边界

- 已审查 `after` 目录中的 38 张实现截图，覆盖 Today、Inbox、Matters、Matter Detail、Reviews、Templates、Files、Agent Runs、Data Boundaries、About 及若干 Drawer/Dialog 状态。
- 第一轮已独立运行针对 H1、M1-M6 的 10 个 Playwright CLI 安全夹具测试，结果为 `10 passed (16.1s)`；最终轮另运行 M2、M4、M5 及审核校验的 4 个精准测试，结果为 `4 passed (7.0s)`。均未使用 Playwright MCP，也没有连接生产数据。
- 为避免与并行 `visual_qa_reviewer` 争用浏览器，本轮未再次控制 Playwright MCP 浏览器。
- 当前 `after` 截图和 `06-functional-qa.md` / `07-final-report.md` 生成时间早于 H1、M1-M6 的最新修复；例如 Review 390 截图仍显示目标 `—`。因此这些旧截图不能证明最新修复的视觉结果，必须由 `visual_qa_reviewer` 重新复验。
- Figma 文件当前只有空白 `Page 1`，且 Figma MCP 写入受 Starter plan 调用额度限制；`docs/ui-upgrade/03-figma-design-map.md` 已如实记录没有原生 Frames、Components 或 Ready for development 标记。因此本轮无法进行逐 Frame 的设计—实现对照，只能按设计文档、代码和最终截图审查。

## 3. 核心流程核对

| 流程 | 结果 | 证据与判断 |
|---|---|---|
| 今日工作台 → 待确认消息 | 通过 | Today 主动作进入 `/inbox`；演示数据边界明确，未声称实时在线。 |
| 待确认消息 → 证据研判 → 人工修改 | 通过 | Source、ContextSnapshot、AI 推断、缺失信息和人工门禁分区明确；非 `create_matter` 动作被安全禁用。 |
| 人工确认 → Matter + WorkItem → 事项详情 | 通过 | 单次确认创建 1 个 Matter 与 1 个 WorkItem，成功后进入 `/matters/:matterId`；409/失败不覆盖人工编辑。 |
| 缺失材料 → 新事项继续跟进 | 通过 | 缺失材料在确认 Drawer 中复显并预填到下一步；明确说明当前 API 不自动创建 Dependency，创建后需人工补充。 |
| Matter 队列 → 详情 → 返回上下文 | 通过 | q/category/risk/status/owner/sort/page 写入 query，并在 API 前 100 项窗口内恢复排序、页码和滚动位置。 |
| Matter 详情 → ReviewPackage | 通过 | 创建审核包有字段校验、dirty guard、重复提交保护，并明确“进入待审核，不会直接发送”。 |
| ReviewPackage → 人工审核 → Communication 入队 | 通过 | 外发目标、approved-only 入队、创建后直达、审核理由校验及所有离开路径的 dirty guard 均已覆盖。 |
| 移动端导航和核心操作 | 通过 | 390 使用移动导航、Inbox 分步、记录卡和全宽 Overlay；Matter 首屏保留风险、负责人、下一步、期限、等待和阻塞。 |

## 4. Blocker

无。

## 5. 原 High（已关闭）

### H1. 审核中心无法显示真实外发目标，破坏人工审核门禁

- 最终状态：**已关闭**。

- 路由：`/reviews`、`/reviews/:reviewPackageId`
- 视口：1440 / 1024 / 390
- 证据：
  - 创建审核包使用 `target.replyToMessageId` 或 `target.receiveId`：`apps/web/src/pages/TaskDetailPage.tsx:246-248`；
  - 后端也以 `replyToMessageId` / `receiveId` 作为真实外发目标：`apps/backend/src/legal_workbench/domain/entities.py:568-570`；
  - 审核队列和移动卡只读取 `target.recipient ?? target.chatId`：`apps/web/src/pages/ReviewCenterPage.tsx:205`、`:233`；
  - 审核详情没有单独展示 target；
  - `artifacts/ui-upgrade/after/reviews/1440.png` 的“目标”为 `—`。
- 影响：法务无法在批准最终正文前验证收件人或原消息，可能批准正确正文但发往错误目标。该问题直接违反“批准版本与发送版本一致”和人工外发审核的安全目的。
- 修复建议：
  1. 建立共享 `formatCommunicationTarget()`，按 `replyToMessageId`、`receiveId + receiveIdType`、`chatId`、`recipient` 的顺序显示；未知结构显示“无法识别目标”，不能显示为普通空值；
  2. 在队列和审核详情的首屏同时展示“回复原消息”或“收件人”；
  3. approved 决定前必须可见，必要时把缺失/不可识别目标作为阻断条件；
  4. Playwright 同时覆盖 `replyToMessageId` 和 `receiveId` 两种真实结构，并断言目标不为 `—`。

修复复审证据：

- `apps/web/src/services/communicationTarget.ts` 统一格式化真实 target；
- Review 队列、移动卡和详情均显示真实目标；未知目标明确显示“无法识别目标”；
- 批准类决定和入队动作都检查 `recognized`，未知目标不能批准或入队；
- 对应 `replyToMessageId`、`receiveId`、unknown target 合约测试通过。

## 6. 原 Medium（全部关闭）

### M1. “创建审核包 → 进入审核”没有连续路径，形成流程断点（影响核心流程）

- 最终状态：**已关闭**。

- 路由：`/matters/:matterId` → `/reviews/:reviewPackageId`
- 视口：全部
- 证据：`legalApi.createReviewPackage()` 返回 `reviewPackageId`，但 `TaskDetailPage.createReviewPackage()` 忽略返回值，只关闭 Dialog 并显示 toast（`apps/web/src/pages/TaskDetailPage.tsx:218-255`）；审核队列中的 `matterId` 也是不可交互文本（`ReviewCenterPage.tsx:203`、`:231`）。
- 影响：用户必须手动切换到审核中心并在无筛选的队列中寻找刚创建的审核包；审核页也不能直接回到事项上下文。这是 Matter 详情和审核中心之间的页面孤岛。
- 修复建议：创建成功后提供“前往审核”主路径并使用返回状态保留事项详情；审核队列的事项编号可聚焦打开对应 Matter。不要自动批准或自动入队。

修复复审证据：`TaskDetailPage` 使用返回的 `reviewPackageId`；`App.tsx` 直达 `/reviews/:reviewPackageId`；审核详情提供“返回事项”。合约测试完成创建 → 审核详情 → 返回事项往返。

### M2. 审核决定编辑没有未保存保护，决定理由校验不足（影响核心流程）

- 最终状态：**已关闭**。

- 路由：`/reviews/:reviewPackageId`
- 视口：全部，移动端风险更高
- 证据：Review Drawer 的 `onClose` 直接调用 `onReviewClosed`，没有 dirty state 或放弃确认；`canSubmit` 只要求通过类决定保留最终正文，`rejected` 和 `needs_information` 可在审核意见为空时提交（`ReviewCenterPage.tsx:145-166`、`:288-298`、`:327-342`）。
- 影响：误触遮罩、关闭键或返回会丢失人工修改；驳回/要求补充信息可能形成没有理由、难以审计和执行的审核记录。
- 修复建议：复用事项表单的 dirty guard 与焦点恢复；`rejected`、`needs_information` 必填审核意见，`approved_with_edits` 必填修改原因或 change summary；保持重复提交保护。

修复历程：理由校验、重复提交保护和“返回审核队列” dirty guard 先行完成；上一轮发现“返回事项”仍可绕过。最终实现新增统一 `requestReviewNavigation()`，`requestReviewClose()` 与 `requestMatterNavigation()` 均通过同一保护。精准测试覆盖 clean 时直接返回、dirty 时继续审核保留内容、确认放弃后返回事项，结果通过。

### M3. 缺失材料、等待对象和阻塞原因没有形成跨页面连续信息（影响核心流程）

- 最终状态：**已关闭**。

- 路由：`/inbox/:candidateId`、`/matters/:matterId`
- 视口：全部
- 证据：
  - Inbox 显示 `judgement.missingInformation`，但确认 Drawer 的上下文和 `ConfirmCandidateInput.initialWorkItems` 不包含缺失材料/等待对象（`InboxPage.tsx:611`、`:659-745`；`services/api.ts:165-186`）；
  - `WorkItem` 已有 `waitingPartyId`、`waitingReason`、`blockerReason`、`blockerOwnerId`，但 `WorkItemPanel` 只显示“存在阻塞”Tag（`TaskDetailPage.tsx:565-573`），没有显示具体等待对象、原因和阻塞责任人；
  - Dependency 展示使用 `description || externalPartyId`，有描述时会隐藏等待对象（`TaskDetailPage.tsx:609-612`）。
- 影响：用户在消息研判时看到了缺失材料，但创建事项后不容易判断“还缺什么、等谁、谁负责解除阻塞”，无法形成实际法务跟进闭环。
- 修复建议：
  1. 确认 Drawer 中保留缺失材料摘要，并要求人工将其转成下一步或依赖；
  2. 如果现有 confirm-create API 暂不支持初始 Dependency，明确提示“创建后需补充依赖”，不要假装已带入；
  3. Matter Detail 同时展示 WorkItem waiting/blocker 字段和 Dependency 的等待对象 + 说明，不能二选一隐藏。

修复复审证据：确认 Drawer 复显 `missingInformation`，将其预填到 `nextAction`，并明确“当前接口不会自动创建依赖”；任务摘要显示 waiting party/reason、blocker reason/owner；Dependency 同时显示对象与说明。相关 Inbox 和 Matter 合约测试通过。

### M4. 权限、陈旧和普通错误状态只在 Inbox 做了真实区分（影响核心流程）

- 最终状态：**已关闭**。

- 路由：`/matters`、`/matters/:matterId`、`/reviews`、`/reviews/:id`、`/system/agent-runs`
- 视口：全部
- 证据：共享 `StatePanel` 已支持 `permission` 和 `stale`，但上述页面仍把 API 失败统一渲染为普通 error；现有 403 专项只见于 Inbox；没有页面在保留旧成功数据时显示“可能不是最新”。
- 影响：权限撤销可能把业务摘要和普通失败混在一起；用户无法区分“没有数据”“无权访问”“数据可能陈旧”。这与 `02-information-architecture.md` 第 187-214 行的状态策略不一致。
- 修复建议：按 `ApiError.status` 映射 401/403/409；权限态清空敏感摘要；若不保留旧数据则无需虚构 stale，若保留则必须显示真实时间戳和“可能不是最新”。为 Matters、Reviews、Agents 至少各增加一个 403 合约测试。

修复历程：`classifyApiFailure()` 先统一主列表和详情；上一轮发现 Deadline / Dependency 子资源仍为普通 error。最终两个子资源也使用同一分类，失败时清空旧数组；任务摘要中的最近硬期限显示失败标题而不是“当前未记录”。精准测试逐一覆盖 401、403、409，确认权限/陈旧文案正确且不泄露原期限或依赖摘要，结果通过。

### M5. Matter 详情的首屏决策信息仍缺“等待 / 阻塞”语义（影响核心流程）

- 最终状态：**已关闭**。

- 路由：`/matters/:matterId`
- 视口：390 最明显，也影响桌面扫描
- 证据：`artifacts/ui-upgrade/after/matter-detail/390.png` 首屏已显示风险、状态、负责人、目标、下一步和计划完成时间，但“存在阻塞”只有无解释 Tag，等待对象/原因不出现；硬期限在下方资源区。
- 影响：移动端核心流程虽可用，但用户不能在首屏回答“现在卡在哪里、等谁”。
- 修复建议：将 nearest hard deadline、等待对象/原因和 blocker owner 提升到 WorkItem 决策摘要；保持真实数据，字段为空时写“当前未记录”，不要推断。

修复历程：字段先加入 `任务决策摘要`，但上一轮仍在事项背景之后。最终 DOM 顺序调整为事项概览 → 行动任务/任务摘要 → 补充信息 → 事项背景。390 精准测试使用 `toBeInViewport()` 验证风险、负责人、下一步、计划完成、等待对象和阻塞原因，并继续检查页面无横向溢出，结果通过。

### M6. 搜索筛选返回只恢复 query，没有恢复页码、排序和滚动上下文（影响核心流程）

- 最终状态：**已关闭**。

- 路由：`/matters` → `/matters/:matterId` → `/matters`
- 视口：全部
- 证据：q/category/risk/status/owner 已通过 URL 和 `history.state.returnTo` 恢复；当前列表没有 sort/page query，Table 未配置受控分页，也没有滚动恢复。`02-information-architecture.md:73-79` 要求 query、页码和筛选上下文恢复。
- 影响：当前小数据集影响有限，但事项增多后从详情返回会失去列表位置，增加重复扫描。
- 修复建议：若后端仍只提供 `limit=100`，先在前端实现稳定排序和 URL page；记录列表 scroll key，返回时恢复；若暂不实施分页，应在最终报告明确为后端/列表规模限制，而不是声称完整满足。

修复复审证据：Matters 已提供受控 sort/page query、12 项分页和 `restoreScrollY`；界面明确“当前仅在服务返回的前 100 项内排序和分页”。排序、第二页、详情往返和滚动恢复合约测试通过。

## 7. Low

### L1. 审核队列泄露技术原码和英文包类型，术语没有完全统一

- 最终状态：**未关闭；Low**。

- 路由：`/reviews`
- 证据：状态显示“待审核（pending_review）”，标题下显示 `external_message`；自动化用例还把该表现固化为预期。
- 影响：不影响门禁，但破坏面向法务的可扫描性。Agent 执行记录保留技术原码是合理的，审核队列不是技术审计页。
- 建议：审核队列只显示中文状态和“外发消息”；原码放入审核详情的“技术信息”折叠区。

### L2. 事项模板的展示分类与实际筛选粒度不一致

- 最终状态：**未关闭；Low**。

- 路由：`/templates` → `/matters?category=...`
- 证据：“主播签约”和“劳动用工”都映射 `employment`；“用户投诉”和“诉讼仲裁”都映射 `dispute`（`LibraryPage.tsx:7-16`）。
- 影响：按钮写“查看主播签约事项”，实际会展示全部劳动用工事项，容易误解筛选范围。
- 建议：改为真实大类名称，或把按钮写成“查看劳动用工类事项”；后端出现二级分类前不要伪装精确筛选。

### L3. 移动导航截图未证明 Drawer 已展开

- 最终状态：**已关闭**。

- 证据：`artifacts/ui-upgrade/after/navigation/390-drawer.png` 显示的是未展开的 Today 页面；现有 Playwright 用例包含移动导航可见性断言，但截图文件名与内容不一致。
- 关闭证据：后续独立视觉 QA 已重新覆盖 `artifacts/ui-upgrade/after/navigation/390-drawer.png`，Drawer 真正展开，当前项高亮、关闭入口、页面切换和演示边界均可见。

### L4. Review 队列缺少等待时长和队列筛选

- 最终状态：**未关闭；Low**。

- 路由：`/reviews`
- 证据：只有提交时间，无等待时长、状态筛选或 Matter 过滤；`02-information-architecture.md:130-136` 将等待时长列为审核队列优先字段。
- 影响：单条演示数据影响低，真实队列增长后会降低优先级判断效率。
- 建议：等待时长只能由真实 submittedAt 计算；先提供状态/Matter 筛选，不得捏造 SLA。

## 8. 已确认的正向结果

- 导航信息架构已收敛为“工作 / 资料与模板 / 系统与审计”，不再以 AI 能力为产品主轴。
- `/`、列表、详情和 Drawer 都有可恢复 URL；Matter 的筛选 query 在显式返回和浏览器返回中保留。
- Today 的行动队列先于统计；演示快照有明确边界，不显示虚假在线、同步或服务健康状态。
- Inbox 已形成“来源证据 → 证据边界 → AI 建议 → 缺失信息 → 人工决定”的安全顺序。
- AI 建议和人工确认有稳定视觉与文案区分；非 create-matter 动作没有被伪装成可执行。
- Matter 列表没有因为 UI 需要而伪造期限、等待对象或下一步；移动端使用结构化记录卡。
- Matter 详情的 Deadline / Dependency 已区分 loading、empty、error，并可局部重试。
- 表单具备基础校验、重复提交保护和统一 dirty guard；Review 的返回队列、返回事项和 Drawer 关闭均经过同一保护。
- ReviewPackage 只有 approved 才能进入外发队列；界面明确“进入队列不等于已发送”。
- Files、About、Data Boundaries 没有把未接入能力或静态原则包装成真实状态。
- AgentRun `completed` 明确解释为运行结束，不是法律结论已经确认。

## 9. 完成门槛建议

当前建议：**UX / 信息架构代码与合约测试门槛通过**。

门槛核对：

1. blocker：0；
2. high：0；
3. 影响核心流程的 medium：0；
4. M2、M4、M5 精准 Playwright CLI：4/4 passed；
5. 未发现本轮修复引入新的审核绕过、权限摘要泄露、虚假状态或核心导航断点。

发布前仍需由独立 `visual_qa_reviewer` 使用真实页面确认最新代码在 1440/1024/390 的视觉结果，并更新早于本轮修复的 `after` 截图与 `06-functional-qa.md` / `07-final-report.md`。这属于独立视觉证据门槛，不重新打开已经通过代码和合约测试关闭的 M2、M4、M5。

Low 项可带入完成，但必须在 `07-final-report.md` 中作为残余问题列出。
