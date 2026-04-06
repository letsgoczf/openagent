## OpenAgent 脚本（Scripts）详细设计

### 1. 目标
- 提供可复现的 CLI 入口：文档导入、索引构建、评估回放、trace 回放、evolve 运行
- 便于在 CI/本地快速验证

### 2. 建议脚本清单（不要求一次实现全部）
- `scripts/ingest_local.py`
  - 输入：文档路径或目录
  - 输出：doc_id、version_id、job_id、ingestion trace
- `scripts/build_index_check.py`
  - 检查：FTS5 是否就绪、Qdrant collection 是否就绪
- `scripts/replay_eval.py`
  - 输入：dataset_version、candidate_version 指纹
  - 输出：EvalReport JSON/HTML
- `scripts/run_evolve_once.py`
  - 触发 evolve job（离线），输出 propose/validate/promote 结果
- `scripts/trace_export.py`
  - 输出某 run_id 的 trace_summary 与事件快照（供前端展示）

### 3. 验收标准
- 所有脚本都有明确输入输出（JSON）
- 脚本可使用同一份配置文件，保证 tokenizer/ocr 参数一致

