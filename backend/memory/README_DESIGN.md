# OpenAgent 记忆系统设计（对齐 Context Engineering：Memory Systems 课程）

本文档将 `05_memory_systems` 模块中的**层级记忆**、**持久化演化**与**重构式记忆**等思想，落到 OpenAgent 的现有架构（Kernel / Runner / RAG / Budget / Trace）上，给出**分阶段**、**可验收**的设计，便于后续实现与评估。

---

## 1. 课程概念 → OpenAgent 映射

| 课程要点 | 在 OpenAgent 中的对应物 / 落点 |
|----------|--------------------------------|
| **Working memory**（秒级、即时加工） | 单次 `run` 内的 `Blackboard` 流、`RunContext.state`、tool loop 中间结果；**不进库**或仅进 trace。 |
| **Short-term memory**（会话级） | 同一 `session_id` 下的多轮对话 turns、最近一次检索状态摘要；可由服务端持久化，与前端 `localStorage` 会话列表**互补**（前端偏展示，后端偏模型上下文）。 |
| **Long-term memory**（跨会话知识） | 现有 **RAG**（SQLite+Qdrant）= 文档型**语义记忆**；本设计中的「用户/任务长期记忆」为**增量层**，需单独命名空间，避免与文档 chunk 混淆。 |
| **Episodic / Semantic / Procedural** | **情节**：对话 turn、工具调用轨迹；**语义**：RAG 证据 + 可选「用户事实」片段；**程序性**：Skill/registry 已覆盖部分策略模板，记忆层可存「成功检索式、常用集合」等元数据。 |
| **Token 预算与层级组装** | 与 `Budget`、`composer.trim_evidence_entries_to_budget`、`build_messages` 同一原则：**记忆写入 prompt 必须经过预算化组装**，而非全量拼接。 |
| **持久化 + 巩固（consolidation）** | run 结束或周期性：摘要、聚类、降冗；写入长期存储；访问计数与衰减可对应课程中的 strength / forgetting。 |
| **重构式记忆（Reconstructive）** | **不默认存整段对话原文**；存 **fragment**（摘要句、实体三元组、工具结果指针），在 `query` 驱动下用检索 +（可选）小型 LLM **组装**成「当前轮可用的记忆上下文」；与「场论吸引子」类比时，可将 **RAG 高密度命中区**视为证据空间的吸引子，记忆检索为在嵌入场中激活邻近片段。 |

---

## 2. 现状与缺口

- **已有**：`session_id` 贯通 WS → `KernelEngine.run_chat` → trace；`Blackboard` 仅单次 run；`build_messages` 为单轮 **system + 单条 user**（含 EVIDENCE + QUESTION）；RAG 提供外部**文档记忆**。
- **已补**：会话 turn、滚动摘要、规则片段 + 向量检索注入（Phase A–C）；**缺口**：跨会话长期用户画像、LLM 式片段抽取/重构融合、记忆专用 eval 指标（Phase D）。

---

## 3. 设计目标（约束）

1. **受控**：记忆读写不扩大 tool allowlist，不绕过 ToolGateway；敏感片段遵守 constitution 与单用户隐私假设（仍建议可配置「禁止上云持久化」）。
2. **可解释**：写入 trace 的事件类型清晰（如 `memory_read` / `memory_write` / `memory_consolidate`），便于 eval 与调试。
3. **可退化**：检索或组装失败时，行为退化为**当前单轮**（与今天一致），不阻塞主流程。
4. **与 RAG 正交**：文档证据仍走 `EvidenceEntry` + citation 规则；**记忆块**单独区块（例如 `MEMORY_CONTEXT`），避免与 `chunk_id` 引用混用，防止伪造引用。

---

## 4. 逻辑架构（推荐）

```
                    ┌─────────────────────────────────────┐
                    │         MemoryOrchestrator           │
                    │  assemble_for_prompt(session, query) │
                    └──────────────┬──────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
 ┌───────────────┐        ┌───────────────┐        ┌─────────────────┐
 │ SessionStore  │        │ FragmentIndex │        │ RAG (existing)   │
 │ (episodic     │        │ (semantic /   │        │ document         │
 │  turns, meta) │        │  reconstruct) │        │ evidence         │
 └───────────────┘        └───────────────┘        └─────────────────┘
```

- **MemoryOrchestrator**：唯一入口，负责按预算拉取 session 摘要、fragment、（可选）RAG 侧「用户记忆集合」，输出 **结构化块** 给 `composer`。
- **SessionStore**：按 `session_id` 追加 turn；支持按 token 预算返回「最近 N 轮」或「滚动摘要 + 最近 K 轮」。
- **FragmentIndex**：向量或 FTS（可与现有 SQLite 模式一致）；存 fragment 记录，供重构式检索；**不**要求逐字还原历史。

---

## 5. 数据模型（草案）

### 5.1 会话情节（SessionStore）

| 字段 | 说明 |
|------|------|
| `session_id` | 与 WS / trace 一致 |
| `run_id` | 可选，关联 trace |
| `role` | `user` / `assistant` |
| `content` | 正文（可压缩存储） |
| `created_at` | 时间戳 |
| `token_estimate` | 可选，便于预算 |

### 5.2 记忆片段（FragmentStore，重构式）

| 字段 | 说明 |
|------|------|
| `fragment_id` | UUID |
| `session_id` | 来源会话，可为空（巩固后） |
| `type` | `semantic` / `episodic` / `procedural` / `preference` 等 |
| `text` | 短文本或结构化 JSON 字符串 |
| `embedding` | 可选；或进 Qdrant 独立 collection `user_memory` |
| `strength` / `access_count` / `last_accessed` | 巩固与衰减 |
| `source_run_ids` | 溯源 |

### 5.3 巩固产物（可选）

- `session_summary`：会话级滚动摘要，替代早期 turn 以省 token。
- `user_profile_facts`：极少条、高置信、人工可审（未来 UI）。

---

## 6. 与核心代码的集成点

1. **`KernelEngine.run_chat`**：在创建 `RunContext` 之后、调用 `ChatRunner` 之前，调用 `MemoryOrchestrator.prepare(ctx, query)`，将结果挂到 `ctx.state["memory_pack"]` 或显式参数。
2. **`composer.build_messages`**：扩展为可选的多段上下文：  
   `system` 不变原则下，在 **user** 拼装中增加 `MEMORY_CONTEXT:`（若有）+ 原有 `EVIDENCE` + `USER QUESTION`；或采用 `messages[]` 多轮形式时，仍须 **单独系统消息说明**：记忆非文档证据，不得产生虚假 `chunk_id` 引用。
3. **`ChatRunner.run`（结束）**：异步或同步触发 `SessionStore.append_turns`；可选队列触发 `consolidate_session`（受 `Budget` 或独立后台任务限制）。
4. **Trace**：`memory_read`（条数、来源层）、`memory_write`（类型、大小）、`memory_consolidate`（是否执行、摘要长度）。

---

## 7. 分阶段路线图

### Phase A — 会话级情节记忆（最小可用）✅ 已实现

- **SessionStore**：`chat_session_turn` 表 + `SQLiteStore.append_chat_session_turn` / `fetch_chat_session_turns_recent`。
- **KernelEngine**：在 `run_started` 之后读历史，`memory_read` trace；run 成功后 `memory_write` 并持久化 user/assistant（assistant 去掉 citations 脚注）。
- **composer.build_messages**：注入 `conversation_history`（system 附 `[Memory]` 说明）；最后一条 user 仍为 EVIDENCE + USER QUESTION。
- **配置**：`memory.enabled` / `session_max_turns` / `session_max_history_tokens`（见 `config/openagent.yaml`）。
- **验收**：同一 `session_id` 连续提问可利用前文；不同 `session_id` 隔离。

### Phase B — 巩固与预算化摘要 ✅ 已实现

- **表** `chat_session_summary`：`summary_text`、`covers_until_id`（该 id 及更早的 turn 已由摘要覆盖，不再逐字注入）。
- **触发**：会话总轮数 ≥ `consolidate_after_turns`，且「未覆盖的尾部」消息数 > `keep_recent_rounds * 2` 时，将超出部分折叠进摘要（一次 `llm.chat`，计入 `Budget`，`memory_consolidate` trace）。
- **读取**：`fetch_chat_session_turns_after(session_id, covers_until_id)` + 摘要注入 `build_messages(..., rolling_summary=...)`；尾部仍受 `session_max_turns` / `session_max_history_tokens` 约束。
- **配置**：`consolidation_enabled`、`keep_recent_rounds`、`consolidation_max_output_tokens`、`rolling_summary_max_tokens`（见 `config/openagent.yaml`）。

### Phase C — Fragment + 重构式检索（课程 04 对齐）✅ 已实现

- **存储**：`memory_fragment`（SQLite 全文）+ Qdrant `storage.qdrant.memory_collection_name`（默认 `openagent_memory`）。
- **规则抽取**：`fragment_extract.extract_fragments_from_turn`（默认路径，免额外 LLM）。
- **LLM 抽取**（可选，`fragment_llm_extraction_enabled`）：`fragment_llm.extract_fragments_via_llm` 输出 JSON `{"fragments":[...]}`，计入 **Budget**，失败或空则回退规则；trace `memory_fragment_extract_llm`；回退时 `memory_fragment_extract_fallback`。
- **检索注入**：稠密检索 Top-K → 模板 `•` 列表；若 `reconstruct_llm_enabled`，`fragment_llm.reconstruct_context_via_llm` 再融为短正文（计入 Budget），失败则用模板。Trace：`memory_reconstruct_llm`。
- **配置**：`fragment_llm_extraction_max_tokens` / `reconstruct_llm_max_tokens` 等（见 `openagent.yaml`）。

### Phase D — 元记忆与评估（最小实现 ✅）

- **`backend/memory/eval_report.py`**：`summarize_memory_trace_events(events)` 聚合单次 run 内与记忆相关的 trace 类型（read/write、consolidate、fragments_write、LLM 抽取/重构成功失败次数、摘要/历史长度峰值等），便于接入 `backend/eval_` 的 EvalReport 或离线脚本。
- **未实现**（留作 eval 数据集 + L2/L3）：记忆命中率、与文档 citation 混淆的自动判别、跨 session 纵向一致性需 golden case。

---

## 8. 风险与对策

| 风险 | 对策 |
|------|------|
| Prompt 膨胀 | 严格 token 预算；摘要优先；fragment 短文本 |
| 记忆与 RAG 引用混淆 | 分区块 + constitution 明确禁止对记忆内容打文档 citation |
| 隐私与数据残留 | 配置项：禁用长期层；会话删除 API；文档化 localStorage 与服务端双轨 |
| 多智能体 `multi` 模式 | 子 agent 默认只读父会话摘要或隔离子黑板；写回需经 Orchestrator 合并策略 |

---

## 9. 配置项（建议）

在 `openagent.yaml` 下 `memory:` 段（已实现项）：

- `enabled` / `session_max_turns` / `session_max_history_tokens`
- Phase B：`consolidation_enabled` / `consolidate_after_turns` / `keep_recent_rounds` / `consolidation_max_output_tokens` / `rolling_summary_max_tokens`
- Phase C：`fragments_enabled` / `fragment_top_k` / `fragments_extract_max` / `fragment_max_chars` / `fragment_context_max_tokens` / `fragment_llm_extraction_enabled` / `fragment_llm_extraction_max_tokens` / `reconstruct_llm_enabled` / `reconstruct_llm_max_tokens`；Qdrant：`memory_collection_name`
- Phase D：见 `memory/eval_report.py`（trace 聚合，非 LLM judge）

---

## 10. 参考阅读（课程内）

- `00_memory_architectures.md`：层级、场论类比、协议化编排。
- `01_persistent_memory.md`：持久化、巩固、图/层模型。
- `04_reconstructive_memory.md`：片段存储、上下文驱动组装、与 token 瓶颈的对应关系。
- `attractor_dynamics.md`（若结合 RAG）：将检索空间理解为动态场时的**稳定性与干扰**，用于解释「为何需要 rerank + 预算截断」。

---

## 11. 小结

OpenAgent 的**文档记忆**已由 RAG 承担；本设计补齐 **会话情节**、**滚动摘要**、**片段向量检索**，以及可选的 **LLM 抽取/重构**（均受 **Budget** 约束），trace 可经 **eval_report** 汇总供评估流水线使用。
