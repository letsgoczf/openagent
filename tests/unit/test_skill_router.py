from __future__ import annotations

from unittest.mock import MagicMock

from backend.config_loader import (
    EmbeddingConfig,
    GenerationConfig,
    ModelsConfig,
    OpenAgentSettings,
    SkillItemConfig,
    SkillRouterConfig,
    SkillsBundleConfig,
    StorageConfig,
    TokenizationConfig,
)
from backend.kernel.budget import Budget
from backend.models.base import ChatResponse, LLMAdapter
from backend.registry.service import build_registry_service
from backend.registry.skill_registry import SkillManifest, SkillRegistry
from backend.registry.skill_router import llm_pick_skill_ids, resolve_matched_skills


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


def _minimal_settings(tmp_path) -> OpenAgentSettings:
    return OpenAgentSettings(
        models=ModelsConfig(
            generation=GenerationConfig(
                provider="ollama",
                model_id="m",
                base_url="http://127.0.0.1:11434",
            ),
            embedding=EmbeddingConfig(
                provider="ollama",
                model_id="e",
                base_url="http://127.0.0.1:11434",
                vector_dimensions=4,
            ),
        ),
        storage=StorageConfig(sqlite_path=str(tmp_path / "db.sqlite")),
        tokenization=TokenizationConfig(provider="auto"),
        skills_bundle=SkillsBundleConfig(enabled=False),
        skills=[
            SkillItemConfig(
                skill_id="alpha",
                name="Alpha",
                description="Alpha skill for tests",
                trigger_keywords=["alpha_kw"],
                tools_allowlist=["t1"],
                prompt_addon="ALPHA_ADDON",
            ),
            SkillItemConfig(
                skill_id="beta",
                name="Beta",
                description="Beta skill for router",
                trigger_keywords=[],
                tools_allowlist=["t2"],
                prompt_addon="BETA_ADDON",
            ),
        ],
    )


def test_resolve_disabled_uses_keywords_only(tmp_path) -> None:
    settings = _minimal_settings(tmp_path)
    settings = settings.model_copy(
        update={"skill_router": SkillRouterConfig(enabled=False)}
    )
    reg = build_registry_service(settings).skill_registry
    out = resolve_matched_skills(
        reg,
        "has alpha_kw here",
        llm=_StubLLM('{"skill_ids":["beta"]}'),
        budget=Budget(max_llm_calls=8),
        trace=MagicMock(),
        settings=settings,
    )
    assert len(out) == 1
    assert out[0].skill_id == "alpha"


def test_resolve_hybrid_unions(tmp_path) -> None:
    settings = _minimal_settings(tmp_path)
    settings = settings.model_copy(
        update={
            "skill_router": SkillRouterConfig(enabled=True, mode="hybrid"),
        }
    )
    reg = build_registry_service(settings).skill_registry
    out = resolve_matched_skills(
        reg,
        "alpha_kw and need beta",
        llm=_StubLLM('{"skill_ids":["beta"]}'),
        budget=Budget(max_llm_calls=8),
        trace=MagicMock(),
        settings=settings,
    )
    ids = {s.skill_id for s in out}
    assert ids == {"alpha", "beta"}


def test_resolve_llm_only_fallback_to_keywords(tmp_path) -> None:
    settings = _minimal_settings(tmp_path)
    settings = settings.model_copy(
        update={
            "skill_router": SkillRouterConfig(enabled=True, mode="llm_only"),
        }
    )
    reg = build_registry_service(settings).skill_registry
    out = resolve_matched_skills(
        reg,
        "alpha_kw only",
        llm=_StubLLM('{"skill_ids":[]}'),
        budget=Budget(max_llm_calls=8),
        trace=MagicMock(),
        settings=settings,
    )
    assert len(out) == 1
    assert out[0].skill_id == "alpha"


def test_llm_pick_records_budget_on_success() -> None:
    b = Budget(max_llm_calls=8)
    llm = _StubLLM('{"skill_ids":["x"]}')
    ids = llm_pick_skill_ids(
        query="q",
        l1_index=[{"skill_id": "x", "name": "X", "description": "d"}],
        allowed_ids={"x"},
        llm=llm,
        budget=b,
        trace=MagicMock(),
        max_tokens=128,
        max_skills_selected=4,
    )
    assert ids == ["x"]
    assert b.llm_calls_used == 1


def test_merged_allowlist_from_matches_static() -> None:
    m = [
        SkillManifest(
            skill_id="a",
            name="",
            description="",
            tools_allowlist=["web_search"],
        ),
        SkillManifest(skill_id="b", name="", description="", tools_allowlist=[]),
    ]
    merged = SkillRegistry.merged_allowlist_from_matches(m)
    assert merged is not None
    assert "web_search" in merged
