## backend/runners 详细设计（聊天运行循环 + 工具调用循环 + profile 执行器）

### 1. 目标
- 实现“在线执行链路”的工程承载：
  - chat.run 循环（select retrieval -> compose -> generate -> tool loop -> finalize）
  - 工具调用循环（模型请求 tool -> Tool Gateway -> 写 blackboard -> 返回模型上下文）
  - profile 执行器（Planner/Researcher/Writer 等角色或单 profile 的等价实现）
- 与 Kernel 保持边界：runners 负责执行编排，kernel 负责裁决与预算/安全

### 2. 运行循环（Chat Runner）
输入：
- `run_context`（budget/flags/tokenizer/evidence config）
- `session_id/run_id`
输出：
- 通过 Kernel 写 trace 并触发 WebSocket 事件推送

#### 2.1 单 profile MVP（推荐先实现）
顺序（在 runner 内部）：
1. planner_stub：根据 constitution/profile 生成本轮需要的检索参数（或直接调用 router）
2. retrieval：调用 rag service 获取 evidence_entries
3. evidence compose：
   - evidence_entry template v1 + 截断 snippet
   - evidence entries 按 rerank 顺序拼装
4. generate：
   - 调用 Model Adapter
   - 流式将 `chat.delta` 推送给前端
5. finalize：
   - 从证据候选生成 citations
   - 写入 trace 并触发 `chat.completed`

#### 2.2 多 profile / 多轮协作（后续扩展）
- 由 router 决策 `mode=multi`
- runner 按 profiles 列表依次执行（或并行但需证据合并策略）
- 所有 profile 的输出写入 blackboard evidence/question 列表

### 3. 工具调用循环（Tool Loop）
当 Model Adapter 返回 tool_calls：
1. tool_call_started：推送 WS 事件（脱敏参数预览）
2. Tool Gateway 校验：
   - 参数 schema 校验
   - 超时控制
   - 输出脱敏（result_preview）
3. tool_call_finished / failed：
   - 写入 blackboard/tool_trace
4. 将 tool 结果以结构化方式回传给下一次 generate（受预算限制）
5. tool loop 最多执行 max_tool_rounds 次

### 4. WebSocket 事件对齐（关键）
runner 必须通过 Kernel 统一写 trace，同时在关键时刻推送以下事件：
- `chat.delta`（生成流式）
- `chat.retrieval_update`
- `chat.ocr_pages_selected`（若触发）
- `chat.evidence_update`（增量展示）
- tool_call_started/finished/failed
- `chat.completed`

### 5. 验收标准（最小）
- 在模型 provider 切换（OpenAI/Ollama/vLLM）后，tool loop 与 evidence builder 行为一致
- chat.delta 流式输出按顺序到达且可拼接为最终 assistant_message
- citations 均来自 evidence_entries 内的 chunk_id 且带 version_id/source_span

