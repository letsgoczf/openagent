# OpenAgent configuration guide

This document describes how to author **`config/openagent.yaml`**, how **`OPENAGENT_*`** environment variables override it, and conventions for **tools**, **Agent Skills**, and **prompt templates**. Authoritative implementation: `backend/config_loader.py` (Pydantic models) and `backend/registry/`.

**[简体中文](./CONFIGURATION.md)**

---

## 1. Config file location and loading

| Method | Details |
|--------|---------|
| Default | `config/openagent.yaml` at the repository root |
| Custom | Set **`OPENAGENT_CONFIG`** to any YAML file path |

Load order: **YAML first, then merge `OPENAGENT_*` env vars** (see below). Invalid settings fail at startup.

---

## 2. Environment variable overrides (`OPENAGENT_`)

- Prefix: **`OPENAGENT_`**
- Nesting: use **double underscores `__`**; keys are **case-insensitive** (normalized to lowercase)
- Scalars: `true` / `false` / `null` / numbers; anything else is treated as a string

Examples:

```bash
export OPENAGENT_CONFIG=/path/to/my-openagent.yaml
export OPENAGENT_MODELS__GENERATION__PROVIDER=ollama
export OPENAGENT_MODELS__GENERATION__MODEL_ID=qwen2.5:latest
export OPENAGENT_ORCHESTRATION__MULTI_AGENT__ENABLED=false
export OPENAGENT_SKILL_ROUTER__ENABLED=true
```

**Note:** `OPENAGENT_CONFIG` is not part of nested overrides; it only selects the YAML path.

---

## 3. Common sections

Field names match `openagent.yaml` and `OpenAgentSettings`. Keys not listed here are usually model/storage/RAG tuning; see inline comments in the template file.

### 3.1 `constitution_path`

- System prompt Markdown (path **relative to repo root**, or absolute).
- `null` uses a short built-in default.

### 3.2 `orchestration.multi_agent`

- **`enabled`**: enable the multi-agent MVP.
- **`trigger_prefix`**: after trimming, if the user message starts with this prefix, run **analyst → synthesizer**; the prefix is stripped from the text sent to the models.

### 3.3 `prompt_management`

- Scans **`prompts_dir`** (default `prompts/`) for **`*.agent.md`**; a planner LLM selects templates to inject.
- **`enabled: true`** adds **one** planner LLM call per turn (counts against Budget).
- Common keys: `planner_max_tokens`, `max_templates_per_role`, `max_chars_per_template`.

### 3.4 `memory`

- Session history, rolling summary, vector fragments, etc.; set **`memory.enabled`** to `false` to disable.
- See comments in `openagent.yaml` (`session_max_turns`, `fragments_enabled`, …).

### 3.5 `tools` (tool registry)

Each entry needs at least:

- **`name`**: tool id (must match built-in handlers and skill allowlists).
- **`description`**: text shown to the model.
- **`input_schema`**: JSON Schema style (`properties` / `required`).
- **`enabled`**, **`timeout_seconds`**, **`tags`** (optional).

**Built-in handlers** (wired in `backend/registry/builtin_tools.py`):

- **`web_search`**: must appear under `tools` to be exposed; uses a DuckDuckGo-style instant-answer fetch.
- **`read_skill_reference`**: when **`skills_bundle.enabled: true`** and there is **no** tool with that name in `tools`, it is **auto-registered** (disable with `skills_bundle.auto_register_read_skill_tool: false`).

### 3.6 `skills_bundle` (on-disk Agent Skills)

Directory layout aligned with [agentskills.io](https://agentskills.io/specification):

- Root: **`skills_dir`** under the repo (default `skills`).
- Each skill: **`skills/<skill-name>/SKILL.md`**, and frontmatter **`name`** must equal the directory name.

Common keys:

| Key | Purpose |
|-----|---------|
| **`enabled`** | Load packages from disk |
| **`skills_dir`** | Path relative to repo root |
| **`defer_skill_body`** | Default `true`: load SKILL body (L2) only after keyword/router match |
| **`tool_name_aliases`** | Optional; **add/override** built-in aliases (§5) |
| **`auto_register_read_skill_tool`** | Default `true`: register `read_skill_reference` if missing from `tools` |

Disk skills are **merged** with the YAML **`skills`** list; for the same **`skill_id`**, **YAML wins**.

### 3.7 `skill_router`

- **`enabled: true`**: besides keywords, an **LLM** picks skills from the L1 index (id / name / description); **one extra LLM call** per turn (Budget).
- **`mode`**: `hybrid` (keywords ∪ LLM) or `llm_only` (fallback to keywords if empty/failed).
- **`max_tokens`**, **`max_skills_selected`**: cap router output.

### 3.8 `skills` (YAML skills)

List fields: `skill_id`, `name`, `description`, `trigger_keywords`, `tools_allowlist`, `prompt_addon`, `enabled`, `tags`.

- **`trigger_keywords`**: substring match on the user query (case-insensitive).
- **`tools_allowlist`**: if non-empty, matched skills restrict tools to the union of listed names; an **empty** list means **no restriction**.

### 3.9 `models` / `storage` / `rag` / `evidence` / `ocr` / `tokenization`

- **`models.generation`** / **`models.embedding`**: `provider` (`openai` | `ollama` | `vllm`), `model_id`, `base_url`, `api_key_env` (**env var name only**, never the secret), Ollama **`think`**, etc.
- **`storage`**: SQLite path, Qdrant `path` / `url` / `location`, `collection_name`, `memory_collection_name`.
- **`rag`**: recall sizes, hybrid weights, `retrieval_policy` (`always` | `adaptive`), etc.
- **`evidence`**: per-entry and assembled evidence token limits for prompts.

---

## 4. Agent Skills (`SKILL.md`) conventions

### 4.1 Layout

```text
skills/
  <skill-name>/
    SKILL.md              # required
    references/           # optional, L3 long-form
    assets/               # optional
```

- Skip directory names starting with **`.`** or **`_`**.
- **`SKILL.md`** starts with **YAML frontmatter** (`---` … `---`), body is Markdown.

### 4.2 Frontmatter

| Field | Required | Notes |
|-------|----------|--------|
| **`name`** | Yes | Must match parent folder; lowercase letters, digits, hyphens |
| **`description`** | Yes | Describe what it does **and** when to use it (L1 + skill_router) |
| **`allowed-tools`** | No | Space-separated names; may use built-in aliases (§5) |
| **`metadata`** | No | String key/value extensions; OpenAgent keys below |

**OpenAgent `metadata` (string values):**

- **`trigger_keywords`**: comma-separated, same idea as YAML `trigger_keywords`.
- **`display_name`**: human-readable label.
- **`openagent_enabled`**: `false` / `0` / `no` etc. disables the package.
- **`tags`**: comma-separated tags.

### 4.3 Progressive disclosure (L1 / L2 / L3)

- **L1**: only `skill_id`, `name`, `description` (`list_l1_index()` / router prompt).
- **L2**: after match, inject **`SKILL.md` body** (when `defer_skill_body: true`, read from disk at match time).
- **L3**: model calls **`read_skill_reference`**; only files under **`references/`** and **`assets/`** (no `..`, no paths starting with `scripts/`).

---

## 5. Tool name aliases (`allowed-tools` → OpenAgent)

Built-in mappings (**no need to set `tool_name_aliases` for these**):

| Common token | Maps to |
|--------------|---------|
| `Read` | `read_skill_reference` |
| `WebSearch` | `web_search` |

**`skills_bundle.tool_name_aliases`** can **override or extend**: keys are case-insensitive; a value of **empty string** drops that token.

---

## 6. Prompt templates (`prompts/*.agent.md`)

- Works with **`prompt_management`**: scans **`*.agent.md`**, planner LLM chooses injections.
- Files that are not `*.agent.md` are not part of the template catalog.

---

## 7. Minimal setup checklist

1. Copy **`config/openagent.yaml`**, edit **`models`** and **`storage`**.
2. Keep **`web_search`** under **`tools`** if you need web lookup.
3. For disk skills, set **`skills_bundle.enabled: true`** and add **`SKILL.md`** under **`skills/`**.
4. Optional: **`prompt_management.enabled`** and **`skill_router.enabled`** (each adds LLM calls per turn).

---

## 8. Related docs

- [`OPENAGENT_ARCHITECTURE.md`](../OPENAGENT_ARCHITECTURE.md) — architecture and events
- [`config/README_DESIGN.md`](../config/README_DESIGN.md) — config design notes (if present)
- [`skills/README_DESIGN.md`](../skills/README_DESIGN.md) — skills layout design
- Commands: root [`README.md`](../README.md) and [`README.en.md`](../README.en.md)
