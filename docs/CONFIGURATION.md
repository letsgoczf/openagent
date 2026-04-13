# OpenAgent 配置说明

**[English](./CONFIGURATION.en.md)**

本文说明主配置文件 **`config/openagent.yaml`** 的写法、环境变量覆盖方式，以及与 **工具 / Agent Skills / 提示词模板** 相关的约定。实现细节以代码为准：`backend/config_loader.py`（Pydantic 模型）、`backend/registry/`。

---

## 1. 配置文件位置与加载

| 方式 | 说明 |
|------|------|
| 默认 | 仓库根下 `config/openagent.yaml` |
| 自定义 | 环境变量 **`OPENAGENT_CONFIG`** 指向任意 YAML 文件路径 |

加载顺序：**先读 YAML，再合并 `OPENAGENT_*` 环境变量**（见下文）。校验失败时进程启动会报错。

---

## 2. 环境变量覆盖（`OPENAGENT_`）

- 前缀：**`OPENAGENT_`**
- 嵌套层级：用 **双下划线 `__`** 连接，键名 **不区分大小写**（会规范为小写再写入）
- 标量解析：`true` / `false` / `null` / 数字 / 其余视为字符串

示例：

```bash
export OPENAGENT_CONFIG=/path/to/my-openagent.yaml
export OPENAGENT_MODELS__GENERATION__PROVIDER=ollama
export OPENAGENT_MODELS__GENERATION__MODEL_ID=qwen2.5:latest
export OPENAGENT_ORCHESTRATION__MULTI_AGENT__ENABLED=false
export OPENAGENT_SKILL_ROUTER__ENABLED=true
```

**注意**：`OPENAGENT_CONFIG` 本身不参与嵌套覆盖，仅用于指定 YAML 路径。

---

## 3. 常用段落速览

以下字段名与 `openagent.yaml` 及 `OpenAgentSettings` 一致。未列出的键多为模型/存储/RAG 调参，见模板文件内注释。

### 3.1 `constitution_path`

- 系统级 Markdown 提示词（相对**仓库根**，或绝对路径）。
- `null` 时使用代码内置简短默认。

### 3.2 `orchestration.multi_agent`

- **`enabled`**：是否启用多智能体 MVP。
- **`trigger_prefix`**：用户消息 strip 后以此前缀开头则进入 **analyst → synthesizer** 两阶段；前缀会从正文里去掉。

### 3.3 `prompt_management`

- 从 **`prompts_dir`**（默认 `prompts/`）扫描 **`*.agent.md`**，由顶层 LLM 按任务选择要注入的模板。
- **`enabled: true`** 时每轮对话 **多 1 次** 规划 LLM，计入 Budget。
- 常用键：`planner_max_tokens`、`max_templates_per_role`、`max_chars_per_template`。

### 3.4 `memory`

- 会话记忆、滚动摘要、向量片段等；关闭可将 **`memory.enabled`** 设为 `false`。
- 细项见 `openagent.yaml` 内注释（`session_max_turns`、`fragments_enabled` 等）。

### 3.5 `tools`（工具注册表）

每项至少包含：

- **`name`**：工具名（与内置 handler、Skills 白名单一致）。
- **`description`**：给模型看的说明。
- **`input_schema`**：JSON Schema 风格（`properties` / `required`）。
- **`enabled`**、**`timeout_seconds`**、**`tags`**（可选）。

**内置 handler**（在 `backend/registry/builtin_tools.py` 绑定）：

- **`web_search`**：需在 `tools` 中声明后才会注册给模型；实现为 DuckDuckGo 摘要类请求。
- **`read_skill_reference`**：当 **`skills_bundle.enabled: true`** 且 `tools` 中**没有**同名项时，会**自动注册**（可用 `skills_bundle.auto_register_read_skill_tool: false` 关闭）。

### 3.6 `skills_bundle`（磁盘 Agent Skills）

与 [agentskills.io](https://agentskills.io/specification) 风格对齐的**目录包**：

- 根目录：仓库下 **`skills_dir`**（默认 `skills`）。
- 每个技能：**`skills/<skill-name>/SKILL.md`**，且 frontmatter 里 **`name`** 必须与目录名一致。

常用键：

| 键 | 说明 |
|----|------|
| **`enabled`** | 是否从磁盘加载技能包 |
| **`skills_dir`** | 相对仓库根的路径 |
| **`defer_skill_body`** | 默认 `true`：仅命中关键词/路由后再读入 SKILL 正文（L2） |
| **`tool_name_aliases`** | 可选；**追加/覆盖**内置别名（见 §5） |
| **`auto_register_read_skill_tool`** | 默认 `true`：未声明时自动注册 `read_skill_reference` |

磁盘技能与 **`skills`**（YAML 列表）**合并**；同一 **`skill_id`** 时 **YAML 覆盖磁盘**。

### 3.7 `skill_router`

- **`enabled: true`** 时，除关键词外再用 **LLM** 根据 L1 目录（id / name / description）挑选技能；**每轮多 1 次** LLM，计入 Budget。
- **`mode`**：`hybrid`（关键词 ∪ LLM）或 `llm_only`（无结果时回退关键词）。
- **`max_tokens`**、**`max_skills_selected`**：约束路由输出。

### 3.8 `skills`（YAML 技能）

列表项字段：`skill_id`、`name`、`description`、`trigger_keywords`、`tools_allowlist`、`prompt_addon`、`enabled`、`tags`。

- **`trigger_keywords`**：子串匹配用户 query（不区分大小写）。
- **`tools_allowlist`**：非空时，匹配到该技能会将工具限制为列表内并集；空列表表示**不限制**。

### 3.9 `models` / `storage` / `rag` / `evidence` / `ocr` / `tokenization`

- **`models.generation`** / **`models.embedding`**：`provider`（`openai` | `ollama` | `vLLM`）、`model_id`、`base_url`、`api_key_env`（填**环境变量名**，勿写密钥明文）、Ollama **`think`** 等。
- **`storage`**：SQLite 路径、Qdrant `path` / `url` / `location`、`collection_name`、`memory_collection_name`。
- **`rag`**：召回规模、混合权重、`retrieval_policy`（`always` | `adaptive`）等。
- **`evidence`**：证据条与组装进 prompt 的 token 上限等。

---

## 4. Agent Skills（`SKILL.md`）写法约定

### 4.1 目录与文件

```text
skills/
  <skill-name>/
    SKILL.md              # 必填
    references/           # 可选，L3 长文
    assets/               # 可选
```

- 忽略以 **`.`** 或 **`_`** 开头的目录名。
- **`SKILL.md`** 顶部为 **YAML frontmatter**（`---` … `---`），正文为 Markdown。

### 4.2 Frontmatter 常用字段

| 字段 | 必填 | 说明 |
|------|------|------|
| **`name`** | 是 | 与父目录名一致；小写字母、数字、连字符 |
| **`description`** | 是 | 建议写清「做什么 + 何时用」，供 L1 展示与 skill_router |
| **`allowed-tools`** | 否 | 空格分隔的工具名；可与内置别名一起用（§5） |
| **`metadata`** | 否 | 扩展字符串键值；OpenAgent 使用见下 |

**`metadata` 中 OpenAgent 约定**（值为字符串时）：

- **`trigger_keywords`**：逗号分隔，等价于 YAML 技能的触发词。
- **`display_name`**：展示用名称。
- **`openagent_enabled`**：`false` / `0` / `no` 等可禁用该包。
- **`tags`**：逗号分隔标签。

### 4.3 渐进式披露（L1 / L2 / L3）

- **L1**：仅 `skill_id`、`name`、`description`（`list_l1_index()` / 路由 prompt）。
- **L2**：命中后注入 **`SKILL.md` 正文**（默认 `defer_skill_body: true` 时延后读盘）。
- **L3**：模型调用工具 **`read_skill_reference`**，只读 **`references/`** 与 **`assets/`** 下文件（禁止 `..`、禁止 `scripts/` 路径前缀）。

---

## 5. 工具名别名（`allowed-tools` → OpenAgent）

内置映射（**无需在 YAML 写 `tool_name_aliases` 也能用**）：

| 常见写法 | 映射到 |
|----------|--------|
| `Read` | `read_skill_reference` |
| `WebSearch` | `web_search` |

在 **`skills_bundle.tool_name_aliases`** 中可**覆盖或追加**：键不区分大小写；值为**空字符串**表示丢弃该 token。

---

## 6. 提示词模板目录（`prompts/*.agent.md`）

- 与 **`prompt_management`** 配合：扫描 **`*.agent.md`**，由规划 LLM 选择是否注入。
- 非 `*.agent.md` 的文件不会进入规划目录。

---

## 7. 最小可用配置思路

1. 复制 **`config/openagent.yaml`**，改 **`models`**、**`storage`**。
2. 需要联网搜索时保留 **`tools`** 中的 **`web_search`**。
3. 需要磁盘技能时设 **`skills_bundle.enabled: true`**，在 **`skills/`** 下添加 **`SKILL.md`**。
4. 可选：打开 **`prompt_management.enabled`**、**`skill_router.enabled`**（均增加 LLM 调用次数）。

---

## 8. 相关文档

- 仓库根 [`OPENAGENT_ARCHITECTURE.md`](../OPENAGENT_ARCHITECTURE.md) — 架构与事件
- [`config/README_DESIGN.md`](../config/README_DESIGN.md) — 配置侧设计笔记（若存在）
- [`skills/README_DESIGN.md`](../skills/README_DESIGN.md) — Skills 目录设计
- 开发命令见根目录 [`README.md`](../README.md)、[`README.en.md`](../README.en.md)
