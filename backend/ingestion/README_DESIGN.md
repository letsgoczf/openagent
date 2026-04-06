## backend/ingestion 详细设计（PDF/PPTX -> IR -> chunkization -> SQLite/Qdrant）

### 1. 目标
- 支持 PDF + PPTX 文档导入
- 先做 text + table（主证据通道）
- chunk_text 全量落到 SQLite
- 同步构建 Qdrant dense 向量索引与 SQLite FTS5 keyword 索引
- 维护 `page_stats`（为 OCR on_miss 页选择服务，偏查询性能）

### 2. 输入/输出契约
输入：
- `document_file`
- `doc_metadata`（可选：类别标签等）

输出：
- `doc_id` 与 `version_id`
- `ingestion_job_status`
- `trace` 指针（前端可拉取 ingestion 进度）

### 3. 核心数据流（离线）
1. DocumentVersioning
   - 计算 document content hash -> `version_id`
   - 记录 `extraction_version`（抽取器版本）、`ingestion_at`
2. 抽取 Text + Table（先主通道）
   - PDF：
     - text：按页 page_number 抽取可用文本块
     - table：抽取表格结构 -> table_ref（row/col range + cell_text 可检索文本）
   - PPTX：
     - text：按 slide_number 抽取文本框与 heading_path（可选）
     - table：解析 table shape -> table_ref（row/col range + cell_text）
3. IR -> chunkization
   - origin=text：生成 chunk_text 写 SQLite
   - origin=table：生成可检索 table 文本化 chunk_text 写 SQLite
   - 每个 chunk 写入 `source_span`（至少 page_number/slide_number + table_ref）
4. 索引构建
   - Qdrant：向量+payload（chunk_id/version_id/origin/page/table 等）
   - SQLite FTS5：对 chunk_text 建索引
5. page_stats 计算（偏查询性能）
   - 统计每页/每 slide：`effective_text_tokens`（只统计 text+table 的证据入口）
   - 写入 `page_stats` 表供 `on_miss` 时 topN 页选择

### 4. 性能与实现要求（查询性能优先）
- chunkization 产物先写 SQLite 再构建索引，确保可回放
- `page_stats` 单独表存储，支持快速 `ORDER BY ... LIMIT N`
- page_stats 统计使用“生成 tokenizer 口径”+ evidence token 缓存口径（保证阈值与模型发送一致）

### 5. OCR 适配（接口预留）
- ingestion 允许记录 OCR 可选通道所需的中间元信息：
  - 每页/每 slide 的渲染参数（与 OCR raster 对齐）
  - image_ref 的可识别标识（供 OCR 强溯源）
- OCR 默认不跑；但在 `ocr.enabled=true` 时 ingestion/runner 应可触发 OCR service。

### 6. 验收标准（MVP）
- 导入后能生成至少 text/table chunks，且能被检索检出
- `page_stats` 存在并能支持 topN 页面选择 SQL
- chunk_text 完整存入 SQLite，citation 能回溯 source_span

