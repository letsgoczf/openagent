## backend/storage 详细设计（SQLite Schema + Qdrant payload 约束）

### 1. 目标
- 定义 SQLite 存储 schema：chunk_text、source_span、page_stats、token 缓存等
- 定义 Qdrant payload 约束：只存向量与必要元信息（不存 chunk_text 全文）
- 支持 citation 精确回溯到 chunk_id/version_id/source_span

### 2. SQLite 必备表（MVP 最小字段集合）
建议至少包含：
- `document`（doc_id, file_path, file_name, file_type）
- `document_version`（version_id, doc_id, content_hash, extraction_version, tokenizer_id, status）
- `chunk`：
  - `chunk_id`（绑定 version）
  - `version_id`
  - `origin_type`（text/table/ocr）
  - `chunk_index`
  - `chunk_text`（你要求：存 SQLite）
  - `source_span_json`
  - `evidence_entry_tokens_v1`
  - `evidence_snippet_text_v1`（截断文本缓存）
  - 方便检索冗余字段：`page_number/slide_number`, `table_id/image_id`
- `page_stats`（为 on_miss 选 topN 页服务）：
  - `version_id`
  - `unit_type`（pdf_page/ppt_slide）
  - `unit_number`
  - `effective_text_tokens`（仅统计 text+table，基于 evidence token 口径）
  - `has_text`
  - `table_count`（可选）
- `trace_event`（可选但建议，用于快速 trace 查询/回放）

### 3. SQLite FTS5（关键）
- 对 `chunk.chunk_text` 建索引（FTS5）
- 检索输出必须拿到 `chunk_id`
- keyword 召回使用 chunk_id 反查 chunk 与 source_span

### 4. Qdrant payload（关键约束）
Qdrant 中每个向量 item 的 payload 至少包含：
- `chunk_id`
- `version_id`
- `origin_type`
- `unit_type/unit_number`（page/slide）
- `table_id` 或 `image_id`（用于定位展示）

禁止将 chunk_text 全文放 payload。

### 5. citations 生成与校验（工程要求）
citations 生成链路：
1. evidence builder 选出的 chunk_id 列表
2. citations 按 chunk_id 从 SQLite 拉取 source_span/version_id
3. Kernel 校验 citations 对 evidence_entries 的 chunk_id 子集关系

### 6. 验收标准
- citations 永远能定位到 chunk_id/version_id/source_span
- on_miss 选页查询基于 page_stats 能在可接受时间内返回 topN
- keyword 检索返回 chunk_id 正确且可映射证据片段

