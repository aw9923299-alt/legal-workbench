# 知识库与检索设计

## 1. 约束

系统只允许Codex作为推理和生成AI，不引入其他LLM、Embedding API或云端向量服务。因此知识库不能假设存在外部Embedding能力。

PostgreSQL同时承担：

- 文件和版本元数据；
- 文本片段；
- 生效、主体、权限和保密过滤；
- 全文检索；
- `pg_trgm`近似匹配；
- 可选pgvector字段；
- 检索审计。

## 2. 首期检索链路

```text
Query Context
→ 权限/主体/版本/生效状态过滤
→ PostgreSQL Full Text Search
→ pg_trgm 标题、术语和短语相似度
→ 合并和去重候选
→ 确定性 authority 排序
→ Chunk/单 Chunk/Token 三重预算
→ Codex 仅基于 Authorized Context 进行分析和引用
```

首期不依赖向量字段即可上线。

Context Builder 每次检索必须显式提供并记录以下范围：

```text
agent_type + matter_type + jurisdiction + document_type
+ effective_date + source_priority
```

只有命中该授权范围的片段会进入专业 Agent 的 `authorizedContext` 与 `authorizedSourceRefs`。Agent 不持有数据库凭证，也不能直接遍历文件系统、文档表或历史 Matter。

## 3. pgvector策略

数据库启用`vector`扩展，但`knowledge_chunks.embedding`必须允许为空。向量召回只有在以下条件满足后启用：

1. 具有经法务和安全评审批准的本地向量生成方式；
2. 不向未经批准的第三方发送公司资料；
3. 向量版本、维度和生成器版本可追溯；
4. 删除、失效和权限撤销能同步影响向量检索；
5. 回归评测证明向量召回带来实际增益。

不得为满足“使用向量数据库”而使用不可解释、未经批准的向量来源。

## 4. 文档模型

`KnowledgeDocument`保存：

- 对既有 `Document` / `DocumentSegment` 解析结果的引用，不复制文件解析正文；
- 原始文件ID、路径和SHA-256；
- 文件类型和解析状态；
- 公司主体、业务线和事项类型；
- 确定性的 `authority_type`、`authority_role`、效力状态和人工元数据状态；
- 版本、生效日、失效日和批准状态；
- 保密等级和访问策略；
- 删除、撤权和Legal Hold状态。

正式法律依据仅允许 `formal_legal_basis`。法规、行政法规、司法解释、规章和规范性文件映射到该角色；案例/监管指引为 `persuasive_authority`，合同为 `contractual_basis`，公司制度/业务规则为 `internal_basis`，历史意见/内部先例为 `strategy_reference`。该映射由领域代码校验，Codex 无权自行升级来源等级。`superseded/repealed` 不得作为当前正式依据；`unknown` 必须降低置信度并形成缺失信息。

`KnowledgeChunk`保存：

- 文档版本ID；
- 章节、页码、段落等定位信息；
- 文本及规范化文本；
- PostgreSQL `tsvector`；
- 可选`vector`；
- embedding生成器和版本；
- 片段哈希。
- 估算 Token 数、估算器版本和是否为近似值。

## 5. 排序

首期综合评分：

```text
metadata eligibility gate
→ weighted full-text rank
+ trigram similarity
+ document authority score
+ recency/effective score
```

启用向量后：

```text
keyword score
+ vector score
+ authority score
+ metadata score
```

正式制度和批准模板优先于历史事项；历史审核样例只能影响表达和流程，不自动成为法律规则。

首期排序先执行 effective-date 与元数据硬过滤，再按 `source_priority`、全文相关度、`pg_trgm` 相似度、资料权威等级和生效时间确定顺序。每次检索的 Query、过滤器、命中片段和 Correlation ID 均写入只追加审计日志。

最终选择还必须受 `LEGAL_KNOWLEDGE_MAX_CHUNKS`、`LEGAL_KNOWLEDGE_MAX_TOKENS` 和 `LEGAL_KNOWLEDGE_MAX_SINGLE_CHUNK_TOKENS` 限制。检索日志只保存 query hash，不保存敏感 query 正文，并记录候选数、选中 Chunk/Token、重复排除、预算排除、过滤器、各分量分数和预算快照。当前默认值为未完成真实资料审计前的保守运行值，真实导入前必须根据 inventory 校准。

## 6. 引用

每个Agent结论的引用必须定位到：

- 文档版本；
- 页码、章节、段落或行范围；
- 片段哈希；
- 检索时间；
- 当时的生效和权限状态。

前端不能只显示文件名。

Butler 的事实、问题、风险、策略、行动和冲突均保存逐项 source/support refs。最终引用必须属于参与运行的原始授权来源并能解析到飞书消息、附件 Segment、Knowledge Chunk、法规、合同或内部先例；Specialist Run ID 只能作为执行 provenance，不能替代事实或法律依据。

## 7. 本地只读增量导入

```text
make knowledge-import SOURCE="/真实可读/Codex-Obs法务项目"
```

导入器只读扫描源目录，复用现有隔离 PDF/DOCX/TXT/Markdown 解析器，依次形成 `LocalDocumentSource → DocumentVersion → DocumentExtraction → DocumentSegment → KnowledgeDocument → KnowledgeChunk`。SHA-256 相同内容只解析一次；未变化文件仅追加观察记录；内容变化创建新版本；失踪源只标记 `missing`，不删除历史。单文件失败隔离，日志不输出正文，API/Agent 输入不暴露绝对路径。`.noindex` File Provider 后备目录会 fail closed，避免把占位文件当成真实资料。

首次分类仅使用目录、文件名和现有元数据的确定性规则。无法可靠识别的资料保存为 `unknown/pending_metadata`，再由单机知识管理页人工修正类型、法域、效力日期和启停状态，并查看 Chunk 与检索命中。

## 8. 删除和失效

文件删除、版本替代、权限撤销或制度失效时：

1. 标记文档版本不可用于新结论；
2. 从全文和向量检索中过滤；
3. 保留历史AgentRun使用记录；
4. 必要时重新评估依赖该资料的未完成草稿；
5. Legal Hold生效时暂停物理删除。
