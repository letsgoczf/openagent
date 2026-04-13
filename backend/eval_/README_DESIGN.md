## backend/eval_ 详细设计（Eval Harness：回放 + L0~L3 指标）

### 1. 目标
- 对 OpenAgent 的关键链路进行离线、可复现评估
- 为 evolve/promote 门禁提供可计算的 EvalReport

### 2. 输入/输出
输入：
- golden set：`openagent/eval/datasets/v1/`（case 列表）
- candidate_version 指纹：包含 constitution/profile/router/skill 与模型 provider/model_id
- run_config：如 retrieval 参数与 OCR 开关（按 case 覆盖）

输出：
- `EvalReport`：
  - 总体指标与分层指标（L0~L3 pass rate）
  - 失败用例列表（case_id、失败阶段、失败原因、trace 指针）
- 记忆子系统 trace 聚合（可选）：`backend/memory/eval_report.summarize_memory_trace_events`，从 `trace_event` 解析 `(event_type, payload)` 列表即可并入报表附录。

### 3. L0~L3 指标（必须实现）
- L0：程序判定
  - 输出 schema/字段完整性
  - 工具调用是否 schema 合法（在 fixture/mock 下）
  - citations 必须来自已检索证据集合
- L1：参考输出比对
  - assertions（正则/要点匹配）
- L2：事实性/可溯源
  - evidence/citation 覆盖：关键 claim 是否有证据支撑
- L3：LLM judge（可选但推荐）
  - 要有对冲/黄金标定

### 4. Replay 机制（工程要求）
- Replay 需要固定：
  - retrieval 参数：top_k、rerank_top_n、ocr enabled 等
  - evidence_entry_template_version 与截断策略
  - tokenization tokenizer_id
- Replay 使用 fixture/mock：
  - 如果不允许外网/真实 tool，应使用 fixture 替代

### 5. 验收标准
- EvalReport 必须可复现
- 失败用例必须给出足够 trace 信息定位：retrieval/evidence/tool/OCR 哪一步导致失败

