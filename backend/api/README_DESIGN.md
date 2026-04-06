## backend/api 详细设计（FastAPI HTTP + WebSocket）

### 1. 目标
- 提供对外 API：聊天、文档导入、作业查询、trace 查询、eval replay
- 提供 WebSocket：chat.run 与实时事件推送
- 负责请求校验、响应结构化与错误码统一

### 2. 实现步骤（按顺序）
1. 定义 Pydantic 请求/响应模型（REST 与 WS 均使用同一套字段命名策略）
2. 实现 WS 连接管理：
   - 连接建立时创建 client state（保存 subscriptions）
   - 处理客户端消息（chat.start 等）并转发给 Kernel/Job 机制
3. 实现 WS 事件推送：
   - 每次事件带 `run_id/job_id + client_request_id + sequence`
   - 对乱序到达进行顺序维护（后端至少保证 sequence 单调）
4. 实现 REST endpoints（可作为 WS 的兜底）：
   - documents import
   - jobs status
   - traces get
   - eval replay（异步任务）
5. 错误处理：
   - tool 失败/模型失败/抽取失败分别映射成统一错误结构
   - WebSocket 上推 `chat.failed` 或 `job.failed` 并带用户友好信息

### 3. 关键契约（与前端/Kernel 对齐）
- chat 事件包含：`chat.delta`、`chat.evidence_update`、`chat.completed` 等关键事件
- jobs 事件包含：`job.progress`、`job.completed`、`job.failed`

### 4. 验收标准
- WebSocket 在网络抖动下可恢复（前端可通过 GET traces/jobs 拉回最终状态）
- citations 在 chat.completed 可完整展示并能回溯 chunk_id/version_id/source_span

