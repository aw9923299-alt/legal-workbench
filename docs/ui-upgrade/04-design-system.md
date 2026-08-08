# Legal Workbench 设计系统

更新时间：2026-08-04
方向：安静的法务运营控制台

## 1. 设计原则

1. 行动先于统计：先回答“现在要处理什么、为什么、下一步是什么”。
2. 证据先于 AI：来源、证据边界和缺失材料永远先于模型结论。
3. 人工决定可辨认：AI 建议、人工确认、确定性系统状态使用不同语义。
4. 状态必须可证实：无状态接口时只显示“待核验/未接入”，不显示在线、同步正常或成功。
5. 密度服务扫描：桌面支持高密度队列；移动端改写任务顺序，不压缩桌面表格。
6. 一页一个主动作：其他动作降级、分组、禁用或放入详情。
7. 复用 Ant Design：只做 token、组合组件和必要 variant，不建立平行框架。

## 2. 色彩

| 语义 | 值 | 用途 |
|---|---|---|
| Primary | `#315f8f` | 主操作、选中、可聚焦链接 |
| Text primary | `#17243a` | 正文与高层级标题 |
| Text secondary | `#657083` | 元数据、说明、辅助标签 |
| Border | `#d8dee8` | 输入、卡片、分隔 |
| Canvas | `#edf1f5` | 应用背景 |
| Surface | `#ffffff` | 主要工作表面 |
| Surface subtle | `#f7f8fa` | 次级分区、只读元数据 |
| Selected surface | `#edf4fa` | 选中行、筛选提示 |
| Success | `#31735d` | 已确认、确定性成功；必须配文字 |
| Warning | `#9c672c` | 待处理、临近期限、缺失材料 |
| Danger | `#a84949` | 严重风险、失败、破坏性动作 |
| AI | `#6c6487` | AI 建议标题/边框，不作正式结论色 |
| AI surface | `#f6f4fa` | AI 建议区域 |
| Missing surface | `#fff9ef` | 缺失材料、待补信息 |
| Disabled | `#a9b1be` | 不可用控件；同时说明原因 |

保留既有主色、正文、次要文字、边框与 6px 圆角。没有证据表明需要更换品牌色；本轮只补齐语义用途。

## 3. 字体

字体栈：`Inter, PingFang SC, Microsoft YaHei, system-ui, sans-serif`。

| 层级 | 桌面 | 移动 | 字重 | 用途 |
|---|---:|---:|---:|---|
| Page title | 24/32 | 22/30 | 600 | 唯一页面标题 |
| Section title | 18/26 | 17/24 | 600 | 一级工作分区 |
| Card title | 16/24 | 16/24 | 600 | 记录标题、Dialog 标题 |
| Body | 14/22 | 14/22 | 400 | 正文、表格 |
| Meta | 13/20 | 13/20 | 400 | ID、时间、来源 |
| Caption | 12/18 | 12/18 | 400 | 技术说明、帮助文案 |

正文不得低于 13px；重要标签不得只靠全大写或颜色形成层级。

## 4. 间距、圆角、边框与阴影

- 基础间距：4px；主要序列为 4、8、12、16、24、32px；
- 页面上下内边距：桌面 24px，1024 为 20px，390 为 16px；
- 内容块间距：24px；同组元素：8–12px；
- 圆角：输入/按钮/卡片统一 6px；小标签 4px；胶囊状态可用全圆角；
- 边框：1px `#d8dee8`；不通过多层阴影制造卡片嵌套；
- 阴影：仅 Drawer、Modal、浮层使用；内容卡默认无阴影或极弱阴影；
- 焦点：2px 主色 outline + 2px offset；不得只依赖浏览器不可见默认态。

## 5. 栅格和响应式

| 宽度 | 壳与内容 | 数据集合 | Overlay |
|---|---|---|---|
| 1440×900 | 224/228px 常驻侧栏；内容最大 1440 | 语义表格、高密度队列 | 中等宽度 Drawer/Dialog |
| 1024×768 | 72px 折叠侧栏；单/双列收敛 | 减少次要列或紧凑列表 | 宽度不超过 viewport-32 |
| 390×844 | 顶栏 + 导航 Drawer | 结构化记录卡 | 近全屏或全屏；footer 安全区 |

所有 viewport：页面级 `scrollWidth <= viewport.width`。JSON、代码与长 ID 只能在局部可滚动容器中横向滚动。

## 6. 语义体系

### 风险

- critical/high/medium/low/pending 使用文字 + 图形/边框 + 颜色；
- 严重/高风险不能只显示红点；
- “待评估”不能使用成功或中性色暗示已处理。

### 期限

- 区分法律期限、平台期限、合同期限、业务期限、内部计划、提醒；
- `plannedCompleteAt` 必须显示“计划完成”，不得称为法律期限；
- 只有 API 返回真实时间戳时才显示具体更新时间。

### AI 与人工

- AI：标题固定含“AI 建议/AI 提取”；弱紫灰 surface；附“需人工核对”；
- 人工：绿色或主色 outline，显示确认人、时间和版本；
- 系统：中性/主色，仅表达确定性流程状态；
- AgentRun completed：显示“运行完成”，明确不等于法律结论确认。

### 数据来源

- 演示数据：稳定显示“安全演示数据”；
- API 数据：显示“由服务接口提供”，不使用“实时同步”；
- 待核验：状态接口未接入；
- 未接入：功能与后端均不存在或未连接。

## 7. 公共组件规格

### PageHeader

- 页面标题、目的说明、来源/更新时间、一个 primary action；
- 次级操作最多两个，超过则放入 overflow；
- 390 下标题与动作纵向排列。

### DataBoundaryBanner

- variants：demo、api、pending、unavailable、stale；
- 包含图标、标题、单句解释，可选 retry/action；
- 不使用 `success` variant 表达未经验证的连接状态。

### QueueToolbar / ActiveFilterBar

- 搜索可 Enter 提交并清除；
- 筛选值真实作用于集合；
- active filters 可见、可逐项清除、可全部清除；
- URL query 为恢复来源。

### ResponsiveCollection / MobileRecordCard

- desktop/compact 可以表格或紧凑列表；390 固定卡片；
- 卡片顺序：标题 → 风险/状态 → 期限/时间 → 负责人 → 下一步/目标 → 主操作；
- 整卡不依赖 click；标题或显式按钮可聚焦。

### StatePanel

- variants：loading、empty、filtered-empty、error、permission、unavailable、stale；
- error 提供重试和 correlation id；
- permission 不展示缓存业务摘要；
- filtered-empty 提供清除筛选；
- unavailable 提供当前安全替代路径。

### FormSection / ResponsiveModal

- Context summary、字段、说明和影响预览分区；
- required、error、help、disabled reason 完整；
- dirty 关闭需要确认；
- submit 中禁用重复提交；成功反馈必须来自真实 API；
- 390 下宽度接近 100%，内容区可滚动，footer 不遮挡错误。

### AI Suggestion Panel / Evidence Panel

- Evidence Panel 先于 AI；
- 分开呈现原始消息、快照范围、附件标识与解析状态；
- AI Panel 分 confirmed facts、inferred facts、missing information；
- 置信度只能作为元数据，不能作为批准门槛的替代。

## 8. 交互状态

所有可交互组件至少覆盖：default、hover、focus-visible、selected、disabled、loading、error/validation。队列和表单还需覆盖：empty、permission、stale、unsaved、duplicate-submit guard。

危险操作的确认内容必须包含目标对象、影响和后果。当前仓库没有真实删除/发送能力时，不应仅为了展示而添加破坏性按钮。

## 9. 无障碍

- 图标按钮必须有可读 `aria-label`；
- 触控目标至少 44×44px；
- 表格行不能成为唯一入口，标题或按钮必须可聚焦；
- Tab 顺序跟随视觉顺序；Drawer/Modal 打开后焦点进入，关闭后回到触发器；
- 风险、错误、选中、禁用均不能只靠颜色；
- 说明和 validation 使用明确文本，必要时 `aria-live`；
- 390 下不隐藏风险、负责人、期限/状态和下一步。

## 10. Ant Design API 与弃用规则

- `Card` 使用当前推荐 `variant` API，不继续新增 `bordered`；
- Drawer/Modal 使用当前 props，避免控制台弃用警告；
- theme token 为唯一全局视觉入口；
- 页面只组合 Ant Design 与项目公共组件，不复制整套相同 CSS；
- 不引入 Tailwind、MUI、Chakra 或其他 UI 框架。

## 11. Figma 变量回填规范

配额恢复后建立：

- `LW / Primitives / Color`；
- `LW / Primitives / Space`；
- `LW / Primitives / Radius`；
- `LW / Primitives / Size`；
- `LW / Semantic / Color`（alias 到 primitive）。

变量显式设置 scopes，并配置 Web code syntax（如 `--lw-color-primary-500`）。组件使用 Auto Layout、Variants 和上述变量。每一项必须能回映射到 Ant Design 或现有项目组件。
