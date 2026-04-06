## backend/evolve 详细设计（自主进化：harvest -> propose -> validate -> promote）

### 1. 目标
- 在安全边界内自动提出改进候选（constitution/skills/router/retrieval defaults 等）
- 通过 eval harness 门禁验证后才发布新版本
- 保证任何进化都可回滚、可复现、可追溯到失败模式聚类与 eval 结果

### 2. 进化对象边界（安全关键）
允许 evolve 修改（evolvable）：
- constitution evolvable 段（例如可调 evidence 展示口径/策略描述）
- skills 的选择逻辑与 retrieval query_template（只在允许字段中）
- router 的策略与选择阈值（不扩权）

禁止 evolve 修改（non-evolvable）：
- 工具白名单扩张
- 预算上限放大
- 安全策略核心边界

### 3. sidecar 作业生命周期
#### 3.1 harvest
- 从 trace store 聚类失败模式：
  - retrieval miss 频率
  - citation coverage 不足
  - OCR on_miss 使用率与效果（如果开启）
  - tool call failure patterns

输出：
- failure_clusters（每个 cluster 提供典型 case_id 集与原因摘要）

#### 3.2 propose
- 根据 failure_clusters 生成候选改动（结构化 diff 或配置 patch）
- 每个候选带：
  - `candidate_id`
  - `changes`（只允许 evolvable 字段）
  - 预期改进方向（与指标关联）

#### 3.3 validate
- 对每个 candidate 跑 eval replay：
  - 必须 L0/L1 pass
  - L2/L3 达到阈值（例如不下降超过 delta）

输出：
- EvalGateResult：pass/fail + metric delta

#### 3.4 promote
- 仅在 validate pass 时发布新版本：
  - 写入 constitution_version/profile_set_hash/router_policy_id 指纹
  - 提供回滚开关（保留旧版本）

### 4. 验收标准
- evolve 自动化不会改变安全边界
- promote 必须可解释：失败模式 -> propose -> eval 改进证据
- 全流程产物可复现（同输入同候选应得到同 eval 结果）

