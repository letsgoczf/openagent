## backend/kernel 详细设计（受控运行时：RunContext + Blackboard + Budget）

### 1. 目标
- 管理一次 chat/run 的生命周期与受控执行
- 作为“执行裁决者”：预算、模式选择、工具 allowlist 强制执行
- 通过 Blackboard 让 profile/协作组件共享结构化状态

### 2. 核心概念与状态机
必需对象：
- `RunContext`：run_id/session_id/budget/token_budget/当前证据状态
- `Blackboard`：append-only 事件流 + 当前快照视图
- `Budget`：max_llm_calls、max_tool_rounds、max_evidence_entries、wall_clock
- `Trace`：结构化日志写出（供 eval/前端 trace 展示）

运行时状态（建议）：
- `initialized -> planned -> retrieving -> (ocr_on_miss) -> generating -> (tool loop)* -> completed/failed`

### 3. 实现步骤
1. Run 初始化：
   - 读取配置：provider/model/tokenizer/evidence模板/ocr触发策略
   - 创建 RunContext 与初始 Blackboard
2. Router/Mode 选择（single/multi）：
   - 输出结构化决策：mode、profiles、max_rounds、工具使用预算
   - Kernel 校验：profiles 与工具 allowlist 必须来自 registry
3. Retrieval 触发与证据构建：
   - 调用 rag service 获取 evidence（并发与轮次受 budget 控制）
   - 依据 evidence质量与 on_miss 策略触发 OCR 页选择
4. OCR（可选）：
   - 选 topN 页面 -> 触发 ocr service -> 将 ocr chunks 写入 SQLite/Qdrant
   - 证据更新增量推送（WS：chat.evidence_update）
5. Generation：
   - composer 组装系统提示（constitution + profile addons + skills）
   - evidence_block 按 EvidenceEntry v1 + 截断策略拼接
6. Tool loop（可选）：
   - 模型如触发 tool call：先过 Tool Gateway 校验，成功后把结构化结果写入 blackboard
   - tool loop 次数受 max_tool_rounds 控制
7. Post-validate：
   - citations 最终校验：必须来自 chunk_id/version_id/source_span
8. 完成：
   - 写 trace 并推送 `chat.completed`，失败推 `chat.failed`

### 4. 受控边界（安全关键）
- 禁止模型越权扩大工具白名单或预算
- 工具调用参数必须 schema 校验
- 黑板写入采用命名空间，避免冲突覆盖

### 5. 验收标准
- 在预算不足、retrieval miss、tool failure、OCR enabled/disabled 下均能正确失败或降级
- 前端 trace 能复现关键事件序列（retrieval_update/evidence_update/ocr_pages_selected）

