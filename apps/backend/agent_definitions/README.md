# Agent Definitions

每个Agent使用独立目录和版本化配置。正式格式见`docs/design/AGENT_PROTOCOL.md`。

建议结构：

```text
core/message-triage/
professional/contract/
support/reply/
```

每个目录最终包含：

- `agent.yaml`：ID、版本、权限、超时和Schema版本；
- `system.md`：系统指令；
- `output.schema.json`：Pydantic导出的JSON Schema；
- `examples/`：脱敏样例；
- `evaluation/`：固定评测集。

在Codex Runtime完成前，不创建宣称可生产执行的Agent配置。
