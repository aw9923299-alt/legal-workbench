# Legal Workbench 最终独立视觉 QA

验收日期：2026-08-04
审查角色：`visual_qa_reviewer`
验收对象：当前未提交工作树；本地安全演示夹具；不连接生产数据

## 1. 最终结论

最终严重度：**0 blocker / 0 high / 0 影响核心流程的 medium / 4 low**。

独立视觉审查使用 `browser-visual-qa` Skill 与 Playwright MCP，重新遍历 10 个逻辑页面在 1440×900、1024×768、390×844 下的 30 个 page/viewport 组合，并重新覆盖 `artifacts/ui-upgrade/after/` 的 30 张基础截图。30/30 组合的页面 `scrollWidth` 均不大于 viewport。

审查中实际发现过 1 个影响核心流程的 Medium：1440×900 的“创建审核包”长 Dialog 底部超出视口，footer 与主操作被裁切。该问题经 frontend 修复后，review-package Dialog 在 1440、1024、390 三个视口均已重新核验：footer 位于视口内，1024/390 由 body 内部滚动承载长表单，页面本身没有横向溢出。该 Medium 已关闭。

最终没有发现新的 blocker、high 或影响核心流程的 medium。

## 2. 覆盖范围

| Route | 1440 | 1024 | 390 | 重点结果 |
|---|---:|---:|---:|---|
| `/today` | 通过 | 通过 | 通过 | 行动队列优先；演示边界可见 |
| `/inbox`、`/inbox/:id` | 通过 | 通过 | 通过 | 队列、详情、确认 Drawer、validation 可达 |
| `/matters` | 通过 | 通过 | 通过 | 筛选、排序、分页、active filters 与卡片布局可用 |
| `/matters/:id` | 通过 | 通过 | 通过 | 任务决策摘要、等待/阻塞、期限、依赖及 Dialog 可达 |
| `/reviews`、`/reviews/:id` | 通过 | 通过 | 通过 | 外发目标首屏可核对；Drawer header/footer 稳定 |
| `/templates` | 通过 | 通过 | 通过 | 演示入口与禁用能力清楚 |
| `/files` | 通过 | 通过 | 通过 | 未接入边界和替代路径不溢出 |
| `/system/agent-runs`、`/:id` | 通过 | 通过 | 通过 | 执行状态不冒充法律确认；JSON 局部滚动 |
| `/system/data-boundaries` | 通过 | 通过 | 通过 | 无虚假在线/同步/成功状态 |
| `/system/about` | 通过 | 通过 | 通过 | 未接入说明和安全替代路径可用 |

## 3. 稳定 Overlay 证据

以下 6 张截图均在 Ant Design 动画稳定后重新获取；不再是进入动画中途的窄片段或空页面：

```text
artifacts/ui-upgrade/after/navigation/390-drawer.png
artifacts/ui-upgrade/after/inbox/390-drawer.png
artifacts/ui-upgrade/after/matter-detail/1440-priority-dialog.png
artifacts/ui-upgrade/after/matter-detail/1440-review-dialog.png
artifacts/ui-upgrade/after/reviews/1440-dialog.png
artifacts/ui-upgrade/after/agents/1440-dialog.png
```

核验结果：

- 移动导航：当前项高亮、关闭入口、全部导航组及主操作完整可见；
- Inbox Drawer：人工字段和固定 footer 可见，长内容由 Drawer body 滚动；
- Priority Dialog：短表单居中，操作完整可见；
- ReviewPackage Dialog：1440/1024/390 的 footer 均在视口内；
- Review Drawer：真实 `replyToMessageId` 目标可见，返回事项/审核队列与提交 footer 可达；
- Agent Drawer：技术状态、来源、结构化输出完整显示，JSON 超长内容只在局部滚动。

## 4. 功能与状态复核

- Review 的真实外发目标已显示；无法识别目标时批准和入队均被阻止；
- Review dirty 状态下，无论关闭、返回审核队列还是返回事项，都先出现放弃修改确认；
- Matter 的 Deadline/Dependency 能区分 401、403、409 和普通失败，失败时不把期限误写成“当前未记录”；
- 390 首屏可见风险、负责人、下一步、计划时间、等待与阻塞语义；
- Matters 的排序、客户端分页和详情返回上下文可用，并明确只覆盖服务返回的前 100 项；
- 1024 折叠侧栏保留视觉分组，不显示截断组名；
- AI 建议、人工决定、Agent 技术状态和 Communication queued 保持不同语义，不出现未经证明的在线、同步或已发送状态。

## 5. Console、网络与 Figma 证据边界

- 独立 MCP 路由巡检未观察到本轮修改导致的渲染崩溃或 Ant Design 弃用警告；
- 主 Agent 在独立审查后补做的 MCP console 抽查仅出现 React DevTools 的开发环境 `INFO`，没有 warning/error；
- 全量 Playwright 使用 fail-closed API 夹具；未声明路径或方法不能静默返回成功；
- Figma MCP 再次确认目标文件可读，但 Starter plan tool-call quota 阻止写入。没有把 PNG、文档映射或代码实现伪称为原生 Figma Frames/Components。

## 6. 已关闭的视觉 Medium

### VQA-M01 — 创建审核包 Dialog 超出 1440×900

- Route：`/matters/matter-demo-1`
- Viewport：1440×900；同时复核 1024×768、390×844
- 原证据：Dialog `y=100`、`height=848`、`bottom=948`，footer 被裁切
- 修复：Dialog 统一视口最大高度；content 使用纵向 flex；body 内部滚动；header/footer 固定在 Dialog 内
- 最终证据：`artifacts/ui-upgrade/after/matter-detail/1440-review-dialog.png`
- 状态：关闭

## 7. 残余 Low

1. 审核队列和部分系统页仍保留技术原码/技术 ID，可扫描性弱于纯业务文案；保留它们有审计价值，后续可移入“技术信息”折叠区。
2. Matter 详情在桌面仍有局部卡片嵌套，长数据下的信息密度还可继续收敛。
3. 共享 entry chunk 仍超过 500 kB；需要真实加载 profile 后再决定是否拆 vendor，本轮不凭构建警告盲目分包。
4. Figma Starter quota 阻止原生设计系统与 Ready for development Frames；这是设计证据缺口，不是代码运行故障。

## 8. 放行意见

视觉与功能层面可放行本轮未提交实现：没有 blocker、high 或影响核心流程的 medium；三个规定视口无页面级横向溢出；移动端核心流程与长 Dialog 操作可达。低优先事项和 Figma 配额限制必须继续保留在最终报告中，不得写成已经完成的原生 Figma 交付。
