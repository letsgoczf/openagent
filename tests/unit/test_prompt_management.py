from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from backend.config_loader import (
    EmbeddingConfig,
    EvidenceConfig,
    GenerationConfig,
    ModelsConfig,
    OpenAgentSettings,
    PromptManagementConfig,
    RagConfig,
    RagRecallConfig,
    RagRerankConfig,
    StorageConfig,
    TokenizationConfig,
    repo_root,
)
from backend.kernel.budget import Budget
from backend.models.base import ChatResponse, LLMAdapter
from backend.prompts.catalog import AgentTemplateEntry, discover_agent_templates, load_template_bodies
from backend.prompts.mentions import extract_forced_agent_templates
from backend.prompts.planner import plan_prompt_templates


class _StubLLM(LLMAdapter):
    def __init__(self, content: str) -> None:
        self._content = content

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> ChatResponse:
        return ChatResponse(content=self._content)


def _settings_pm_enabled() -> OpenAgentSettings:
    return OpenAgentSettings(
        models=ModelsConfig(
            generation=GenerationConfig(
                provider="ollama",
                model_id="tiny",
                base_url="http://127.0.0.1:11434",
            ),
            embedding=EmbeddingConfig(
                provider="ollama",
                model_id="nomic-embed-text",
                base_url="http://127.0.0.1:11434",
                vector_dimensions=4,
            ),
        ),
        storage=StorageConfig(sqlite_path="data/openagent.db"),
        tokenization=TokenizationConfig(provider="auto"),
        evidence=EvidenceConfig(max_evidence_entry_tokens=100),
        rag=RagConfig(
            recall=RagRecallConfig(
                top_k_dense=2,
                top_k_keyword=2,
                max_candidates=5,
                rerank_top_n=2,
            ),
            rerank=RagRerankConfig(strategy="merged_score"),
        ),
        prompt_management=PromptManagementConfig(enabled=True, max_templates_per_role=3),
    )


def test_discover_agent_templates_tmp(tmp_path: Path) -> None:
    (tmp_path / "alpha.agent.md").write_text('# Alpha Agent\n\nbody', encoding="utf-8")
    (tmp_path / "skip.md").write_text("x", encoding="utf-8")
    entries = discover_agent_templates(prompts_dir=tmp_path)
    assert [e.id for e in entries] == ["alpha"]
    assert "Alpha Agent" in entries[0].blurb or "alpha" in entries[0].blurb.lower()


def test_discover_repo_prompts_has_known_ids() -> None:
    entries = discover_agent_templates(prompts_dir=repo_root() / "prompts")
    ids = {e.id for e in entries}
    assert "alignment" in ids
    assert all(e.path.is_file() for e in entries)


def test_load_template_bodies_order_and_unknown_id(tmp_path: Path) -> None:
    p = tmp_path / "z.agent.md"
    p.write_text("ZCONTENT", encoding="utf-8")
    entries = [
        AgentTemplateEntry(id="z", path=p, blurb="z"),
        AgentTemplateEntry(id="missing", path=tmp_path / "nope.agent.md", blurb=""),
    ]
    bodies = load_template_bodies(["z", "ghost", "z"], entries=entries, max_chars_per_template=100)
    assert len(bodies) == 2
    assert "ZCONTENT" in bodies[0]
    assert "ZCONTENT" in bodies[1]


def test_plan_prompt_single_strips_synthesizer_templates() -> None:
    settings = _settings_pm_enabled()
    catalog = [
        AgentTemplateEntry(id="a", path=Path("p"), blurb="ba"),
        AgentTemplateEntry(id="b", path=Path("p2"), blurb="bb"),
    ]
    llm = _StubLLM('{"worker_templates":["a"],"synthesizer_templates":["b"],"rationale":"test"}')
    b = Budget(max_llm_calls=8)
    plan = plan_prompt_templates(
        query="hello",
        mode="single",
        llm=llm,
        budget=b,
        trace=MagicMock(),
        settings=settings,
        catalog=catalog,
    )
    assert plan.worker_templates == ["a"]
    assert plan.synthesizer_templates == []
    assert b.llm_calls_used == 1


def test_plan_prompt_multi_keeps_both_roles() -> None:
    settings = _settings_pm_enabled()
    catalog = [
        AgentTemplateEntry(id="x", path=Path("p"), blurb="bx"),
        AgentTemplateEntry(id="y", path=Path("p2"), blurb="by"),
    ]
    llm = _StubLLM('{"worker_templates":["x"],"synthesizer_templates":["y"],"rationale":""}')
    b = Budget(max_llm_calls=8)
    plan = plan_prompt_templates(
        query="q",
        mode="multi",
        llm=llm,
        budget=b,
        trace=MagicMock(),
        settings=settings,
        catalog=catalog,
    )
    assert plan.worker_templates == ["x"]
    assert plan.synthesizer_templates == ["y"]


def test_extract_forced_agent_templates_basic() -> None:
    allowed = frozenset({"alignment", "lit"})
    ids, cleaned = extract_forced_agent_templates(
        "@alignment 请做综述",
        allowed_ids=allowed,
    )
    assert ids == ["alignment"]
    assert cleaned == "请做综述"


def test_extract_unknown_mention_kept_in_text() -> None:
    allowed = frozenset({"alignment"})
    ids, cleaned = extract_forced_agent_templates(
        "see @ghost and @alignment end",
        allowed_ids=allowed,
    )
    assert ids == ["alignment"]
    assert "@ghost" in cleaned
    assert "end" in cleaned


def test_extract_dedupe_order() -> None:
    allowed = frozenset({"a", "b"})
    ids, cleaned = extract_forced_agent_templates(
        "@b @a @b x",
        allowed_ids=allowed,
    )
    assert ids == ["b", "a"]
    assert cleaned == "x"


def test_extract_email_not_stripped_without_catalog_id() -> None:
    allowed = frozenset({"alignment"})
    ids, cleaned = extract_forced_agent_templates(
        "mail user@gmail.com ok",
        allowed_ids=allowed,
    )
    assert ids == []
    assert "user@gmail.com" in cleaned


def test_plan_prompt_disabled_no_llm() -> None:
    s = _settings_pm_enabled()
    s = s.model_copy(update={"prompt_management": PromptManagementConfig(enabled=False)})
    catalog = [AgentTemplateEntry(id="a", path=Path("p"), blurb="b")]
    llm = _StubLLM('{"worker_templates":["a"],"synthesizer_templates":[],"rationale":""}')
    b = Budget(max_llm_calls=8)
    plan = plan_prompt_templates(
        query="q",
        mode="single",
        llm=llm,
        budget=b,
        trace=MagicMock(),
        settings=s,
        catalog=catalog,
    )
    assert plan.worker_templates == []
    assert b.llm_calls_used == 0
