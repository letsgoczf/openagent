from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.config_loader import (
    EmbeddingConfig,
    EvidenceConfig,
    GenerationConfig,
    MemoryConfig,
    ModelsConfig,
    OpenAgentSettings,
    RagConfig,
    RagRecallConfig,
    RagRerankConfig,
    StorageConfig,
    TokenizationConfig,
)
from backend.kernel.blackboard import Blackboard
from backend.kernel.budget import Budget
from backend.kernel.engine import KernelEngine
from backend.kernel.multi_chat import run_sequential_two_agent
from backend.kernel.run_context import RunContext
from backend.rag.citation import Citation
from backend.rag.evidence_builder import EvidenceEntry
from backend.rag.service import RetrievalResult
from backend.runners.chat_runner import ChatRunResult
from backend.storage.sqlite_store import SQLiteStore


def _settings_simple(tmp_path) -> OpenAgentSettings:
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
        storage=StorageConfig(
            sqlite_path=str(tmp_path / "engine.db"),
        ),
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
    )


@patch("backend.runners.chat_runner.embed_text", return_value=[1.0, 0.0, 0.0, 0.0])
@patch("backend.runners.chat_runner.build_qdrant_client")
@patch("backend.runners.chat_runner.create_llm_adapter")
@patch("backend.runners.chat_runner.RetrievalService")
def test_engine_trace_events_sequence(
    mock_rs_cls,
    mock_factory,
    mock_qclient,
    _mock_embed,
    tmp_path,
) -> None:
    mock_qclient.return_value = MagicMock()

    mock_factory.return_value = MagicMock()
    mock_factory.return_value.chat.return_value = "assistant reply [1]"

    ent = EvidenceEntry(
        chunk_id="c1",
        version_id="v1",
        origin_type="text",
        location_summary="Page 1",
        evidence_snippet_text_v1="snip",
        evidence_entry_tokens_v1=1,
    )
    cite = Citation(
        chunk_id="c1",
        version_id="v1",
        source_span={"page_number": 1},
        location_summary="Page 1",
    )
    rr = RetrievalResult(
        evidence_entries=[ent],
        citations=[cite],
        retrieval_state={"dense_hits": 1},
        candidate_debug=None,
    )

    inst = MagicMock()
    inst.retrieve.return_value = rr
    mock_rs_cls.return_value = inst

    settings = _settings_simple(tmp_path)
    eng = KernelEngine(settings=settings)
    out = eng.run_chat("hello world", budget=Budget(max_llm_calls=3))

    assert out.answer.strip() == "assistant reply [1]"
    assert out.citations[0].chunk_id == "c1"

    import sqlite3

    store_path = tmp_path / "engine.db"
    conn = sqlite3.connect(str(store_path))
    rows = conn.execute(
        "SELECT event_type FROM trace_event ORDER BY sequence_num"
    ).fetchall()
    types = [r[0] for r in rows]
    assert "run_started" in types
    assert "mode_selected" in types
    assert "retrieval_update" in types
    assert "evidence_update" in types
    assert "completed" in types
    conn.close()


def test_engine_does_not_persist_cancelled_chat_to_memory(tmp_path) -> None:
    settings = _settings_simple(tmp_path).model_copy(
        update={
            "memory": MemoryConfig(
                enabled=True,
                consolidation_enabled=False,
                fragments_enabled=False,
            )
        }
    )
    sqlite = SQLiteStore(tmp_path / "engine.db")
    runner = MagicMock()
    runner.llm_adapter = MagicMock()
    runner.run.return_value = ChatRunResult(
        answer="partial stopped answer",
        citations=[],
        evidence_entries=[],
        degraded=True,
        run_id="run-cancelled",
        retrieval_state={},
        degrade_reason="user_cancelled",
    )
    qdrant = MagicMock()

    with patch(
        "backend.kernel.engine.build_chat_runner",
        return_value=(runner, sqlite, qdrant),
    ):
        result = KernelEngine(settings=settings).run_chat(
            "remember this",
            session_id="sess-cancelled",
            budget=Budget(max_llm_calls=3),
        )

    assert result.degrade_reason == "user_cancelled"
    check = SQLiteStore(tmp_path / "engine.db")
    rows = check.fetch_chat_session_turns_recent("sess-cancelled", 10)
    assert rows == []
    check.close()


def test_multi_chat_returns_after_cancelled_analyst() -> None:
    class _Trace:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict[str, object] | None]] = []

        def emit(
            self,
            event_type: str,
            payload: dict[str, object] | None = None,
        ) -> None:
            self.events.append((event_type, payload))

    class _Runner:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, *args, **kwargs) -> ChatRunResult:
            self.calls += 1
            if self.calls > 1:
                raise AssertionError("synthesizer should not run after cancellation")
            return ChatRunResult(
                answer="partial draft",
                citations=[],
                evidence_entries=[],
                degraded=True,
                run_id="run-multi-cancelled",
                retrieval_state={"phase": "analyst"},
                degrade_reason="user_cancelled",
            )

    runner = _Runner()
    trace = _Trace()
    ctx = RunContext(
        run_id="run-multi-cancelled",
        session_id="sess-multi-cancelled",
        budget=Budget(max_llm_calls=3),
    )

    result = run_sequential_two_agent(
        runner=runner,  # type: ignore[arg-type]
        ctx=ctx,
        trace=trace,  # type: ignore[arg-type]
        blackboard=Blackboard(),
        effective_query="question",
        version_scope=None,
        stream=False,
        stream_writer=None,
        prompt_addons=None,
    )

    assert result.degrade_reason == "user_cancelled"
    assert runner.calls == 1
    assert (
        "merge_started",
        {"strategy": "cancelled_after_analyst", "sub_agents": ["sub_analyst"]},
    ) in trace.events
