## OpenAgent docs 写作与组织规范

### 1. 目标
- 保证架构、数据模型、接口契约、抽取与检索策略、评估与进化门禁均可快速定位
- 避免散落在代码注释中的关键信息

### 2. 建议的 docs 文件列表（按优先级）
- `architecture.md`：顶层架构总览（可引用 OPENAGENT_ARCHITECTURE.md）
- `api_contracts.md`：FastAPI REST/WS 事件与字段定义
- `data_model.md`：SQLite/Qdrant schema、chunk/source_span/page_stats/evidence tokens
- `ingestion_spec.md`：PDF/PPTX text+table 抽取、chunkization、page_stats
- `retrieval_spec.md`：dense+keyword 召回、merge、rerank、evidence builder、citations
- `evidence_spec.md`：EvidenceEntry v1、截断策略、token 缓存口径
- `evaluation_spec.md`：黄金集格式、L0~L3 指标与阈值
- `evolution_spec.md`：harvest->propose->validate->promote、promote gate
- `config_spec.md`：provider/tokenizer/ocr 关键字段（可引用 config/README_DESIGN）

### 3. 文档模板建议
- 每个文档默认包含：
  - Scope / Non-goals
  - 输入/输出
  - 关键字段/结构体（JSON、表 schema）
  - 实现步骤（可按模块拆）
  - 验收标准（测试点）

