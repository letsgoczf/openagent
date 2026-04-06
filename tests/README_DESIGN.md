## OpenAgent 测试详细设计（单元 + 集成）

### 1. 目标
- 保证每个关键模块可回归：抽取、chunkization、检索、evidence 组装、citation 输出、token 预算估算
- 保证评估 harness 可在 CI 中运行（至少跑 L0/L1）

### 2. 目录含义
- `openagent/tests/unit/`：纯函数/局部依赖的单元测试
- `openagent/tests/integration/`：端到端链路测试（使用 mock tools 和小样本数据）

### 3. 单元测试重点（建议）
- `TokenizerService`：
  - count_tokens 与 evidence_entry_tokens_v1 缓存一致
- `Evidence Builder`：
  - EvidenceEntry v1 模板字段固定
  - 截断策略生效且 token 缓存可复现
- `Retrieval Merge 去重`：
  - 相同 chunk_id 去重逻辑
  - origin 权重/降权逻辑
- `citation 生成`：
  - citations 必来自 chunk_id 且附带 version_id/source_span

### 4. 集成测试重点（建议）
- ingestion（text+table）：
  - PDF/PPTX 小样本导入后能产生 chunk 与 page_stats
- retrieval+chat：
  - 给固定问题，应返回非空 assistant_message 与至少 1 条 citations
- OCR 开关：
  - OCR 默认关闭：不生成 origin=ocr chunks
  - OCR on_miss：在构造 miss 场景下生成 ocr chunks 并触发 evidence_update
- WebSocket：
  - chat.delta 流式增量到达顺序正确
  - evidence_update 增量能在前端状态合并（可用前端测试或后端事件快照）

### 5. 验收标准
- 单测与集成测可在本机稳定通过（依赖最小化）
- 集成测试使用 fixture/mock，不依赖真实外部网络（模型 provider 可 mock）

