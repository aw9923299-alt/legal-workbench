# AI 收件箱 / 待确认消息最终独立视觉验收

## 最终判定

- 结论：**PASS**。
- 当前问题：**Blocker 0 / High 0 / Medium 0 / Low 0**。
- 发布建议：通过本轮收件箱视觉与安全门禁验收，可进入发布收尾。
- 先前发现的 H01 非法时间异常、H02 重新分析旧结果竞态、M01 空必填未处理异常均已在真实 Playwright 浏览器中确认修复。
- 三个规定视口均无页面级横向溢出；核心路径无未处理异常、无意外失败请求、无 Ant Design `bordered` 弃用警告或静态 message API 警告。

## 验收边界

| 项目 | 记录 |
|---|---|
| 页面入口 | `http://127.0.0.1:4173/` → “处理待确认消息” |
| Git 基线 | `5662476`；验收时工作区包含尚未提交的本轮实现 |
| 浏览器 | Playwright MCP 驱动的独立 Chromium/Google Chrome 无头实例 |
| 视口 | 1440×900、1024×768、390×844 |
| 数据环境 | 显式 UI contract fixtures，与 `apps/web/e2e/inbox.spec.ts` 同源语义 |
| mutation 边界 | `confirm-create` 始终被拦截；人工编辑只取消。retry 竞态测试仅向 fixture 发出 1 次受控 POST，不到达真实后端 |

本报告只能证明前端在确定性 UI 合约载荷下的渲染、交互和门禁行为，**不能证明真实飞书、Codex、认证、附件正文解析、Candidate 状态迁移或 confirm-create 集成可用**。所有 fixture 响应均显式带有 UI contract 语义，不作为真实业务数据或上线能力证据。

## 修复项逐项关闭

### QA-INBOX-H01｜非法或越界计划完成时间触发未处理异常

- 原严重度：**high**；当前状态：**已修复**。
- 视口 / 位置：390×844；确认 Drawer → “计划完成时间”。
- 实时证据：分别输入“不是有效时间”和格式看似正确但日期越界的“2026-02-30 18:00”，其余必填项完整后点击确认；两种输入均显示“请按 YYYY-MM-DD HH:mm 填写有效时间”。
- 安全证据：`pageerror=[]`、console error/warning 为空、`confirm-create` 请求为 0，Drawer 保持打开。
- 期望对照：非法输入必须停留在人工编辑层，给出字段级反馈，不能转换日期、提交或抛异常。
- 后续建议：保留非法文本、月日越界和合法时间三组回归测试；日期格式或时区策略变化时同步更新文案与严格解析规则。

### QA-INBOX-H02｜retry 后旧 completed AgentRun 使创建入口重新启用

- 原严重度：**high**；当前状态：**已修复**。
- 视口 / 位置：1440×900；正式动作门禁 → “重新分析”。
- 实时证据：fixture 接受 retry，但列表和详情继续返回旧 `candidate-create / run-create / completed`。重试前“审阅并创建事项”可用；retry 后按钮禁用，并显示“重新分析已提交，等待 Candidate 暴露新的 AgentRun”；点击页面“刷新”后提示仍在、按钮仍禁用。
- 安全证据：fixture 仅记录 1 次 retry POST，`confirm-create` 为 0；`pageerror=[]`、console error/warning 为空、无 HTTP 4xx/5xx、无 request failure。
- 期望对照：只有 Candidate 暴露新的 AgentRun，且新详情与该 Run 一致并进入可接受终态，才能解除 freshness barrier。
- 后续建议：保留“retry 成功 + 旧终态详情 + 手动刷新”回归用例，并增加未来“新 Run 完成后正确解冻”的正向契约测试。

### QA-INBOX-M01｜空必填校验同时产生未处理 pageerror

- 原严重度：**medium**；当前状态：**已修复**。
- 视口 / 位置：390×844；确认 Drawer → 主确认按钮。
- 实时证据：不填写人工必填字段直接点击确认，页面显示 7 条清晰错误：事项负责人、法律风险、业务影响、首个任务负责人、优先级、计划完成时间、下一步行动。
- 安全证据：`pageerror=[]`，`confirm-create` 请求为 0，Drawer 保持可编辑。
- 期望对照：Ant Form 的预期校验拒绝应被正常消费，不进入全局异常通道。
- 后续建议：保留错误数量与关键文案断言；新增字段时同步更新测试而不是放宽为仅检查“任一错误”。

## 三视口视觉与响应式结果

| 视口 | 实时布局 | 页面级横向溢出 | 关键结果 |
|---|---|---|---|
| 1440×900 | 300px 队列 + 证据详情主表面 | 无 | 两条 Candidate、原始消息、证据范围、AI 结果均正常；console/network 干净 |
| 1024×768 | 250px 队列 + 单列详情 | 无 | 关键文字和详情不被裁切；console/network 干净 |
| 390×844 | 默认队列，选择后进入单条详情 | 无 | 返回按钮 44px、创建入口 44px；来源、证据范围、AI 和门禁均保留 |

三个视口均由首页主按钮真实进入收件箱，队列数量为 2；未发现可见元素越出页面左右边界。

## 主流程与安全门禁矩阵

| 检查项 | 结果 | 独立证据摘要 |
|---|---|---|
| 首页主操作进入 | 通过 | “处理待确认消息”进入“待确认消息”，未绕过应用导航 |
| 队列切换 | 通过 | 从品牌口播 Candidate 切换至音乐版权 Candidate，原文、快照、附件、AI 推断和缺失信息随选择变化 |
| 原始消息 | 通过 | 展示发送人 ID、时间、类型、正文；群聊名称明确标注“当前接口未提供” |
| 证据范围 | 通过 | 展示快照版本、消息/参与人/附件数量与 ID、截断状态、快照时间 |
| 缺附件 | 通过 | 无附件但有材料缺口时显示“当前快照未纳入附件”，并展示“最终口播脚本附件”等缺口 |
| 附件仅元数据 | 通过 | 有附件 ID 时显示 `att-copyright-notice` 与“未证明附件正文已解析” |
| AI 结果 | 通过 | AI 位于来源证据之后；事实、推断、期限与缺失信息有稳定区分；置信度注明不能替代证据 |
| 人工编辑与取消 | 通过 | Drawer 可修改 AI 建议字段，显示原子创建影响预览；取消后关闭，`confirm-create=0` |
| create_matter 门禁 | 通过 | 证据完整、待确认、非分析中时才提供创建入口；异常/运行中/重试等待状态均禁用 |
| 非 create_matter | 通过 | 显示“已阻止错误新建事项”，不渲染创建入口 |
| 未接入动作 | 通过 | 关联/更新、补充材料、仅作信息、忽略、暂缓、合并全部禁用，mutation 记录为 0 |
| 键盘 | 通过 | 从刷新按钮 Tab 可聚焦第一条 Candidate；焦点为 2px 项目蓝 outline，Enter 可进入移动详情 |
| 移动触控 | 通过 | 返回队列和主创建入口均为 44px；确认 Drawer 全宽，关闭/主按钮/取消按钮均为 44px |

## 异步与边界状态矩阵

| 状态 | 结果 | 观察 |
|---|---|---|
| 列表加载 | 通过 | 只显示 Skeleton，不显示虚构 Candidate；响应后进入真实 fixture 队列 |
| 详情加载 | 通过 | 队列保留，详情 Skeleton 显示，正文在响应前不提前出现 |
| 空队列 | 通过 | 显示“暂无待确认消息”，不显示 Candidate |
| 列表错误 | 通过 | 显示“候选列表加载失败”与重试；fixture 的 500 被正确呈现 |
| 401/403 | 通过 | 403 显示独立“无权查看待确认消息”与重试，不伪装为空或成功 |
| 详情错误 | 通过 | 显示“证据详情加载失败”与“重试详情”，创建按钮禁用 |
| 缺附件 | 通过 | 明示材料缺口，不把 0 个附件解释为材料齐全 |
| 运行中 | 通过 | 显示“正在分析，正式确认已冻结”，创建按钮禁用 |
| retry 返回旧结果 | 通过 | freshness barrier 跨刷新持续，旧 completed 结果不能重新启用创建 |

错误和无权限 fixture 会有预期的 500/403 网络响应；这些是受控状态输入，不是未解释的产品网络故障。默认主流程、三视口、表单校验与 retry-stale 回归均无意外 4xx/5xx 或 request failure。

## Console 与网络

- 三个规定视口默认主流程：console error/warning 为空，`pageerror=[]`，无 4xx/5xx，无 request failure。
- 非法/越界日期和空必填：无未处理异常，无 confirm-create 请求。
- retry-stale：无 `Static function can not consume context`，无 Ant Design `bordered is deprecated`，无未处理异常。
- error/forbidden/detail-error 场景中的 500/403 为 fixture 主动构造并由页面正确解释；不将其记为发布缺陷。

## 截图清单

最终证据位于 `artifacts/ui-review/inbox/`：

- `after-inbox-1440.png`
- `after-inbox-1024.png`
- `after-inbox-390.png`
- `after-inbox-390-detail.png`
- `after-inbox-390-confirm.png`
- `after-inbox-390-missing-context.png`
- `after-inbox-390-noncreate-gate.png`
- `state-inbox-empty-390.png`
- `state-inbox-forbidden-1024.png`

保留的首轮对照截图：`before-inbox-1440.png`、`before-inbox-1024.png`、`before-inbox-390.png`。

## 完成条件

1. Blocker 为 0：通过。
2. High 为 0：通过；H01、H02 已关闭。
3. 无影响研判流程的 Medium：通过；M01 已关闭。
4. 三个规定视口无页面级横向溢出：通过。
5. 队列 → 证据 → AI → 人工编辑 → 安全确认入口：通过。
6. 非 create_matter 与未接入动作不产生错误正式状态：通过。
7. 加载、空、错误、无权限、详情失败、缺附件、运行中：通过。
8. 无 Ant Design 弃用警告和本轮相关控制台异常：通过。
9. 未调用真实 confirm-create、未改变业务状态：通过。

## 验证缺口

- fixture 只验证 UI 合约；未连接真实飞书、Codex、附件解析或生产认证。
- 正式确认成功、409 版本冲突、服务端幂等回放和创建后导航没有通过真实后端执行，本轮为避免业务写入而未触发。
- 没有 Candidate 的 failed/dead-letter 消息仍不在当前 Inbox 队列契约内，页面已明确提示该覆盖边界。
- 本报告未单独重跑全仓 typecheck/build/后端测试；工程发布仍需与主 Agent 的自动化及构建记录合并判断。
