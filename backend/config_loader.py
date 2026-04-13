from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

ENV_PREFIX = "OPENAGENT_"
# Path to YAML; not applied as nested config — skipped in env overlay.
OPENAGENT_CONFIG_ENV = "OPENAGENT_CONFIG"


class GenerationConfig(BaseModel):
    """LLM provider settings for chat/completions."""

    provider: Literal["openai", "ollama", "vllm"]
    model_id: str
    api_key_env: str | None = Field(
        default="OPENAI_API_KEY",
        description="Environment variable name holding the OpenAI API key.",
    )
    base_url: str | None = Field(
        default=None,
        description="Base URL for Ollama or vLLM (OpenAI-compatible) servers.",
    )
    think: bool | Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="Ollama 专用：对支持的思考模型开启 think，才会返回/流式输出 thinking 过程；null 表示不传参。",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="采样温度；null 表示不在请求里传 temperature，由服务端默认。",
    )


class EmbeddingConfig(BaseModel):
    """Embedding model for dense retrieval (Qdrant)."""

    provider: Literal["openai", "ollama", "vllm"] = "openai"
    model_id: str = "text-embedding-3-small"
    api_key_env: str | None = Field(
        default="OPENAI_API_KEY",
        description="Environment variable name for API key when provider needs it.",
    )
    base_url: str | None = Field(
        default=None,
        description="Base URL for Ollama or OpenAI-compatible embedding endpoints.",
    )
    vector_dimensions: int | None = Field(
        default=None,
        ge=1,
        description="Qdrant collection vector size; omit to resolve at runtime from the model.",
    )


class ModelsConfig(BaseModel):
    generation: GenerationConfig
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)


class RagRecallConfig(BaseModel):
    """
    在线检索规模与混合权重：语义上与 ``backend/rag/demo/04_rag_recipes.HybridRAG``
    的 ``embedding_weight`` / ``keyword_weight`` 一致（稠密≈向量、关键词≈FTS5）。
    """

    top_k_dense: int = Field(default=50, ge=1, le=500)
    top_k_keyword: int = Field(default=30, ge=1, le=200)
    max_candidates: int = Field(default=120, ge=1, le=500)
    rerank_top_n: int = Field(default=10, ge=1, le=50)
    w_dense: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="稠密通道权重（对应 demo 中语义 / embedding 分支）",
    )
    w_keyword: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="关键词通道权重（对应 demo 中 keyword_weight）",
    )

    @model_validator(mode="after")
    def _normalize_weights(self) -> RagRecallConfig:
        s = float(self.w_dense) + float(self.w_keyword)
        if s <= 0:
            self.w_dense = 0.5
            self.w_keyword = 0.5
        else:
            self.w_dense = float(self.w_dense) / s
            self.w_keyword = float(self.w_keyword) / s
        return self


class RagRerankConfig(BaseModel):
    """Reranking after dense+keyword merge (see DEVELOPMENT_PLAN P3)."""

    strategy: Literal["merged_score", "cross_encoder"] = "merged_score"
    model_id: str | None = None
    provider: Literal["openai", "ollama", "vllm"] | None = None
    api_key_env: str | None = Field(
        default=None,
        description="Optional API key env for cross_encoder provider.",
    )
    base_url: str | None = None


class RagConfig(BaseModel):
    recall: RagRecallConfig = Field(default_factory=RagRecallConfig)
    allowed_origin_types: list[Literal["text", "table", "ocr"]] | None = Field(
        default=None,
        description="若设置，仅保留这些 origin_type 的 chunk（README_DESIGN 2.2 可选过滤）",
    )
    rerank: RagRerankConfig = Field(default_factory=RagRerankConfig)
    retrieval_policy: Literal["always", "adaptive"] = Field(
        default="always",
        description="always：每轮都执行 RAG；adaptive：先由 LLM 判定是否需要查知识库再检索（多耗 1 次 LLM）。",
    )
    retrieval_router_max_tokens: int = Field(
        default=80,
        ge=16,
        le=512,
        description="检索路由 LLM 输出 token 上限（仅 JSON）。",
    )
    retrieval_router_fail_open: bool = Field(
        default=True,
        description=(
            "仅 adaptive 策略：路由器 LLM 报错或 JSON 无法解析时，true=仍执行 RAG（宽松），"
            "false=跳过检索（收紧，减少无关文档命中）。"
        ),
    )


class QdrantConfig(BaseModel):
    """Qdrant 连接参数（与 qdrant_client.QdrantClient 一致，只能选一种连接方式）."""

    # 优先级：location > path > url（与 factory 中解析顺序一致）
    location: str | None = Field(
        default=None,
        description='例如 ":memory:" 使用进程内实例；设置后忽略 path / url',
    )
    path: str | None = Field(
        default=None,
        description="本地嵌入式存储目录；设置后使用 path 模式",
    )
    url: str | None = Field(
        default="http://127.0.0.1:6333",
        description="远程 Qdrant HTTP 地址（path / location 未设置时生效）",
    )
    api_key_env: str | None = Field(
        default=None,
        description="Qdrant Cloud 等需要密钥时，由此环境变量读取 API Key",
    )
    collection_name: str = Field(
        default="openagent_chunks",
        description="默认向量集合名（ingestion / retrieval 共用）",
    )
    memory_collection_name: str = Field(
        default="openagent_memory",
        description="Phase C：会话记忆片段向量集合（与文档 chunk 分离）",
    )


class StorageConfig(BaseModel):
    """本地 SQLite 与 Qdrant 向量库存放与连接。"""

    sqlite_path: str = Field(
        default="data/openagent.db",
        description="SQLite 数据库文件路径（相对仓库根或绝对路径）",
    )
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)


class TokenizationConfig(BaseModel):
    provider: Literal["auto", "tiktoken", "hf"] = "auto"
    tokenizer_model_id: str | None = None
    count_scope: Literal["full_messages_by_template_cache"] = (
        "full_messages_by_template_cache"
    )


class OcrTriggerConfig(BaseModel):
    mode: Literal["on_miss"] = "on_miss"


class OcrConfig(BaseModel):
    enabled: bool = False
    trigger: OcrTriggerConfig = Field(default_factory=OcrTriggerConfig)
    max_ocr_pages: int = Field(default=8, ge=1, le=128)
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    chunking: Literal["line"] = "line"
    coord_space: Literal["page_normalized"] = "page_normalized"


class EvidenceConfig(BaseModel):
    entry_template_version: Literal["v1"] = "v1"
    max_evidence_entry_tokens: int = Field(default=300, ge=50, le=2000)
    max_assembled_evidence_tokens: int = Field(
        default=1800,
        ge=200,
        le=20000,
        description="把多条 evidence 组装进单次 LLM 请求时的总 token 预算（不含 system prompt 与用户问题）。",
    )
    snippet_truncation_version: str = "v1"


class MultiAgentConfig(BaseModel):
    """多智能体 MVP：前缀触发顺序双阶段编排（见 ``kernel/multi_chat.py``）。"""

    enabled: bool = Field(
        default=True,
        description="为 false 时始终 single，忽略触发前缀。",
    )
    trigger_prefix: str = Field(
        default="[multi]",
        description="用户 query strip 后以前缀开头则进入 multi；前缀会从 effective_query 中去掉。",
    )


class OrchestrationConfig(BaseModel):
    multi_agent: MultiAgentConfig = Field(default_factory=MultiAgentConfig)


class PromptManagementConfig(BaseModel):
    """
    顶层 Agent 从 ``prompts/*.agent.md`` 中选择要注入的模板（计入 Budget 的一次短 LLM）。
    """

    enabled: bool = Field(
        default=False,
        description="为 true 时每轮 run 先规划再注入所选模板正文到 system 侧 addon。",
    )
    prompts_dir: str = Field(
        default="prompts",
        description="相对仓库根的模板目录，仅匹配 *.agent.md。",
    )
    planner_max_tokens: int = Field(
        default=512,
        ge=64,
        le=2048,
        description="规划 LLM 输出 JSON 的 max_tokens。",
    )
    max_templates_per_role: int = Field(
        default=3,
        ge=0,
        le=12,
        description="每个角色（worker / synthesizer）最多采纳的模板数量上限。",
    )
    max_chars_per_template: int = Field(
        default=12000,
        ge=500,
        le=200_000,
        description="单模板注入 system 前的最大字符数（超出截断）。",
    )


class MemoryConfig(BaseModel):
    """会话级情节记忆（Phase A）：同 session_id 多轮对话持久化与 prompt 注入。"""

    enabled: bool = Field(
        default=True,
        description="为 false 时不读写 chat_session_turn，行为与旧版单轮一致。",
    )
    session_max_turns: int = Field(
        default=16,
        ge=0,
        le=128,
        description="注入 prompt 时最多包含的「轮数」：一轮 = user + assistant 各一条。",
    )
    session_max_history_tokens: int = Field(
        default=4000,
        ge=0,
        le=200_000,
        description="历史消息（不含本轮 EVIDENCE/QUESTION 拼装块）的近似 token 上限。",
    )
    consolidate_after_turns: int = Field(
        default=48,
        ge=1,
        le=500,
        description="Phase B：会话总轮数（user+assistant 算一轮）达到该值后才允许触发巩固。",
    )
    consolidation_enabled: bool = Field(
        default=True,
        description="Phase B：是否启用滚动摘要；关闭后仅 Phase A 全量/截断读取。",
    )
    keep_recent_rounds: int = Field(
        default=8,
        ge=1,
        le=64,
        description="Phase B：每次注入 prompt 时保留的最近轮数（verbatim）；更早内容进滚动摘要。",
    )
    consolidation_max_output_tokens: int = Field(
        default=512,
        ge=128,
        le=8000,
        description="Phase B：单次巩固 LLM 输出摘要的 token 上限（近似）。",
    )
    rolling_summary_max_tokens: int = Field(
        default=1200,
        ge=0,
        le=32000,
        description="Phase B：注入 system 的滚动摘要 token 上限（超出则截断）。",
    )
    fragments_enabled: bool = Field(
        default=True,
        description="Phase C：是否写入/检索记忆片段（向量库 + SQLite）。",
    )
    fragment_top_k: int = Field(
        default=6,
        ge=0,
        le=32,
        description="Phase C：按当前 query 向量检索的片段条数上限。",
    )
    fragments_extract_max: int = Field(
        default=6,
        ge=1,
        le=24,
        description="Phase C：每轮对话最多抽取并入库的片段条数。",
    )
    fragment_max_chars: int = Field(
        default=480,
        ge=80,
        le=4000,
        description="Phase C：单条片段文本最大字符数。",
    )
    fragment_context_max_tokens: int = Field(
        default=900,
        ge=0,
        le=16000,
        description="Phase C：注入 system 的「检索片段」总 token 上限。",
    )
    fragment_llm_extraction_enabled: bool = Field(
        default=False,
        description="用 LLM 从单轮对话抽取片段（JSON）；计入 Budget；失败则回退规则抽取。",
    )
    fragment_llm_extraction_max_tokens: int = Field(
        default=500,
        ge=64,
        le=4000,
        description="片段抽取 LLM 输出 token 上限。",
    )
    reconstruct_llm_enabled: bool = Field(
        default=False,
        description="检索到片段后，再用 LLM 融合为短上下文；计入 Budget；失败则用模板列表。",
    )
    reconstruct_llm_max_tokens: int = Field(
        default=450,
        ge=64,
        le=4000,
        description="重构 LLM 输出 token 上限。",
    )


# ─────────────────────────── P6 Registry ────────────────────────────


class ToolItemConfig(BaseModel):
    """配置中的工具定义（Registry 层会转为 ToolDefinition）。"""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    timeout_seconds: float = 30.0
    tags: list[str] = Field(default_factory=list)


class SkillItemConfig(BaseModel):
    """配置中的技能定义（Registry 层会转为 SkillManifest）。"""

    skill_id: str
    name: str = ""
    description: str = ""
    trigger_keywords: list[str] = Field(default_factory=list)
    tools_allowlist: list[str] = Field(default_factory=list)
    prompt_addon: str = ""
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class SkillsBundleConfig(BaseModel):
    """
    磁盘技能包（agentskills.io 风格）：``skills_dir/<name>/SKILL.md``。
    与 ``openagent.yaml`` 的 ``skills`` 合并；同 ``skill_id`` 时 YAML 覆盖磁盘。
    """

    enabled: bool = Field(
        default=True,
        description="为 false 时仅从 openagent.yaml 加载 skills。",
    )
    skills_dir: str = Field(
        default="skills",
        description="相对仓库根；每个子目录一项技能，且须含 SKILL.md。",
    )
    defer_skill_body: bool = Field(
        default=True,
        description="为 true 时磁盘 SKILL.md 正文仅在技能被关键词命中后读入（渐进式披露 L2）。",
    )
    tool_name_aliases: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "追加/覆盖内置别名（Read→read_skill_reference、WebSearch→web_search）。"
            "值置空字符串表示丢弃该 token。"
        ),
    )
    auto_register_read_skill_tool: bool = Field(
        default=True,
        description="skills_bundle 启用且 tools 中未声明 read_skill_reference 时自动注册该工具。",
    )


class SkillRouterConfig(BaseModel):
    """
    用 LLM 根据 ``list_l1_index()`` 选择 skill_id；与关键词匹配组合（hybrid）或仅用 LLM（llm_only）。
    计入 Budget 的一次短调用；关闭后行为与仅关键词一致。
    """

    enabled: bool = Field(
        default=False,
        description="为 true 时在关键词之外（或替代）启用 LLM 选技能。",
    )
    mode: Literal["hybrid", "llm_only"] = Field(
        default="hybrid",
        description="hybrid：关键词命中 ∪ LLM 选择；llm_only：仅 LLM，解析失败或无结果时回退关键词。",
    )
    max_tokens: int = Field(default=256, ge=64, le=1024, description="路由 LLM 输出上限。")
    max_skills_selected: int = Field(
        default=4,
        ge=1,
        le=16,
        description="LLM 最多返回的技能 id 数。",
    )


class OpenAgentSettings(BaseModel):
    models: ModelsConfig
    constitution_path: str | None = Field(
        default="config/constitution.md",
        description="系统提示词 Markdown；相对仓库根；null 则用代码内置默认。",
    )
    storage: StorageConfig = Field(default_factory=StorageConfig)
    rag: RagConfig = Field(default_factory=RagConfig)
    tokenization: TokenizationConfig = Field(default_factory=TokenizationConfig)
    ocr: OcrConfig = Field(default_factory=OcrConfig)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    prompt_management: PromptManagementConfig = Field(default_factory=PromptManagementConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    # P6 Registry 字段
    tools: list[ToolItemConfig] = Field(default_factory=list)
    skills: list[SkillItemConfig] = Field(default_factory=list)
    skills_bundle: SkillsBundleConfig = Field(default_factory=SkillsBundleConfig)
    skill_router: SkillRouterConfig = Field(default_factory=SkillRouterConfig)


def repo_root() -> Path:
    """仓库根目录（与 `backend/`、`config/` 同级）。"""
    return Path(__file__).resolve().parent.parent


def resolve_repo_relative_path(rel_or_abs: str) -> Path:
    """相对路径相对于仓库根；绝对路径原样规范化。"""
    p = Path(rel_or_abs).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (repo_root() / p).resolve()


def default_config_path() -> Path:
    """Prefer OPENAGENT_CONFIG, then repo-root config/openagent.yaml, then CWD."""
    raw = os.environ.get(OPENAGENT_CONFIG_ENV)
    if raw:
        return Path(raw).expanduser().resolve()
    package_root = Path(__file__).resolve().parent.parent
    candidate = package_root / "config" / "openagent.yaml"
    if candidate.is_file():
        return candidate
    cwd_candidate = Path.cwd() / "config" / "openagent.yaml"
    if cwd_candidate.is_file():
        return cwd_candidate
    return candidate


def _parse_env_scalar(raw: str) -> Any:
    t = raw.strip()
    tl = t.lower()
    if tl in ("true", "yes", "on"):
        return True
    if tl in ("false", "no", "off"):
        return False
    if tl in ("null", "none", ""):
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t


def _deep_set(target: dict[str, Any], keys: list[str], value: Any) -> None:
    cur: dict[str, Any] = target
    for key in keys[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[keys[-1]] = value


def _apply_env_overrides(base: dict[str, Any]) -> None:
    """Merge OPENAGENT_* env vars using double-underscore nesting, lowercase keys."""
    for name, raw in os.environ.items():
        if not name.startswith(ENV_PREFIX):
            continue
        inner = name[len(ENV_PREFIX) :]
        if inner == "CONFIG":
            continue
        segments = [part.lower() for part in inner.split("__") if part]
        if not segments:
            continue
        _deep_set(base, segments, _parse_env_scalar(raw))


def load_config_dict(path: Path | None = None) -> dict[str, Any]:
    """Load YAML from disk, apply env overrides, return a plain dict (pre-Pydantic)."""
    cfg_path = path or default_config_path()
    if not cfg_path.is_file():
        raise FileNotFoundError(
            f"OpenAgent config not found: {cfg_path}. "
            f"Copy or create config/openagent.yaml, or set {OPENAGENT_CONFIG_ENV}."
        )
    text = cfg_path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    if loaded is None:
        data: dict[str, Any] = {}
    elif isinstance(loaded, dict):
        data = loaded
    else:
        raise ValueError(f"Config root must be a mapping, got {type(loaded).__name__}")
    _apply_env_overrides(data)
    return data


def load_config(path: Path | None = None) -> OpenAgentSettings:
    """Load and validate OpenAgent settings."""
    return OpenAgentSettings.model_validate(load_config_dict(path))
