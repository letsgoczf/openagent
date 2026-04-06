## OpenAgent 开发计划

> 基于 `OPENAGENT_ARCHITECTURE.md` 及各模块 `README_DESIGN.md` 制定。
> 当前状态：全部模块仅有设计文档，零代码。`.venv` 已安装部分依赖（ollama, qdrant-client）。
>
> **产品定位**：工程目标是 **Agent 系统**（Kernel、Runners、工具与编排）；仓库中的 `backend/rag` 与配置里的 `rag:` 是 **检索与证据子系统**，为 Agent 提供可溯源的 grounded 上下文，勿将整体项目理解为「只做 RAG」。

---

### 模块依赖关系

```text
config ─────────────────────────────────────────────────┐
   ↓                                                     │
storage（SQLite schema + Qdrant setup）                   │
   ↓                                                     │
models（LLM Adapter + TokenizerService）                  │
   ↓                                                     │
registry（Tool / Rag / Skills 注册表）                     │
   ↓                                                     │
ingestion（PDF/PPTX → chunk → SQLite + Qdrant）           │
   ↓                                                     │
检索与证据（`rag` 子系统：dense + keyword + merge + rerank） │
   ↓                                                     │
kernel + runners（RunContext + Budget + Agent 聊天循环）    │
   ↓                                                     │
api（FastAPI + WebSocket）  ← 第一次端到端对话 ─────────────┘
   ↓
frontend（React 对接 WebSocket）
   ↓
ocr / eval_ / evolve（可选 / 离线）
```

---

### 里程碑总览

| 里程碑 | 阶段 | 预估 | 产出 |
|---|---|---|---|
| M0 | P0 脚手架 | 0.5 天 | 项目可安装、配置可加载 |
| M1 | P1 存储 + 模型 | 2 天 | SQLite/Qdrant 就绪，LLM 可调用 |
| M2 | P2 文档摄取 | 2 天 | word/excel/text/md/PDF/PPTX 可导入并建索引 |
| M3 | P3 检索 + 证据 | 2 天 | 检索子系统可输出 evidence（供 Agent 消费） |
| **M4** | **P4 Kernel + Runners** | **2.5 天** | **第一次端到端对话（脚本级）** |
| M5 | P5 API 层 | 1.5 天 | WebSocket + REST 对外可访问 |
| M6 | P6 Registry | 1 天 | 工具/Skills 白名单受控 |
| **M7** | **P7 前端** | **3 天** | **浏览器完整交互链路** |
| M8 | P8 OCR | 1.5 天 | on_miss OCR 可选通道 |
| M9 | P9 Eval + Evolve | 2.5 天 | 离线评估与自主进化 |
| M10 | P10 高级特性 | 待定 | PAOR 推理循环 + 多 Profile |

**关键路径：P0 → P1 → P2 → P3 → P4（约 9 天）达到首次对话。**
**P0 → P7（约 14.5 天）达到可演示产品。**

---

### P0：项目脚手架（~0.5 天）

**目标：** 项目可安装、配置可读取、包结构可导入。

#### 任务清单

| # | 任务 | 产出文件 |
|---|---|---|
| 0.1 | 创建 `pyproject.toml`，声明核心依赖 | `pyproject.toml` |
| 0.2 | 每个 backend 子模块加 `__init__.py` | `backend/*/__init__.py` |
| 0.3 | 创建配置模板 | `config/openagent.yaml` |
| 0.4 | 实现配置加载器（YAML 读取 + env 覆盖 + 校验） | `backend/config_loader.py` |
| 0.5 | 补全 `.gitignore`（data/, .venv/, *.db, __pycache__） | `.gitignore` |

#### 核心依赖（pyproject.toml）

```text
fastapi, uvicorn[standard], websockets
openai, ollama, tiktoken
qdrant-client
pdfplumber, python-pptx
pydantic >= 2.0
pyyaml
```

#### 验收标准

- `pip install -e .` 成功
- `python -c "from backend.config_loader import load_config; load_config()"` 正常返回配置对象

---

### P1：存储层 + 模型层（~2 天）

**目标：** SQLite/Qdrant 可读写，LLM 可调用并流式输出，TokenizerService 可计数。

#### P1a：Storage（~1 天）

| # | 任务 | 产出文件 |
|---|---|---|
| 1.1 | SQLite 建表：document, document_version, chunk, page_stats, trace_event | `backend/storage/schema.py` |
| 1.2 | FTS5 虚拟表：对 chunk_text 建全文索引 | 同上 |
| 1.3 | SQLite CRUD 封装：insert_chunk, query_fts5, get_chunk_by_id 等 | `backend/storage/sqlite_store.py` |
| 1.4 | Qdrant collection 初始化 + 向量 upsert/search 封装 | `backend/storage/qdrant_store.py` |
| 1.5 | 单元测试：建表、插入、FTS5 检索、Qdrant 写入/查询 | `tests/unit/test_storage.py` |

#### SQLite 核心表

```text
document:          doc_id, file_path, file_name, file_type, created_at
document_version:  version_id, doc_id, content_hash, extraction_version, tokenizer_id, status
chunk:             chunk_id, version_id, origin_type, chunk_index, chunk_text,
                   source_span_json, evidence_entry_tokens_v1, evidence_snippet_text_v1,
                   page_number, slide_number, table_id
page_stats:        version_id, unit_type, unit_number, effective_text_tokens, has_text, table_count
trace_event:       event_id, run_id, sequence, event_type, payload_json, created_at
```

#### P1b：Models（~1 天）

| # | 任务 | 产出文件 |
|---|---|---|
| 1.6 | 统一 LLM Adapter 抽象接口（chat + stream） | `backend/models/base.py` |
| 1.7 | OpenAI Adapter（含流式 delta 输出） | `backend/models/openai_adapter.py` |
| 1.8 | Ollama Adapter | `backend/models/ollama_adapter.py` |
| 1.9 | vLLM Adapter（兼容 OpenAI v1 接口） | `backend/models/vllm_adapter.py` |
| 1.10 | TokenizerService（tiktoken 为主，支持配置覆盖） | `backend/models/tokenizer.py` |
| 1.11 | 工厂函数：根据配置创建对应 adapter + tokenizer | `backend/models/factory.py` |
| 1.12 | 单元测试：token 计数一致性、adapter mock 测试 | `tests/unit/test_models.py` |

#### 验收标准

- SQLite：插入 chunk → FTS5 检索 → 返回正确 chunk_id
- Qdrant：upsert 向量 → search → 返回正确 chunk_id + score
- Models：向 OpenAI/Ollama 发消息 → 流式收到回复
- Tokenizer：`count_tokens("hello world")` 返回正整数

---

### P2：文档摄取（~2 天）

**目标：** PDF/PPTX 导入后，SQLite 中有 chunk + FTS5 索引，Qdrant 有向量，page_stats 有数据。

| # | 任务 | 产出文件 |
|---|---|---|
| 2.1 | PDF text 抽取（pdfplumber）：按页提取文本块 | `backend/ingestion/pdf_extractor.py` |
| 2.2 | PDF table 抽取：表格结构化 → table_ref + cell_text | 同上 |
| 2.3 | PPTX text + table 抽取（python-pptx） | `backend/ingestion/pptx_extractor.py` |
| 2.4 | IR 中间表示定义 | `backend/ingestion/ir.py` |
| 2.5 | Chunkization：按 origin 分 chunk，计算 source_span | `backend/ingestion/chunker.py` |
| 2.6 | Writer：chunk 写入 SQLite + 向量写入 Qdrant + FTS5 + evidence token 缓存 | `backend/ingestion/writer.py` |
| 2.7 | DocumentVersioning：content_hash → version_id | `backend/ingestion/versioning.py` |
| 2.8 | page_stats 计算与写入 | `backend/ingestion/page_stats.py` |
| 2.9 | Ingestion Job 编排（串联 2.1~2.8） | `backend/ingestion/job.py` |
| 2.10 | 集成测试：小样本 PDF/PPTX 导入 → 验证 chunk/FTS5/Qdrant/page_stats | `tests/integration/test_ingestion.py` |

#### 验收标准

- 一个 PDF 导入后：SQLite chunk 表 > 0 行，FTS5 可检索，Qdrant 有向量，page_stats 有数据
- chunk.source_span_json 包含 page_number + 定位信息
- version_id 由 content_hash 决定，重复导入不会产生新版本

---

### P3：检索 + 证据构建（~2 天）

**目标：** 给定 query 返回排序后的 evidence entries，每条可溯源到 chunk_id / version_id / source_span。

| # | 任务 | 产出文件 |
|---|---|---|
| 3.1 | Dense recall：Qdrant top_k 检索 + version_scope 过滤 | `backend/rag/dense_recall.py` |
| 3.2 | Keyword recall：SQLite FTS5 top_k 检索 | `backend/rag/keyword_recall.py` |
| 3.3 | Merge & Dedup：chunk_id 去重 + score 归一化（min-max） | `backend/rag/merge.py` |
| 3.4 | Reranker：MVP 先用 merged_score 排序，预留 cross-encoder 接口 | `backend/rag/reranker.py` |
| 3.5 | Evidence Builder：EvidenceEntry v1 模板 + 截断 snippet + token 缓存 | `backend/rag/evidence_builder.py` |
| 3.6 | Citations 生成：chunk_id → source_span + version_id | `backend/rag/citation.py` |
| 3.7 | RetrievalService 统一入口（串联 3.1~3.6） | `backend/rag/service.py` |
| 3.8 | 单元测试：merge 去重、evidence token 缓存、citation 校验 | `tests/unit/test_rag.py` |

#### EvidenceEntry v1 结构

```text
EvidenceEntry:
  chunk_id:                  str
  version_id:                str
  origin_type:               text | table | ocr
  location_summary:          str      # "Page 3, Para 2" 或 "Slide 5, Table 1"
  evidence_snippet_text_v1:  str      # 截断后的 chunk 文本
  evidence_entry_tokens_v1:  int      # 缓存的 token 数
  dense_score:               float | None
  keyword_score:             float | None
  rerank_score:              float | None
```

#### 验收标准

- 给定 query + 已导入文档，返回 top-N evidence entries
- 每条 entry 有 chunk_id / version_id / source_span / snippet / token 数
- 同一 query 在固定配置下，排序结果稳定

---

### P4：Kernel + Runners（~2.5 天）—— 里程碑：首次对话

**目标：** 在脚本中完成"query → 检索 → 组装 prompt → LLM 生成 → citations"完整链路。

#### P4a：Kernel（~1.5 天）

| # | 任务 | 产出文件 |
|---|---|---|
| 4.1 | RunContext 数据结构（run_id, session_id, budget, state） | `backend/kernel/run_context.py` |
| 4.2 | Budget 控制器（max_llm_calls / max_tool_rounds / wall_clock / token_budget） | `backend/kernel/budget.py` |
| 4.3 | Blackboard（append-only 事件流 + 命名空间 + 快照视图） | `backend/kernel/blackboard.py` |
| 4.4 | Trace 写入器（结构化事件 → SQLite trace_event） | `backend/kernel/trace.py` |
| 4.5 | Router stub（MVP 固定返回 mode=single） | `backend/kernel/router.py` |
| 4.6 | Kernel 编排入口（初始化 → router → 委派 runner → 完成） | `backend/kernel/engine.py` |

#### P4b：Runners（~1 天）

| # | 任务 | 产出文件 |
|---|---|---|
| 4.7 | Prompt Composer：system prompt（constitution）+ evidence block 拼装 | `backend/runners/composer.py` |
| 4.8 | Chat Runner（single profile）：retrieve → compose → generate → finalize | `backend/runners/chat_runner.py` |
| 4.9 | Tool Loop（基础版）：model tool_call → schema 校验 → 执行 → 写 blackboard | `backend/runners/tool_loop.py` |
| 4.10 | 端到端脚本测试 | `scripts/chat_once.py` |

#### 验收标准

- `python scripts/chat_once.py --query "xxx"` 输出带 citations 的完整回答
- Trace 中可见 retrieval_update / evidence_update / completed 事件序列
- Budget 耗尽时正确停止并降级

---

### P5：API 层（~1.5 天）

**目标：** 后端对外可通过 WebSocket 和 REST 访问。

| # | 任务 | 产出文件 |
|---|---|---|
| 5.1 | FastAPI app 骨架 + CORS + 启动配置 | `backend/api/app.py` |
| 5.2 | Pydantic 请求/响应模型（统一字段命名） | `backend/api/schemas.py` |
| 5.3 | WebSocket 端点（`/ws`）：chat.start → Kernel → 事件流推送 | `backend/api/ws_handler.py` |
| 5.4 | REST：`POST /v1/documents/import` | `backend/api/routes/documents.py` |
| 5.5 | REST：`GET /v1/jobs/{job_id}`, `GET /v1/traces/{run_id}` | `backend/api/routes/jobs.py`, `traces.py` |
| 5.6 | 统一错误处理 + WS 断连恢复策略 | `backend/api/errors.py` |
| 5.7 | 启动脚本 | `scripts/start_server.py` |

#### 验收标准

- `uvicorn backend.api.app:app` 启动成功
- WebSocket 连接后发 chat.start → 收到 chat.delta 流式 + chat.completed
- `POST /v1/documents/import` 上传文档文件 → 返回 job_id → job 完成

---

### P6：Registry（~1 天）

**目标：** 工具/Skills/RAG 白名单受控，未注册资源访问被拒绝。

| # | 任务 | 产出文件 |
|---|---|---|
| 6.1 | Tool Registry：从配置加载工具定义 + JSON Schema | `backend/registry/tool_registry.py` |
| 6.2 | Tool Gateway：参数校验 / 超时 / 脱敏预览 | `backend/registry/tool_gateway.py` |
| 6.3 | Rag Registry：collection + filter 策略管理 | `backend/registry/rag_registry.py` |
| 6.4 | Skills Registry：manifest 加载 + trigger 匹配 + prompt_addon 注入 | `backend/registry/skill_registry.py` |
| 6.5 | 统一接口暴露给 Kernel | `backend/registry/service.py` |
| 6.6 | 单元测试：未注册 tool 拒绝、Skill allowlist 校验 | `tests/unit/test_registry.py` |

#### 验收标准

- 模型尝试调用未注册 tool → 拒绝并写 trace
- Skill tools_allowlist 之外的工具调用 → 失败
- RAG 只能访问 registry 暴露的 collection_id

---

### P7：前端（~3 天）

**目标：** 浏览器中完成"上传文档 → 提问 → 流式回答 + citations 溯源"完整链路。

| # | 任务 | 产出文件 |
|---|---|---|
| 7.1 | Next.js 项目初始化（已有设计方向，深色主题 + 霓虹强调色） | `frontend/` |
| 7.2 | WebSocket 连接管理 hook | `frontend/src/hooks/useChat.ts` |
| 7.3 | Chat 页面：消息列表 + 输入框 + 流式渲染 | `frontend/src/app/chat/page.tsx` |
| 7.4 | Evidence 面板：检索过程 trace + citation 来源展示 | `frontend/src/components/evidence/` |
| 7.5 | 文档管理页面：上传 + 列表 + 状态 | `frontend/src/app/documents/page.tsx` |
| 7.6 | Settings 页面：provider/model 切换 | `frontend/src/app/settings/page.tsx` |
| 7.7 | 全局状态管理（WebSocket 事件 → UI 状态） | `frontend/src/stores/` |

#### 验收标准

- 上传 PDF → 看到 ingestion 进度 → 完成
- 输入问题 → 看到流式回答 + evidence 面板实时更新
- 点击 citation → 跳转到来源 chunk（页码/表格定位）

---

### P8：OCR 可选通道（~1.5 天）

**目标：** text 检索不足时自动触发 OCR，补充证据并增量推送。

| # | 任务 | 产出文件 |
|---|---|---|
| 8.1 | OCR Service：接入 OCR 引擎（Tesseract 或云端），line 粒度 + bbox page_normalized | `backend/ocr/ocr_service.py` |
| 8.2 | OCR Chunker：line → chunk，写入 SQLite + Qdrant | `backend/ocr/chunker.py` |
| 8.3 | on_miss 触发集成：Kernel 判断 evidence 不足 → page_stats topN → 调 OCR → 增量更新 | 集成到 runner + kernel |
| 8.4 | 集成测试：构造 miss 场景 → OCR 触发 → evidence_update 推送 | `tests/integration/test_ocr.py` |

#### 验收标准

- OCR 默认关闭时：无 origin=ocr chunks
- on_miss 触发后：selected_units OCR chunks 入库 > 0
- 前端能看到 `chat.ocr_pages_selected` + `chat.evidence_update`

---

### P9：Eval + Evolve（~2.5 天）

**目标：** 离线可复现评估，进化门禁保障质量。

#### P9a：Eval（~1.5 天）

| # | 任务 | 产出文件 |
|---|---|---|
| 9.1 | Golden set 数据格式定义 + 5~10 条样例 | `eval/datasets/v1/` |
| 9.2 | Replay 机制：固定 retrieval 参数 + fixture/mock | `backend/eval_/replay.py` |
| 9.3 | L0 指标：schema 完整性 + 工具调用合法性 + citation 来源校验 | `backend/eval_/metrics.py` |
| 9.4 | L1 指标：断言式要点匹配 | 同上 |
| 9.5 | L2 指标：citation 覆盖与证据支撑 | 同上 |
| 9.6 | L3 指标：LLM judge（可选） | 同上 |
| 9.7 | EvalReport 输出（JSON + 失败用例列表） | `backend/eval_/report.py` |
| 9.8 | CLI 入口 | `scripts/replay_eval.py` |

#### P9b：Evolve（~1 天）

| # | 任务 | 产出文件 |
|---|---|---|
| 9.9 | Harvest：从 trace_store 聚类失败模式 | `backend/evolve/harvest.py` |
| 9.10 | Propose：生成候选改动（仅 evolvable 字段） | `backend/evolve/propose.py` |
| 9.11 | Validate：对候选跑 eval replay + 门禁判定 | `backend/evolve/validate.py` |
| 9.12 | Promote：通过门禁 → 发布新版本 + 写指纹 | `backend/evolve/promote.py` |
| 9.13 | CLI 入口 | `scripts/run_evolve_once.py` |

#### 验收标准

- `python scripts/replay_eval.py` 输出 EvalReport，L0/L1 pass rate 可计算
- 失败用例有足够 trace 信息定位问题阶段
- evolve promote 仅在 eval 通过后执行，且写入版本指纹

---

### P10：高级特性 —— 自主决策 & 多 Agent（远期）

**目标：** 提升 Agent 自主推理能力与复杂任务处理能力。

| # | 任务 | 产出文件 |
|---|---|---|
| 10.1 | Planner 实现（PAOR 循环，Kernel 内部阶段） | `backend/kernel/planner.py` |
| 10.2 | PlanSpec 数据结构 + Kernel 合规校验 | `backend/kernel/plan_spec.py` |
| 10.3 | Reflect 机制：evidence 充分性 + 工具结果校验 + 自纠错 | `backend/runners/reflect.py` |
| 10.4 | 歧义消解：clarify step + 追问策略 | 集成到 planner |
| 10.5 | Router 真实实现：复杂度评估 → single/multi 决策 | `backend/kernel/router.py` 升级 |
| 10.6 | Multi-profile runner：顺序/并行执行 + 结果合并 | `backend/runners/multi_runner.py` |
| 10.7 | Profile Registry + AgentProfile 数据结构 | `backend/registry/profile_registry.py` |
| 10.8 | Orchestrator（multi 模式任务分解 + 分发） | `backend/kernel/orchestrator.py` |
| 10.9 | 新增 WebSocket 事件集成（plan_generated / reflect_update / agent_spawned 等） | 集成到 api |

#### 验收标准

- 简单查询走 single profile 快速路径，无额外开销
- 复杂查询触发 PAOR 循环，trace 中可见 plan → act → observe → reflect 阶段
- multi 模式下多 profile 输出正确合并，冲突有标记

---

### RAG 后续扩展（教材：`backend/rag/demo/04_retrieval_augmented_generation/`）

> 不单独占版本里程碑编号；作为 **P3 完成之后** 的可选工作包。完整子任务、配置草案、验收与依赖见 [backend/rag/README_DESIGN.md](../backend/rag/README_DESIGN.md) **§6**（含 **6.1–6.6**）。

**与主路径依赖**

| 工作包 | 大致依赖 | 说明 |
|--------|----------|------|
| 6.2 模块化 / 协议 | P3 已完成即可；**结合 P6** 最顺 | Registry `rag_views` 与统一 `Recall` 签名 |
| 6.1.1 cross-encoder | P3 + 模型配置 | 与 `rag.rerank`、LLM adapter 共用密钥与 base_url |
| 6.1.2 MMR / 6.1.3 context assembly | P4 Kernel/Composer | 组装与 prompt 预算在 Runner 侧闭合 |
| 6.3 Agentic 多跳 | **P4 优先**；深化需 **P10** | 循环与停止策略必须走 Budget + trace |
| 6.4 图 RAG | P2 摄取扩展 + P1 schema 增量 | 实体/边落库或附表 |
| 6.5 垂直场景 | **P6** Profile/Skill | 配置覆盖，少改代码 |

**任务级 backlog（便于拆 issue）**

| ID | 主题 | 预估 | 主要产出（路径） | 测试（建议） |
|----|------|------|------------------|--------------|
| RAG-E1 | Recall 协议 + 指标钩子 | 0.5–1d | `backend/rag/protocols.py`，`service.py` 增量 | `test_rag.py` 打桩单通道 |
| RAG-E2 | Cross-encoder rerank | 1–2d | `reranker.py`，可选 `cross_encoder_rerank.py` | mock API + 顺序断言 |
| RAG-E3 | MMR / 去冗 | 0.5–1d | `dedup_redundant.py` 或 `merge.py` | Fixture 同页重复率 |
| RAG-E4 | Context assembler（composer 侧） | 0.5–1d | P4 `runners/composer.py`，可选 `rag/context_assembler.py` | 集成：token 上限 |
| RAG-E5 | Query rewrite / 多查询入口 | 1d | `rag/query_transform.py` | 纯函数单测 |
| RAG-E6 | 多跳编排（Kernel） | 2–3d | `kernel/*`，`rag/multi_hop.py` | `trace_event` 序列 + Budget |
| RAG-E7 | 图存储 + graph_recall | 3–5d | `rag/graph/*`，schema 迁移 | graph → chunk_id 可溯源 |
| RAG-E8 | 检索离线指标 | 1d | `eval_/retrieval_metrics.py` | P9 回放挂接 |

---

### 测试策略

#### 每阶段必须包含的测试

| 测试类型 | 覆盖范围 | 运行时机 |
|---|---|---|
| 单元测试 | 纯函数与局部依赖（tokenizer、evidence builder、merge 去重、citation 校验） | 每次提交 |
| 集成测试 | 端到端链路（ingestion → retrieval → chat，使用 mock model + 小样本） | 每个阶段完成时 |
| Eval 回放 | golden set replay（L0/L1 至少） | P9 完成后纳入 CI |

#### 关键测试文件

```text
tests/
  unit/
    test_storage.py           # P1
    test_models.py            # P1
    test_rag.py               # P3
    test_registry.py          # P6
    test_budget.py            # P4
  integration/
    test_ingestion.py         # P2
    test_chat_e2e.py          # P4
    test_ws_events.py         # P5
    test_ocr.py               # P8
```

---

### 风险与注意事项

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| Reranker 模型选型 | P3 检索质量 | MVP 先用 score 排序，后续接入 cross-encoder |
| OCR 引擎性能与成本 | P8 响应时间 | on_miss + topN 页限制 + 异步执行 |
| 多 Provider token 计数不一致 | 全链路 token 预算偏差 | TokenizerService 统一口径 + trace 记录 tokenizer_id |
| 前端 WebSocket 断连 | 用户体验 | REST 兜底端点 + 重连机制 |
| Evolve 误 promote | 线上质量退化 | eval 门禁强制 + 版本回滚开关 |

---

### 开发顺序图

```text
P0 脚手架 ──► P1 存储+模型 ──► P2 摄取 ──► P3 检索+证据
      │                                         │
      │                                         ▼
      │          P7 前端 ◄── P5 API ◄── P4 Kernel+Runners
      │                                         │
      │                                         ├──► P6 Registry
      │                                         │
      │                                         ▼
      └──────────────────────── P8 OCR ──► P9 Eval ──► P10 高级
```
