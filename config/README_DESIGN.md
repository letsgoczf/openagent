## OpenAgent 配置体系详细设计（单用户）

### 1. 目标
- 让用户以配置文件选择模型 provider（OpenAI / Ollama / vLLM）
- 让用户可选覆盖 tokenizer，用于 token 计数（OCR on_miss 触发、evidence token 预算）
- 让用户控制 OCR（默认成本优先：`on_miss` + `max_ocr_pages`）
- 让用户控制 evidence entry 模板版本（保证 token 口径一致）
- 让后端可以“复现”：任何一次 run 记录关键配置指纹（写入 trace）

### 2. 配置文件落点
- 推荐：`openagent/config/openagent.yaml`（用户可复制并编辑）
- 后端启动时：
  - 默认读取仓库提供的模板（或 `.env` 补齐密钥）
  - 支持通过 CLI/env 覆盖配置路径

### 3. 配置结构（建议字段）
#### 3.1 模型与 provider
- `models.generation.provider`: `openai | ollama | vllm`
- `models.generation.model_id`: provider 内模型名
- provider 专用：
  - openai：`api_key_env`
  - ollama：`base_url`
  - vllm：`base_url`

#### 3.2 tokenizer（用于 token 计数口径一致性）
- `tokenization.provider`: `auto | tiktoken | hf`
- `tokenization.tokenizer_model_id`：可选覆盖
  - 若为 null，则优先使用 `models.generation.model_id` 推导
- `tokenization.count_scope`: 当前你选择的口径通过 evidence-entry 缓存实现
  - 推荐固定为：`full_messages_by_template_cache`（文档解释即可，不要做成复杂可选项）

#### 3.3 OCR（成本优先、强溯源预留）
- `ocr.enabled`: 默认 `false`
- `ocr.trigger.mode`: `on_miss`（严格兜底，默认不主动跑）
- `ocr.max_ocr_pages`: 5~8（成本优先）
- `ocr.min_confidence`: OCR 行低于阈值丢弃或降权
- `ocr.chunking`: `line`（你已选）
- `ocr.coord_space`: 固定 `page_normalized`（禁止用户随意改，降低返工）

#### 3.4 Evidence entry（token 口径关键）
- `evidence.entry_template_version`: 固定 `v1`
- `evidence.max_evidence_entry_tokens`: 200~400（你已选“截断策略 2”）
- `evidence.snippet_truncation_version`: 固定（便于升级）

### 4. 配置指纹与复现要求
每次 run 或 ingestion job 必须记录以下指纹信息：
- `constitution_version`（宪法版本哈希）
- `profiles_set_hash`（实际启用的 profile 集合）
- `router_policy_id`（路由策略标识）
- `generation_provider + model_id`
- `tokenizer_id + tokenizer_version`
- `evidence.entry_template_version + evidence truncation version`
- `ocr.enabled + ocr trigger params`

指纹写入 `trace` 并可在回放/评估时复用。

### 5. 验收标准
- 用户只需要改一个 YAML 就能切 provider + 调 tokenizer + 开启/关闭 OCR
- 任意一次 run 都能通过 trace 指纹复现证据与 token 预算行为
- OCR 坐标系强制为 `page_normalized`

