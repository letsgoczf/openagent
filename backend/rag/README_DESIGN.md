## backend/rag 详细设计（Qdrant + SQLite FTS5 + reranker + Evidence Builder）

本目录实现的是 **OpenAgent 内的检索与证据子系统**，由 Kernel / Runners 在对话与工具循环中按需调用；整体产品形态仍是 **Agent 系统**，请勿把本模块等同于项目全称。

### 0. 与 demo 教材的关系
- ``demo/04_rag_recipes.py`` 中的 ``HybridRAG``（向量召回 + 关键词、按 ``keyword_weight`` / ``embedding_weight`` 融合）与线上实现的 **dense + FTS5 + `w_dense` / `w_keyword`** 语义对齐；配方说明亦见 ``demo/04_retrieval_augmented_generation/`` 下 Markdown。
- 生产代码以本文件与 ``config/openagent.yaml`` 的 ``rag.recall`` 为准；``backend/rag/recipes_bridge.py`` 提供与 demo 权重换算一致的辅助函数。

### 1. 目标
- 实现“最优检索”pipeline：dense 召回 + keyword 召回 + merge 去重 + rerank 重排 + EvidenceEntry 组装
- 输出可追溯证据：最终所有证据都可映射到 `chunk_id/version_id/source_span`

### 2. 检索 pipeline（在线）
输入：
- `query`（用户问题）
- `version_scope`（文档版本范围策略：默认 latest_active）
- `rag_views`（由 registry/profile 提供）
- `budget`（用于控制候选规模/证据数量）
输出：
- `retrieval_state`（给前端 Trace 展示的计数信息）
- `evidence_entries`（EvidenceEntry v1 列表，带截断 snippet + tokens）
- `candidate_debug`（可选：用于 trace/debug）

#### 2.1 Dense recall（Qdrant）
流程：
1. 从 Qdrant collection 获取 top_k_dense（如 50）的候选 chunk_id
2. 过滤/降噪：
   - 版本范围：只取允许的 `version_id`
   - metadata 过滤：只允许 registry 暴露的 filters
输出：
- `c_dense: List[chunk_id + dense_score + payload_meta]`

#### 2.2 Keyword recall（SQLite FTS5）
流程：
1. 在 SQLite FTS5 对 chunk_text 做检索，取 top_k_kw（如 20~35）
2. 过滤：
   - version_scope
   - chunk 只取允许 origin（可选：table/text 优先）
输出：
- `c_kw: List[chunk_id + kw_score]`

#### 2.3 Merge & Dedup
- 把 c_dense 与 c_kw 按 chunk_id 合并，形成去重后的候选集合
- score 归一化策略：
  - 实现要求：选一种固定可复现方法（如 min-max 或 z-score）
  - 把 dense/keyword 的分数合成 `merged_score`
输出：
- `c_merged: List[candidate]`，长度受 `max_candidates` 限制（如 100~120）

#### 2.4 rerank（重排器）
- 输入给 reranker：`query + chunk_text_snippet`（必要时 table/text 优先）
- 输出：按相关性排序的 top_n（进入 evidence builder）
工程要求：
 - reranker 的选择（模型名/版本）需写入 trace
 - rerank top_n 默认 8~12

### 3. Evidence Builder（EvidenceEntry v1）
目标：
- 把 evidence 变成“统一模板 entry”，并生成截断 snippet 与 token 缓存

EvidenceEntry v1：
- 字段固定：chunk_id/version_id/origin + location + content(snippet)
- 截断策略 v1：你已选“截断内容”，并缓存 token

输出：
- `evidence_entries[]`：每条 evidence entry：
  - `chunk_id`
  - `version_id`
  - `origin_type`
  - `location_summary`（用于 citations 展示）
  - `evidence_snippet_text_v1`
  - `evidence_entry_tokens_v1`

工程要求（性能）：
- evidence_entry_tokens_v1 必须可缓存（chunk 首次生成后持久化）
- 检索 on_miss / evidence 预算计算必须使用缓存 token，不做重复 token 计数

### 4. citations 生成（与上游 Kernel 对齐）
citations 必来自：
- `chunk_id -> SQLite chunk + source_span + version_id`

Kernel 在生成前后必须校验：
- citations chunk_id 存在于本次 retrieval evidence_entries

### 5. 验收标准（最小）
- 对同一 query，在固定配置下 evidence_entries 排序稳定（允许模型随机，但 rerank 与 merge 行为可复现）
- citations 每条都能映射到 chunk_id/version_id/source_span（强溯源）
- Trace 中 retrieval_update 的计数与 evidence_entries 数量一致

### 6. 后续扩展（与 `demo/04_retrieval_augmented_generation/` 对照）

以下条目 **不改变** 当前 P3 最小管线默认行为；作为演进 backlog。教材目录：`demo/04_retrieval_augmented_generation/`。

**全局原则**

- **溯源**：任意扩展召回的最终 `EvidenceEntry` / `Citation` 仍须满足 §4（仅引用 SQLite 中已存在的 `chunk_id`）。
- **可观测**：新召回通道须在 `retrieval_state` 中计数，在 `candidate_debug`（或等价 trace payload）中可区分来源；Eval 回放须能固定排序与融合策略版本。
- **Budget**：多跳、图扩展、额外 rerank 调用须扣减 Kernel `Budget`（`max_tool_rounds` / token / 墙钟），不得在 `backend/rag` 内绕过 Budget 私自循环。

---

#### 6.1 理论与上下文组装（`00_rag_fundamentals.md`）

| 子项 | 说明 | 建议产出 | 配置（草案） |
|------|------|----------|--------------|
| **6.1.1 Cross-encoder rerank** | 在 `merged_score` 之后用查询–段落对重排；trace 记录 `model_id` / `provider`。 | 扩展 `backend/rag/reranker.py`；可选 `backend/rag/cross_encoder_rerank.py`；`tests/unit/test_rag.py` | `rag.rerank.strategy: cross_encoder` 已预留；补 `timeout_ms`、`batch_size` |
| **6.1.2 去冗（MMR 等）** | 在进入 Evidence Builder 前对候选 `chunk_id` 做多样性筛选，降低相邻 chunk 冗余。 | `backend/rag/dedup_redundant.py` 或并入 `merge.py`；参数：`lambda_diversity`、`embedding_provider` 可选 | `rag.recall.mmr_enabled`、`mmr_lambda` |
| **6.1.3 Context assembly（块压缩）** | 在 `runners/composer.py` 侧将多条 evidence 压入单上下文（章节标题、编号列表），**不**改写 SQLite 正文；可把「组装后 token 数」写入 trace。 | P4 `composer.py` + 可选 `backend/rag/context_assembler.py` | `evidence.max_assembled_tokens`（与单条 `max_evidence_entry_tokens` 区分） |
| **6.1.4 检索效用指标（离线）** | nDCG、重复率、覆盖率等；供 P9 Eval，不阻塞在线路径。 | `backend/eval_/retrieval_metrics.py`（或 `backend/rag/metrics.py` 仅导出纯函数） | 无；由 eval fixture 驱动 |

**验收（6.1）**：固定 query + fixture 下 rerank 顺序可复现；开启 MMR 后 Top-N 中同页重复 chunk 比例下降（用统计断言）；cross-encoder 失败时降级到 `merged_score` 并写 trace。

---

#### 6.2 模块化与协议（`01_modular_architectures.md`）

| 子项 | 说明 | 建议产出 | 与 P6 关系 |
|------|------|----------|------------|
| **6.2.1 Recall 协议** | 定义 `RecallResult`（`hits: list[RecallHit]`，`channel: dense|keyword|graph`）。 | `backend/rag/protocols.py`（TypedDict / Pydantic） | — |
| **6.2.2 组件注册** | `dense_recall` / `keyword_recall` / 未来 `graph_recall` 实现同一 `RecallFn` 签名；便于 mock。 | 各 recall 模块导出统一入口；`RetrievalService` 仅依赖协议 | `rag_views` 决定启用通道与白名单 filter |
| **6.2.3 指标钩子** | 每次 recall 返回 `latency_ms`、`hit_count`；聚合进 `retrieval_state.timings_ms`（已有字段可扩展）。 | 扩展 `service.py`；可选 `backend/rag/instrumentation.py` | Trace 与 WS `chat.retrieval_update` 对齐 |
| **6.2.4 配置 schema** | 各通道独立子配置块，避免单一巨型 dict。 | `config/openagent.yaml` + `config_loader.py` 中 `Rag*Config` 细化 | Registry 只读 policy id，不内嵌具体超参 |

**验收（6.2）**：单测可对单一 recall 打桩，其余通道关闭仍可跑通 `retrieve`；配置缺省与 P3 行为二进制一致。

---

#### 6.3 Agentic / 多跳检索（`02_agentic_rag.md`）

| 子项 | 说明 | 建议产出 | 执行位置 |
|------|------|----------|----------|
| **6.3.1 Query rewrite** | HyDE、子问题分解等；**不**在 RAG 内调 LLM 隐式循环，由 Runner 传入 `queries: list[str]` 或 Kernel 逐步调用。 | `backend/rag/query_transform.py`（纯函数 + 可选 LLM 适配器注入） | P4 `chat_runner` / P10 Planner |
| **6.3.2 多跳合并** | 对多路 `RetrievalResult` 做 union + 再 merge/rerank；每跳 `sequence` 写入 `trace_event`。 | `backend/rag/multi_hop.py`；或 Kernel 编排循环 | `kernel/engine.py` + `trace.py` |
| **6.3.3 停止策略** | 证据充分性启发式（命中数、score 阈值）对接 P10 Reflect，避免无限检索。 | `backend/runners/reflect.py`（远期）与 `RetrievalService` 返回的 `retrieval_state` 字段约定 | Budget `max_tool_rounds` |

**验收（6.3）**：同一 run 内多跳产生的全部 `chunk_id` 可被 citation 校验；超额预算时最后一步为「降级合并」并带 `trace` 原因码。

---

#### 6.4 图增强 RAG（`03_graph_enhanced_rag.md`）

| 子项 | 说明 | 建议产出 | 存储 |
|------|------|----------|------|
| **6.4.1 实体与边** | 从 chunk / table 抽取实体、关系；边指向 `chunk_id` 或 `version_id` 范围。 | `backend/rag/graph/`：`schema.md`（设计）、`graph_store.py`（SQLite 附表或独立 DB） | 新增迁移脚本或 P1 schema 增量 |
| **6.4.2 graph_recall** | 给定 query 向量或实体链接，游走 Top-K 结点，映射回 `chunk_id`。 | `backend/rag/graph_recall.py` | 与 Qdrant 并行，merge 阶段加权 |
| **6.4.3 融合** | `c_graph` 与 dense/keyword 同步 min-max 或独立通道权重 `w_graph`。 | 扩展 `merge.py`、`config_loader.RagRecallConfig` | `rag.recall.w_graph` |

**验收（6.4）**：图召回仅返回已入库 chunk；缺失映射时丢弃并计数 `graph_dropped`；`retrieval_state` 含 `graph_hits`。

---

#### 6.5 高级应用与垂直场景（`04_advanced_applications.md`）

| 子项 | 说明 | 建议产出 |
|------|------|----------|
| **6.5.1 Profile 级 RAG 预设** | 法律/技术等切换 `top_k`、权重、`allowed_origin_types`、prompt addon；仅存 Registry / YAML。 | P6 `skill_registry` + `rag.recall` profile 覆盖 |
| **6.5.2 长文档 / 层级 chunk** | 父 chunk–子 chunk；dense 打在子块，展示合并到父级 `location_summary`。 | P2 摄取 + SQLite `parent_chunk_id`（若引入） |
| **6.5.3 多模态** | 向量与元数据引用图片页；OCR chunk `origin_type=ocr` 与 P8 衔接。 | P8 + `payload_meta.image_id` 已有预留 |

**验收（6.5）**：换 Profile 仅改配置与 registry，不改 `RetrievalService` 核心控制流。

---

#### 6.6 建议实施顺序（与优先级）

```text
6.2（命名与协议） → 6.1.1（cross-encoder） → 6.1.2（MMR） → 6.3（多跳，依赖 P4 Kernel）
→ 6.4（图，依赖 schema 与摄取） → 6.5（产品与垂直）
```

**原则（重申）**：新增通道须在 trace 中可区分；失败须可降级；Eval 须可固定随机种子外的一切参数。

