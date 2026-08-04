# Legal Workbench 产品设计最终自审

更新时间：2026-08-04
审查角色：`product_ui_designer` 独立只读复核
设计方向：安静的法务运营控制台

## 1. 审查范围与证据

本次复核对照了：

- `artifacts/ui-upgrade/before/` 与 `artifacts/ui-upgrade/after/` 中全部 1440×900、1024×768、390×844 页面截图；
- Inbox、事项表单、审核详情、AgentRun 详情、移动导航等附加状态截图；
- `03-figma-design-map.md`；
- `04-design-system.md`；
- 当前 App 壳、共享组件、响应式集合及相关页面代码。

覆盖页面：今日工作台、待确认消息、事项队列、事项详情、审核中心、事项模板、合同与文件、Agent 执行记录、数据边界、系统信息。

本轮未修改应用源代码，也未使用 Playwright MCP。最终 30 张基础截图和 6 组稳定 Overlay 证据已经更新；本次按要求仅基于更新后的 before/after 截图和代码完成复核。交互级结论仍以最终独立浏览器验收为准。

## 2. Figma 状态

Figma 文件仍未形成可作为最终视觉对照源的原生 Frames。正式写入被 Starter plan MCP tool call quota 阻断；仓库文档已经明确记录这一限制，没有把截图或设计规范描述为 Figma 原生组件、Variables、Variants 或 Ready for development Frames。

因此本轮只能完成“设计规范 → 代码 → Playwright 截图”的复核，不能完成“最终 Figma Frame → 实现截图”的逐页视觉比较。该限制不等于应用缺陷，但最终报告必须保留，不能宣称 Figma 设计已原生落地。

## 3. 总体结论

最终实现已经从“含多个演示 Dashboard 与静态系统状态的原型”收敛为一致、克制、行动优先的法务工作台。主要改善成立：

1. Dashboard 移除了位于行动队列之前的指标条；首屏直接进入“下一步工作队列”。
2. AI 不再作为应用壳中心能力；导航改为用户任务语言“待确认消息”。
3. 应用导航按工作、资料与模板、系统与审计分组。
4. Matters、Reviews、Agents 在 1024 和 390 使用紧凑记录或结构化卡片，不再压缩桌面表格。
5. Security 已改为“数据边界”，删除静态绿色“正常/成功”、假数量和假 Switch。
6. Library 明确标注安全演示数据，未接入按钮禁用并写明原因，真实入口导航到事项队列。
7. Files 与 System About 使用专属 unavailable 状态，说明目的、当前限制、后端缺口和可用替代路径。
8. PageHeader、DataBoundaryBanner、ResponsiveCollection、StatePanel、UnavailableState 形成了跨页面共享语言。
9. 风险、期限、人工确认和运行状态均有文本，不只依赖颜色。
10. 应用壳删除了无行为的 AI、通知、在线/同步图标，底部明确“本地演示不代表连接或同步状态”。

从截图看，当前页面已经不具有明显的 AI 模板化 Dashboard 风格；统计不再压过行动，移动端也不再只是缩小桌面。

最终问题计数：

- blocker：0；
- high：0；
- 影响核心流程的 medium：0；
- 保留的非核心 medium：3；
- 保留的 low：3。

## 4. 设计自审矩阵

| 检查项 | 结果 | 证据与说明 |
|---|---|---|
| AI Dashboard 感 | 通过 | Dashboard 首屏只保留可信边界和主行动队列；AI 建议退到下方辅助区 |
| 统计是否压过行动 | 通过 | before 的四指标条已从首屏移除；工作队列成为第一个内容表面 |
| 卡片嵌套 | 基本通过 | Library、Reviews、Agents、Security 已扁平化；Matter Detail 仍有一层可继续收敛 |
| 主操作数量 | 通过 | PageHeader 通常只有一个业务主动作；刷新保持次级按钮 |
| 重要信息是否隐藏 | 通过 | 风险、状态、负责人、目标、期限、下一步在对应队列和详情首层可见 |
| 移动端是否只是缩小 | 通过 | Matters、Reviews、Agents、Security 均改为单列结构化记录 |
| 风险是否只用颜色 | 通过 | 高风险、紧急、硬期限均同时有明确文字 |
| 虚假状态 | 通过 | 数据边界明确未接入运行状态接口；Footer 不暗示在线或同步 |
| 不可执行按钮 | 通过 | 模板新建/配置和 Inbox 未接入动作均明确禁用并解释 |
| AI 与人工决定 | 通过 | Inbox 和 Agent 页面均固定提示需人工确认；运行完成不等于法律结论确认 |
| 共享视觉语言 | 通过 | 页面标题、边界提示、数据集合、空错状态和不可用状态已统一 |
| Figma 原生交付 | 未完成，已诚实记录 | Starter quota 阻断，没有最终原生 Frames |

## 5. Findings

### Blocker

未从最终静态页面证据中发现产品视觉 blocker。

### High

没有未解决的 high。

#### PD-FINAL-H01 — 已关闭：关键 Overlay 与移动导航证据已稳定补齐

- Route / viewport：`/today` 390；`/inbox/:candidateId` 390；`/matters/:matterId` 1440；`/reviews/:reviewPackageId` 1440；`/system/agent-runs/:runId` 1440。
- status：resolved。
- evidence：
  - `after/navigation/390-drawer.png` 完整显示分组导航、关闭按钮、主操作和演示边界说明；
  - `after/inbox/390-drawer.png` 与 `after/inbox/390-validation.png` 完整显示全宽表单、字段、validation 与固定 footer；
  - `after/matter-detail/1440-priority-dialog.png` 完整显示优先级、时间、理由、覆盖原因及确定性操作；
  - `after/matter-detail/1440-review-dialog.png` 完整显示外发审核包表单及“不直接发送”门禁说明；
  - `after/reviews/1440-dialog.png` 完整显示审核证据、事实、理由、风险和提交审核决定；
  - `after/agents/1440-dialog.png` 完整显示运行状态边界、授权来源和局部可滚动结构化输出。
- result：先前问题属于截图停在 motion 过渡中的证据缺口，不是稳定界面的布局缺陷；更新后的证据已经满足产品视觉复核要求。

### Medium

#### PD-FINAL-M01 — 审核与 Agent 状态仍混排中文和技术原码

- Route / viewport：`/reviews`、`/system/agent-runs`，全部视口。
- affected region：状态 Tag。
- evidence：`待审核（pending_review）`、`运行完成（completed）` 仍出现在队列首层。
- observed：技术原码抢占用户队列的扫描空间，且与其他纯中文状态不一致。
- expected：队列只显示“待审核”“运行完成”；原码放入详情的技术信息区。
- recommendation：共享状态词典提供 `label` 与 `rawCode` 两层展示策略。

#### PD-FINAL-M03 — Matter Detail 仍有局部 Card 嵌套

- Route / viewport：`/matters/:matterId`，全部视口，390 最明显。
- affected region：行动任务。
- evidence：行动任务外层表面中再次嵌套 WorkItem 表面，内部又有期限和依赖两个 bordered panel。
- observed：信息边界清楚，但表面层级比其余新页面更重。
- expected：Section → WorkItem row/block → definition groups，最多保留一层主要边界。
- recommendation：下一轮将期限/依赖改为无卡片的 definition group 或 divider list；不影响本轮核心流程。

#### PD-FINAL-M04 — 部分面向法务用户的技术标识可读性仍偏低

- Route / viewport：Inbox、Matters、Agents，全部视口。
- affected region：时间、负责人和来源元数据。
- evidence：Inbox 队列保留完整 ISO 时间；多处直接展示 `ou_legal_demo`、`om-demo-1`。
- observed：安全演示边界明确，但用户阅读仍需解析技术 ID 和时区格式。
- expected：队列优先显示本地化时间与人员显示名；技术 ID 仅在详情/审计区保留。
- recommendation：后端或 adapter 提供 display name；时间统一为 `YYYY-MM-DD HH:mm`，原始值保留在技术详情。

原 `PD-FINAL-M02` 已关闭：更新后的全部 1024 截图中，折叠侧栏不再显示 `资料...`、`系统...` 等截断分组文字，只保留清楚的图标分组和分隔。

### Low

#### PD-FINAL-L01 — 顶栏全局搜索存在重复搜索图标

- Route / viewport：全部桌面/1024 页面。
- affected region：Input.Search。
- evidence：输入框左侧 prefix 与右侧 search button 均为放大镜。
- observed：功能明确但视觉重复。
- expected：保留一个识别入口即可。
- recommendation：移除 prefix 或改为纯 Enter 提交输入框。

#### PD-FINAL-L02 — Eyebrow 语言仍不完全统一

- Route / viewport：Matters 使用 `LEGAL MATTERS`，其他页面多已改为中文语义。
- affected region：PageHeader eyebrow。
- observed：不影响任务，但略有通用 SaaS 模板感。
- expected：统一使用中文场景语义，英文只保留产品/技术专名。
- recommendation：将 `LEGAL MATTERS` 改为“法律事项”或删除非必要 eyebrow。

#### PD-FINAL-L03 — Unavailable 页面桌面空间利用偏空

- Route / viewport：`/files`、`/system/about`，1440。
- affected region：UnavailableState surface。
- observed：大面积空白与大警告图标略接近通用系统占位页。
- expected：继续保持诚实边界，同时缩短表面高度或增加“当前可用入口”说明列表。
- recommendation：作为后续 polish；当前状态已明显优于假功能或无说明占位。

## 6. 与 before 的关键差异

| 页面 | before | after |
|---|---|---|
| Dashboard | 指标、队列、期限、消息、AI、周统计同页竞争 | 首屏行动队列绝对优先，统计和建议后置 |
| Inbox | 语义良好但缺服务边界说明 | 增加“接口提供、不代表实时同步”，来源/AI/人工关系更清楚 |
| Matters | 390 表格逐字断行 | 1024 紧凑记录、390 Matter Card、真实筛选 |
| Detail | 低对比加载蒙层、字段与操作分散 | 风险/状态/负责人/目标置顶，任务与补充信息稳定分区 |
| Reviews | 桌面小卡片、390 半屏卡片 | 1440 表格、1024/390 全宽审核记录 |
| Library | 八张重复大卡、假“可配置” | 扁平目录、演示标识、配置禁用原因、真实浏览入口 |
| Agents | 390 裁切表格 | 1024/390 Run Card，并明确运行完成不等于法律确认 |
| Security | 假正常、假成功、假 Switch、移动表格 | 数据边界、未接入状态、产品约束与后端缺口 |
| Files/About | 共用泛化占位 | 各自说明目的、限制、后端缺口和替代路径 |

## 7. 完成门槛建议

当前建议：**产品设计层面通过本轮完成门槛。**

依据：

1. 30 张三档视口基础截图完整；
2. 移动导航、Inbox Drawer/validation、事项 Dialog、审核 Drawer、AgentRun Drawer 均已有稳定状态证据；
3. blocker 为 0，high 为 0，影响核心流程的 medium 为 0；
4. 三项保留 medium 均为术语呈现、局部表面层级和技术元数据可读性，不阻断导航、判断、审核或人工门禁；
5. 三项 low 仅为视觉与文案 polish；
6. Figma 原生 Frames 因 Starter quota 未完成的限制已经明确记录，没有进行虚假的像素一致性声明。

保留的 medium：

- `PD-FINAL-M01`：审核与 Agent 队列仍显示技术原码；
- `PD-FINAL-M03`：Matter Detail 仍有局部 Card 嵌套；
- `PD-FINAL-M04`：人员/来源技术 ID 与部分时间格式可读性仍可提升。

保留的 low：

- `PD-FINAL-L01`：顶栏搜索图标重复；
- `PD-FINAL-L02`：少数英文 eyebrow 与中文体系不完全一致；
- `PD-FINAL-L03`：Unavailable 页面桌面空间利用偏空。

最终系统级完成声明仍应同时引用 `visual_qa_reviewer` 的真实浏览器结果和工程验证结果；就产品设计与现有最终截图而言，无需为上述残余项阻止本轮交付。
