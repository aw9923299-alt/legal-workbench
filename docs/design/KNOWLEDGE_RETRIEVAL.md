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
→ Codex基于有限候选进行相关性选择和引用
```

首期不依赖向量字段即可上线。

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

- 原始文件ID、路径和SHA-256；
- 文件类型和解析状态；
- 公司主体、业务线和事项类型；
- 文档类别：正式制度、模板、历史事项、审核样例；
- 版本、生效日、失效日和批准状态；
- 保密等级和访问策略；
- 删除、撤权和Legal Hold状态。

`KnowledgeChunk`保存：

- 文档版本ID；
- 章节、页码、段落等定位信息；
- 文本及规范化文本；
- PostgreSQL `tsvector`；
- 可选`vector`；
- embedding生成器和版本；
- 片段哈希。

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

## 6. 引用

每个Agent结论的引用必须定位到：

- 文档版本；
- 页码、章节、段落或行范围；
- 片段哈希；
- 检索时间；
- 当时的生效和权限状态。

前端不能只显示文件名。

## 7. 删除和失效

文件删除、版本替代、权限撤销或制度失效时：

1. 标记文档版本不可用于新结论；
2. 从全文和向量检索中过滤；
3. 保留历史AgentRun使用记录；
4. 必要时重新评估依赖该资料的未完成草稿；
5. Legal Hold生效时暂停物理删除。
