## backend/ocr 详细设计（成本优先 on_miss + 强溯源 bbox line 粒度）

### 1. 目标
- 为 PDF/PPTX 提供可选 OCR 通道
- 在成本优先策略下：OCR 默认不主动全量跑，仅在 on_miss 触发后跑
- OCR 输出必须强溯源（强要求：`page_normalized` bbox + line 粒度）
- OCR chunk_text 仍存入 SQLite，并可参与证据组装与 citations

### 2. 触发条件（由 Kernel/Retrieval 决策）
OCR service 只实现“执行抽取”，不负责触发策略。
输入由 Kernel 给定：
- `version_id`、`unit_type`（pdf_page 或 ppt_slide）
- `selected_units`（topN 页面列表）
- `ocr_mode`（page_full/slide_full）
- `chunking`（line）
- `min_confidence`（低置信行丢弃或降权）

### 3. OCR 抽取输出契约（IR 级）
输出为 OCR 行级块（建议命名）：
- 每行包含：
  - `page_number/slide_number`
  - `image_ref_id`（整页渲染得到的 raster/图片标识）
  - `line_index`
  - `text`
  - `confidence`（可选）
  - `bbox`（page_normalized 坐标系）

### 4. bbox 强溯源要求
- coord_space 固定为：`page_normalized`
- bbox 格式：`[x1, y1, x2, y2]`（0~1 归一化）
- 必须与 OCR 渲染栅格的页面宽高一致换算并写入 trace

### 5. chunkization 与写入 SQLite
- 对每个 OCR line 生成一个 chunk：
  - `origin_type=ocr`
  - `chunk_text` 存 SQLite
  - `source_span` 写入 JSON（image_ref_id + bbox + page/slide）
- 同步更新 Qdrant payload（payload 不含 chunk_text 全文）

### 6. 验收标准
- OCR 默认关闭时：不会生成 origin=ocr chunks
- OCR on_miss 时：
  - selected_units 的 OCR 行 chunks 入库数量 > 0
  - citations 能引用 origin=ocr chunk 的 source_span（bbox 可用）

