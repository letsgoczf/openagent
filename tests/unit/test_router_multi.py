from __future__ import annotations

from backend.config_loader import (
    EmbeddingConfig,
    EvidenceConfig,
    GenerationConfig,
    ModelsConfig,
    MultiAgentConfig,
    OpenAgentSettings,
    OrchestrationConfig,
    RagConfig,
    RagRecallConfig,
    RagRerankConfig,
    StorageConfig,
    TokenizationConfig,
)
from backend.kernel.router import route_query


def _minimal_settings() -> OpenAgentSettings:
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
        storage=StorageConfig(sqlite_path=":memory:"),
        tokenization=TokenizationConfig(provider="auto"),
        evidence=EvidenceConfig(),
        rag=RagConfig(recall=RagRecallConfig(), rerank=RagRerankConfig()),
    )


def test_route_multi_strips_prefix() -> None:
    s = _minimal_settings()
    s.orchestration = OrchestrationConfig(
        multi_agent=MultiAgentConfig(enabled=True, trigger_prefix="[multi]")
    )
    d = route_query("[multi]  总结文档", settings=s)
    assert d["mode"] == "multi"
    assert d["effective_query"] == "总结文档"
    assert d["profiles"] == ["analyst", "synthesizer"]


def test_route_single_without_prefix() -> None:
    s = _minimal_settings()
    d = route_query("普通问题", settings=s)
    assert d["mode"] == "single"
    assert d["effective_query"] == "普通问题"


def test_route_multi_disabled_ignores_prefix() -> None:
    s = _minimal_settings()
    s.orchestration = OrchestrationConfig(
        multi_agent=MultiAgentConfig(enabled=False, trigger_prefix="[multi]")
    )
    d = route_query("[multi] x", settings=s)
    assert d["mode"] == "single"
