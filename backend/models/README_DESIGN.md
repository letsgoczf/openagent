## backend/models 详细设计（LLM Adapter + TokenizerService）

### 1. 目标
- 统一对外 LLM 调用接口，支持 OpenAI / Ollama / vLLM
- 提供可配置 tokenizer，用于 evidence token 预算估算、OCR on_miss 触发阈值

### 2. 实现模块
- LLM Adapter（provider-specific client）
- TokenizerService（provider-agnostic 接口）

### 3. 实现步骤
1. 定义统一 LLM Adapter 接口：
   - `chat(messages, gen_params, tools=None, stream=False) -> assistant_text 或 stream`
   - 工具调用返回结构化 tool_calls（由 Tool loop 消费）
2. OpenAI Adapter：
   - 映射 messages 到 provider 格式
   - 实现 streaming -> 由 WS 层转为 `chat.delta`
3. Ollama Adapter：
   - base_url 配置化
   - 封装 provider 的 chat API 差异（只在 adapter 内处理）
4. vLLM Adapter：
   - 兼容 v1-style endpoint（基于 base_url）
5. TokenizerService：
   - provider auto 推导 tokenizer 或使用配置覆盖 `tokenization.tokenizer_model_id`
   - 实现：
     - `count_tokens(text) -> int`
     - `count_evidence_entry_tokens_v1(chunk_text_snippet) -> int`
   - 缓存 tokenizer 实例，避免重复加载

### 4. 关键口径（必须一致）
- OCR 触发与 evidence entry token 计算必须使用同一个 tokenizer 口径与证据模板版本
- tokenizer_id/tokenizer_version 必须写入 trace

### 5. 验收标准
- evidence token 计数与实际发送给模型的证据条目一致（偏差可接受但必须可复现）
- 选择 provider/model_id 切换后，不会影响证据引用与 citations 生成

