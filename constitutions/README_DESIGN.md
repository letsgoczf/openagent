## OpenAgent 宪法（Constitution）详细设计

### 1. 目标
- 类似 `CLAUDE.md`：为模型提供行为约束、输出格式偏好、失败时策略
- 支持版本化：`constitution_version` 必须能写入 trace，确保评估与回放一致

### 2. 存储与版本
- 建议用户在 `openagent/constitutions/` 放：
  - `OPENAGENT_CONSTITUTION_v1.md`（示例）
- 内核加载时记录：
  - constitution 文件 hash 或版本号

### 3. 可演进段与不可演进段（与 evolve 对齐）
- evolvable 段：例如输出风格、建议工具使用偏好、evidence 展示口径（在白名单内）
- non-evolvable：安全边界（禁止扩权、预算上限、证据引用规则等）

### 4. 验收标准
- constitution 改动必须触发 eval replay 并通过 promote gate
- constitution 注入位置必须固定（例如：系统级段落 + skill addon 插入段）

