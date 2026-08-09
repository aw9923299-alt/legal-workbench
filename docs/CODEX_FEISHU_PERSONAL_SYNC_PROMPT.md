# Codex 提示词：飞书个人账号消息与文档接入

将以下内容直接交给 Codex 执行。

---

你正在维护仓库 `aw9923299-alt/legal-workbench`。

## 目标

基于当前 `main` 最新代码，实现“个人飞书账号消息 + 云文档同步到法务工作台”。

正式设计以此文件为唯一需求基线：

`docs/superpowers/specs/2026-08-08-feishu-personal-sync-design.md`

先完整阅读该设计，以及现有 Feishu、Outbox、Document、Codex Runtime、Scope、Setup 相关代码和测试，再实施。不要另起架构。

## 必须遵守

1. 保留现有 App/Bot Feishu 接入，新增 User OAuth 身份，形成双身份架构。
2. User API 消息必须进入现有统一 Ingestion，不得直接写 `FeishuMessage` 核心表。
3. PostgreSQL 是唯一业务事实库；Redis 仅用于队列/协调。
4. `user_access_token`、`refresh_token` 只能通过现有 `LocalSecretProvider` 保存，禁止进入 PostgreSQL 正文、Redis、前端、日志、Codex 输入。
5. Refresh Token 只能使用一次，必须实现并发安全的刷新与原子轮换。
6. Codex 不得直接调用飞书 API，不得读取 Secret。
7. 首期个人身份只读，不实现 `send_as_user`。
8. 不使用飞书客户端抓包、本地缓存解析、UI 自动化或其他非官方方式。
9. 消息“采集”和“触发 Codex 分析”必须解耦，不能让所有个人群消息都自动触发模型。
10. 所有外发继续经过人工审核门禁。

## 实施顺序

严格按以下顺序推进，每阶段完成测试后再进入下一阶段：

### Phase 0：Capability Spike

真实验证：OAuth/PKCE、Refresh Token、已知 P2P、已知群、群发现、P2P 发现、未读状态、个人消息附件、文档搜索、Markdown 正文。

如缺真实飞书凭证：
- 不得伪造通过；
- 提供可直接运行的验证脚本/入口；
- 状态明确记录为 `not_executed`；
- 对未经验证的能力保持安全降级。

### Phase 1：User Authorization

实现 OAuth + PKCE、Authorization 模型、UserTokenProvider、Secret 存储、Refresh rotation、授权状态与 API。

### Phase 2：Personal Message Sync

实现 User Client、已知 chat 历史同步、统一 Ingestion Adapter、Checkpoint、overlap 补偿、限流和恢复。

### Phase 3：Discovery & Scope

复用并扩展现有 `IntegrationScope`，支持 P2P/group、自动发现、Allow/Exclude/Pause、回溯窗口和前端管理。

### Phase 4：Native Feishu Documents

实现消息文档链接识别、文档搜索/导入、可选文件夹订阅、Markdown → DocumentVersion/Segment，并与消息来源关联。

### Phase 5：MessageAnalysisPolicy

将“消息已采集”与“需要 Agent 分析”分开；P2P、@本人、回复本人、明确任务/期限、高价值法务群优先分析，其余默认 `store_only`。

### Phase 6：可靠性验收

覆盖 Mac 睡眠/唤醒、断网、429、权限撤回、Token 失效、Redis flush、PostgreSQL 重启、单 Scope 故障隔离。

## 实现要求

- 遵循当前模块化单体边界和现有命名/Repository/UoW/Outbox 模式。
- 优先复用现有 `IngestFeishuEventHandler`、`LocalSecretProvider`、Document Pipeline、Scope、Setup、SSE 与审计机制。
- 外部 HTTP 调用不要长期占数据库事务。
- 所有写操作继续使用 Actor、Idempotency-Key、Correlation ID、乐观锁/行锁和 AuditEvent。
- 每个迁移保持单一职责，并支持 upgrade/downgrade。
- 不做与本需求无关的大规模重构。
- 对飞书官方能力不确定时，以官方文档和真实 API 返回为准，不猜测。

## 验证

完成后至少运行并报告真实结果：

```bash
make lint
make test
npm run build
```

同时验证：

- Alembic `upgrade head → downgrade → upgrade head`；
- OAuth/Token 并发刷新测试；
- 消息重复同步不产生重复 Message/Outbox/Candidate；
- Checkpoint 补偿；
- User Token 不出现在日志/API/Codex 输入；
- 有真实凭证时执行真实飞书 smoke；无凭证时明确写 `not_executed`。

## 最终输出

只给我四项：

1. 完成了什么；
2. 关键文件/迁移；
3. 测试与真实验收结果；
4. 尚未验证或受飞书官方能力限制的事项。

不要输出冗长过程记录，不要声称未实际执行的测试已经通过。
