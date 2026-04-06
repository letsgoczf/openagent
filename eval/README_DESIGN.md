## OpenAgent Eval（离线评估）详细设计

> 位于仓库根目录 `openagent/eval/`：放数据集与 fixture。实现代码在 `openagent/backend/eval_/`。

### 1. 目标
- 构建可回放的 golden set：保证 prompt/skill/router/evidence pipeline 改动可比较
- 输出 EvalReport：用于 evolve job 的 promote gate

### 2. 数据集目录约定
- `openagent/eval/datasets/v1/`：版本化数据集（YAML/JSON）
- `openagent/eval/fixtures/`：本地 mock 工具返回与假 RAG 片段

### 3. golden set 用例结构（建议最小字段）
- `case_id`（稳定）
- `dataset_version`
- `input`：
  - `user_message`
  - 可选：session 前缀/历史（若需要多轮）
- `constraints`：
  - 是否必须 citation
  - 预期输出结构 schema（如需要）
- `assertions`（L0/L1）：
  - JSON 字段断言
  - 正则/要点匹配
- `expected_evidence`（L2）：
  - 应命中的 doc_id/chunk_id 或至少 page_number 范围

### 4. 评估执行（对应 backend/eval_）
- Replay：固定模型 provider、固定 generation 参数（温度等）
- 固定 retrieval 参数：top_k、rerank、OCR 开关（按 case 配置）
- 输出 EvalReport：
  - L0/L1/L2/L3 各自 pass 率
  - 失败 case 列表（case_id、失败原因、trace 指针）

### 5. 验收标准
- 数据集必须可在本地无外部依赖复现（fixture 提供 mock）
- 失败报告足够定位：能回到 trace 的哪一步（retrieval/evidence/tool/OCR）
- promote gate 使用同一套阈值配置

