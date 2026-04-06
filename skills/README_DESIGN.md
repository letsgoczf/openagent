## OpenAgent Skill 详细设计（受控能力注入）

### 1. 目标
- 让用户定义“自定义 Skill”，用于让模型在特定任务上更像专家
- Skill 受控：不允许扩展工具白名单或突破安全边界
- Skill 可被版本化：以 manifest/version 标识并可追溯到 trace

### 2. Skill manifest 目录
- `openagent/skills/manifests/`：放置内置 skill 的 manifest
- 用户可通过额外路径挂载自己的 manifest（后续支持）

### 3. manifest 最小字段（建议）
- `id`：全局唯一
- `version`：semver 或整数递增
- `description`：给管理员/用户理解用
- `trigger`：
  - `keywords`（可选）
  - `intent_labels`（可选）
  - 或 `match_rules`（可选：简单规则）
- `prompt_addon`：
  - 仅作为 system/persona 附加片段注入（由框架控制插入位置）
- `retrieval_hints`（可选）：
  - 给 retriever/reranker 的 query 改写提示
  - 例如：优先查某些术语表或字段
- `tools_allowlist`（强制、受控）：
  - 允许此 Skill 在 tool gateway 中调用的工具集合

### 4. Skill 的注入策略（Kernel 侧）
步骤：
1. Router/Mode 决策后确定候选 profiles/skills
2. Kernel 从 Skills Registry 选中匹配的 skill 列表
3. 按规则注入：
   - 安全 core prompt（固定）
   - persona（固定/可选）
   - Skill prompt_addon（按匹配分数排序，限制总 token 与条数）
4. 收紧 tool allowlist：
   - 模型只能在 tool loop 中调用 manifest 允许的工具名
5. 记录 trace：
   - `active_skill_ids`、每个 skill 的 version 与注入 token 估计

### 5. 安全与验收标准
- 未在 allowlist 的工具名必须拒绝并记录 `tool_call_failed`
- prompt_addon 不得包含“修改系统安全策略/解锁未授权工具”的指令（这条可用静态扫描辅助）
- Skill 的任何版本变更必须能通过 eval replay 回归（与 promote 门禁挂钩）

### 6. 需求归类判定清单（Skill / Profile / Tool）
用于在评审需求时快速判断“应该改哪一层”。

#### 6.1 十条判定规则
1. 如果需求是“增强某个领域的回答风格、术语、关注点”，优先归类为 **Skill**（`prompt_addon`）。
2. 如果需求是“改检索词偏好、术语映射、召回提示”，优先归类为 **Skill**（`retrieval_hints`）。
3. 如果需求是“在当前任务中限制可调用工具集合”，归类为 **Skill**（`tools_allowlist` 收紧）。
4. 如果需求是“新增一个外部能力/API 调用”，归类为 **Tool**（Registry + Gateway + schema）。
5. 如果需求是“模型要按多步流程执行/切换角色协作”，归类为 **Profile**（runner 编排）。
6. 如果需求是“调整 single/multi 模式、轮数、预算策略”，归类为 **Kernel/Profile**，不是 Skill。
7. 如果需求是“改变全局安全规则、合规边界、不可做事项”，归类为 **Constitution**，不是 Skill。
8. 如果需求要求“动态突破白名单或动态注册新工具”，应拒绝直接实现；改为走 Tool Registry 正式变更流程。
9. 如果需求需要“跨轮持久状态机或黑板状态变更逻辑”，归类为 **Kernel/Runner**，不是 Skill。
10. 如果一个需求同时涉及“领域偏置 + 执行流程 + 新工具”，必须拆分为三类变更分别评审，避免单一 Skill 承担过多职责。

#### 6.2 三步决策法（评审时可直接使用）
- 第一步：先问“这是在改**偏置**、**流程**还是**能力**？”
- 第二步：按映射落位：
  - 偏置 -> Skill
  - 流程 -> Profile/Kernel
  - 能力 -> Tool
- 第三步：安全复核：
  - 是否试图扩权？
  - 是否影响全局安全边界？
  - 是否可被 trace + version + eval replay 覆盖？

#### 6.3 最终归类原则
- 能用 Skill 解决的需求，应保持在 manifest 可声明字段内，不引入执行逻辑。
- 一旦需求涉及执行编排或外部能力扩展，应升级到 Profile/Kernel 或 Tool 层实现。

