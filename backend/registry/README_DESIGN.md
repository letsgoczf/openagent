## backend/registry 详细设计（Tool / Rag / Skills 注册表）

### 1. 目标
- 集中管理“可用能力与约束”：工具（tools）、RAG 资源（collections/索引策略）、Skill（受控能力片段）
- 只做注册与白名单，不执行任何不受控业务逻辑
- 为 Kernel 提供可校验的安全边界：模型只能在注册表允许的范围内工作

### 2. 模块职责边界
- 必须依赖配置（`openagent/config/openagent.yaml`）：
  - tool allowlist（全局/按 profile）
  - rag collections（与文档类别/提取类型关联）
  - skills（内置 + 可扩展的 manifest）
- 不允许：
  - 模型动态新增工具名或 collection 名
  - Skill 通过 prompt 注入扩张权限

### 3. 数据结构与契约（实现要求）
#### 3.1 Tool Registry（必须）
对每个 tool 定义：
- `tool_name`
- `json_schema`（参数 schema）
- `return_schema`（返回结构/字段）
- `timeout_ms`
- `allowed_profiles` 或 `allowed_skills`
- `sensitivity_level`（用于脱敏预览）
- `handler_ref`（内部实现引用，前端不关心）

Tool 执行时只允许调用 registry 中存在的 tool_name，并对参数做 schema 校验。

#### 3.2 Rag Registry（必须）
对每个 rag view 定义：
- `collection_id`（映射到 Qdrant collection）
- `version_scope`（默认 latest_active）
- `filters`（metadata 过滤策略，例如按文档类别/标签/源）
- `top_k_defaults`（dense/keyword 默认参数）

检索服务在运行时只能使用 registry 暴露的 rag views。

#### 3.3 Skills Registry（必须）
Skill manifest 最小字段：
- `skill_id`
- `version`
- `description`
- `trigger`（keywords/intent_labels 或简单 match_rules）
- `prompt_addon`（system 片段/人格/格式约束）
- `retrieval_hints`（可选：query 改写、检索权重建议）
- `tools_allowlist`（强制：本 Skill 允许的工具集合）
- `max_addon_tokens`（可选：控制 prompt 注入成本）

Skills 注入策略：
- Skill 只注入 prompt_addon + retrieval_hints + tools_allowlist 子集
- 工具执行仍走 Tool Gateway 的 schema 校验

### 4. 实现步骤（按顺序）
1. 解析配置并加载工具注册表（从代码内置或配置）
2. 扫描 `openagent/skills/manifests/` 并加载 Skill manifest
3. 为每个 Skill 做静态校验（字段完整性、tools_allowlist 是否存在于 Tool Registry）
4. 暴露给 Kernel 的统一接口：
   - `get_tools(profile_or_skill_id) -> ToolDefinition[]`
   - `get_rag_view(view_id) -> RagViewDefinition`
   - `match_skills(user_message, blackboard_summary) -> SkillMatch[]`

### 5. 安全与验收标准
- 验收 1：模型尝试调用未注册 tool_name 必须拒绝并写入 trace（tool_call_failed）
- 验收 2：Skill 的 tools_allowlist 之外的工具调用必须失败
- 验收 3：RAG 只能访问 registry 暴露的 collection_id，不能由模型自由选择

