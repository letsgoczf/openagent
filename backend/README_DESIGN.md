## Backend 详细设计（FastAPI + Kernel + Agent 运行时 + 检索/证据）

> 本文为工程规格说明书：不包含具体代码实现，但给出实现步骤、关键接口契约、验收标准与技术路线。
> **定位**：后端围绕 **Agent 执行与编排** 组织；`backend/rag` 是检索与证据子系统，为 Agent 提供可溯源上下文，不是独立「RAG 产品」层。

### 0. 目录角色定义
- `backend/api`：FastAPI HTTP/WS 入口层（请求校验、事件推送、job 管理）
- `backend/kernel`：Run 生命周期、Blackboard 通信、Budget 控制、模式选择（single/multi 协作由复杂度决定）
- `backend/models`：LLM Adapter（OpenAI/Ollama/vLLM）+ TokenizerService（token 计数与口径一致性）
- `backend/registry`：Tool / Rag / Skills 注册表（只负责“注册与白名单”，不执行不受控逻辑）
- `backend/rag`：检索 pipeline（dense + keyword + merge + rerank + evidence builder）
- `backend/ingestion`：PDF/PPTX 抽取（text + table 为主）-> IR -> chunkization -> 写 SQLite/Qdrant
- `backend/ocr`：OCR 抽取（可选，成本优先 on_miss + topN 页 + line bbox page_normalized）
- `backend/runners`：聊天运行循环、工具调用循环、profile 执行器
- `backend/storage`：SQLite Schema + Qdrant payload 适配（chunk_text + citation 可溯源）
- `backend/eval_`：评估回放/指标计算（L0/L1/L2/L3）
- `backend/evolve`：离线进化 sidecar（harvest -> propose -> validate -> promote）

### 1. 后端总体数据流（在线）
1. `WS chat.start` 创建 `run_id` 与 `RunContext`
2. Kernel 选择 mode/profile（单/多由 router + budget + 失败历史决定）
3. Runners 调用 Retrieval Service：
   - Qdrant dense recall -> SQLite FTS keyword recall -> merge 去重
   - reranker 重排 -> evidence builder 组装 EvidenceEntry v1（截断 + token 缓存）
4. 若触发 OCR（on_miss）：
   - 从 `page_stats` 选 topN 页面（token 密度，已用生成 tokenizer 口径计算）
   - OCR line chunks 入库 SQLite + 索引
   - evidence builder 增量更新并通过 WebSocket 推送 `chat.evidence_update`
5. Writers/Generator 调模型输出最终回答
6. citations 来自 `chunk_id -> source_span + version_id`，写入 trace 并以 `chat.completed` 推送

### 2. 后端总体数据流（离线 ingestion）
1. 上传文档 `POST /v1/documents/import` -> job_id
2. DocumentVersioning：
   - 计算 `version_id`（content_hash）与 `extraction_version`
3. 抽取（主）：
   - PDF：text（page_number）+ table（table_id + row/col range + 可检索 cell_text）
   - PPTX：文本框（slide_number + heading_path/shape_index）+ table shape（row/col range）
4. IR -> chunkization：
   - `origin=text`：chunk_text 入 SQLite
   - `origin=table`：table 文本化后 chunk_text 入 SQLite
   - 每个 chunk 写 `source_span`（至少 page_number/slide_number + table_ref）
5. 索引构建：
   - Qdrant：chunk 向量 + payload（chunk_id/version_id/origin/page/table/image 标识）
   - SQLite FTS5：chunk_text 全量索引（可检索、可溯源）
6. page_stats 计算（偏查询性能）：
   - 只统计 text+table 的 effective_text_tokens（不含 OCR）
   - 写入 `page_stats` 单独表，支持 `ORDER BY ... LIMIT N`

### 3. API 与接口契约（实现要求）
#### 3.1 WebSocket 端点
- 单连接入口：`GET /ws`
- 事件需带：`event/client_request_id/run_id/sequence`

#### 3.2 FastAPI REST 端点（关键）
- `POST /v1/chat`（可选：若仅 WS，则此处用于任务启动）
- `POST /v1/chat` or `WS chat.start`：创建 run
- `POST /v1/documents/import`：创建 ingestion job
- `GET /v1/jobs/{job_id}`：兜底轮询（VS WS 断连时恢复）
- `POST /v1/eval/replay`：离线回放
- `GET /v1/traces/{run_id}`：调试/trace 拉取（兜底）

### 4. Kernel 详细实现步骤（单用户）
#### 4.1 RunContext 与 Budget
- RunContext 必含：
  - `run_id/session_id`
  - `budget`：`max_llm_calls/max_tool_rounds/max_evidence_entries/token_budget/wall_clock_ms`
  - 当前状态：active profiles、retrieval stats、ocr status、tool trace
- Budget 强制下限/上限由配置决定，禁止模型绕过。

#### 4.2 Blackboard 通信
- Blackboard 采用 append-only 事件流（事件序列化进 trace_store）
- 事件命名空间约束：
  - Kernel 事件：`blackboard.kernel.*`
  - evidence 事件：`blackboard.evidence.*`
  - tool 事件：`blackboard.tool.*`

#### 4.3 模式选择（单/多 profile）
- Router 输出结构化决策：
  - `mode=single|multi`
  - `profiles`（按复杂度/预算选择）
  - `max_rounds`（硬限制）
- Kernel 校验：
  - profiles 与工具 allowlist 必须匹配注册表
  - 若超预算：自动降级为 single 或减少并行数

### 5. Model Service 详细实现步骤
#### 5.1 LLM Adapter
- 三类 provider：OpenAI / Ollama / vLLM
- 统一接口：
  - `chat(messages, gen_params, tools?) -> assistant_message (+ optional tool_calls)`
- 流式输出：
  - FastAPI WS 的 `chat.delta` 由适配层产生增量文本

#### 5.2 TokenizerService（必须可配置）
- 用户配置 `tokenization.tokenizer_model_id`（优先）或自动推导
- 提供：
  - `count_tokens(text)`（用于 evidence token 缓存与 OCR 触发阈值）
  - `count_evidence_entry_tokens_v1(chunk_id/version_id/origin)`（基于模板 v1 和截断文本）
- token 口径必须版本化：
  - `tokenizer_id`、`tokenizer_version`（至少写入 trace）

### 6. Registry 详细实现步骤（安全关键）
#### 6.1 Tool Registry
- 每个 tool 必有 JSON Schema 参数定义
- 执行必须走 Tool Gateway：
  - schema 校验、超时控制、参数脱敏预览

#### 6.2 Skills Registry（受控能力注入）
- Skill manifest 字段（最小）：
  - `id/version`
  - `trigger`（触发条件，至少描述）
  - `prompt_addon`（仅作为 prompt 片段）
  - `retrieval_hints`（可选）
  - `tools_allowlist`（受控白名单）
- Kernel 在运行时：
  - 匹配 skills -> 注入 prompt_addon -> 收紧工具白名单

### 7. RAG 与 Evidence builder 详细实现步骤
#### 7.1 候选检索
- dense：Qdrant `top_k_dense=50`（起步可调）
- keyword：SQLite FTS5 `top_k_kw=20~35`
- merge：去重（按 chunk_id）与 score 归一化（实现时选一个可复现方法）
- 候选上限：`max_candidates=100~120`

#### 7.2 reranker 重排
- reranker 输入：query + chunk_text（必要时 table/text 优先）
- rerank 输出：top_n evidence 进入 evidence builder

#### 7.3 EvidenceEntry v1（截断 + token 缓存）
- Evidence entry 模板 v1 固定
- chunk_text 进 SQLite，但 evidence entry 内放 `evidence_snippet_text_v1`（截断版本）
- 对每个 chunk 预计算并缓存：
  - `evidence_entry_tokens_v1`
  - `evidence_snippet_text_v1`

#### 7.4 citations 生成规则
- citations 必来自：
  - chunk_id -> source_span + version_id -> location 字段
- citations 中不得出现未入库的 chunk_id

### 8. Ingestion 与 OCR 详细实现步骤
#### 8.1 text/table 抽取（必做）
- PDF：
  - 优先文本层（page_number）
  - 表格：table_ref + 行列范围 + cell_text
- PPTX：
  - 文本：shape/text elements（slide_number + heading_path 可选）
  - 表格：table shape -> row/col range -> cell_text

#### 8.2 chunkization（必做）
- 对 IR 分 origin 创建 chunk
- chunk_text 写入 SQLite
- source_span 写入 JSON（text/table 至少需要 page/slide 与定位字段）

#### 8.3 page_stats 计算（偏查询性能）
- `page_stats`：用于 OCR on_miss 的“选 top N 页面”
- effective_text_tokens 只统计 text+table 的证据入口 token/或 chunk 文本 token（以你选的 evidence token 缓存为准）

#### 8.4 OCR（可选，成本优先 on_miss）
- trigger：
  - on_miss（text/table 检索 miss 或证据质量低）
- pages selection：
  - 从 `page_stats` 取 effective_text_tokens topN（max_ocr_pages 默认 5~8）
- OCR 输出：
  - line 粒度 chunks，origin=ocr
  - bbox 存储坐标系 `page_normalized`
- OCR chunk 的 evidence 默认降权，避免噪声挤掉 text/table 证据

### 9. Storage（SQLite + Qdrant）实现要求
#### 9.1 SQLite
- chunk_text 全量存入 SQLite，支持 evidence 可溯源展示
- FTS5 索引：对 chunk_text 建索引
- page_stats 单独表，支持 LIMIT 查询

#### 9.2 Qdrant
- 只存向量与 payload：
  - payload 含 chunk_id/version_id/origin/page/table_id/image_id
- 禁止在 payload 中放 chunk_text 全文（控制大小）

### 10. Eval 与 Evolution（实现门禁）
#### 10.1 eval_
- golden set replay：
  - replay 使用固定数据集、固定模型 provider、固定 prompt/addon/router 指纹
- L0/L1/L2/L3：
  - L0：schema/格式/工具调用正确性
  - L1：断言式要点匹配
  - L2：citation 覆盖与证据支撑
  - L3：LLM judge（可选、必须对冲）

#### 10.2 evolve
- evolve 允许改：
  - constitution 的 evolvable 段、skills、retrieval query_templates、router policy
- evolve 不允许改：
  - 工具白名单的边界、预算上限、关键安全策略
- promote gate：
  - eval report 达标后才发布，并写入版本指纹

