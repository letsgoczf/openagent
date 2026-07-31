"""流式 tool_calls 不得作为 chat.delta content 推给前端。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from backend.config_loader import (
    EmbeddingConfig,
    EvidenceConfig,
    GenerationConfig,
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
from backend.kernel.run_context import RunContext
from backend.kernel.trace import TraceWriter
from backend.rag.service import RetrievalResult
from backend.registry.tool_gateway import ToolGateway
from backend.registry.tool_registry import ToolDefinition, ToolRegistry
from backend.runners.chat_runner import ChatRunner
from backend.storage.sqlite_store import SQLiteStore


def _settings(tmp_path) -> OpenAgentSettings:
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
        storage=StorageConfig(sqlite_path=str(tmp_path / "stream_tc.db")),
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
            retrieval_policy="always",
        ),
    )


@patch("backend.runners.chat_runner.embed_text", return_value=[1.0, 0.0, 0.0, 0.0])
def test_streaming_tool_calls_not_written_as_content(_mock_embed, tmp_path) -> None:
    """模型流式返回 content + tool_calls 时，stream_writer 不得收到 tool_calls。"""
    cfg = _settings(tmp_path)
    sqlite = SQLiteStore(cfg.storage.sqlite_path)
    qdrant = MagicMock()
    qdrant.collection_name = "chunks"

    tool_payload = [
        {
            "id": "tc_0",
            "type": "function",
            "function": {
                "name": "web_search",
                "arguments": json.dumps({"query": "news"}),
            },
        }
    ]

    def fake_stream(messages, *, stream=False, tools=None, **_kwargs):
        assert stream is True
        yield ("content", "正在检索…")
        yield ("tool_calls", json.dumps(tool_payload, ensure_ascii=False))

    llm = MagicMock()
    llm.chat.side_effect = fake_stream
    tok = MagicMock()
    tok.count_tokens.return_value = 1

    reg = ToolRegistry()
    reg.register(
        ToolDefinition(
            name="web_search",
            description="search",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
    )
    gw = ToolGateway(reg)
    gw.register_handler(
        "web_search",
        lambda query="": {"ok": True, "results": [{"title": query}]},
    )

    class _Reg:
        tool_gateway = gw
        rag_registry = MagicMock()

    _Reg.rag_registry.get_allowed_ids.return_value = None

    runner = ChatRunner(
        cfg,
        sqlite,
        qdrant,
        llm,
        tok,
        registry=_Reg(),
        tool_schemas=reg.get_all_schemas(),
    )

    with patch.object(
        runner._retrieval,
        "retrieve",
        return_value=RetrievalResult(
            evidence_entries=[],
            citations=[],
            retrieval_state={"dense_hits": 0, "keyword_hits": 0},
        ),
    ):
        streamed: list[tuple[str, str]] = []

        def stream_writer(kind: str, text: str) -> None:
            streamed.append((kind, text))

        ctx = RunContext(run_id="r1", session_id="s1", budget=Budget())
        trace = TraceWriter(sqlite, "r1")
        result = runner.run(
            ctx,
            "搜索一下新闻",
            trace,
            Blackboard(),
            stream=True,
            stream_writer=stream_writer,
        )

    assert result.answer == "正在检索…"
    assert streamed == [("content", "正在检索…")]
    leaked = "".join(text for kind, text in streamed if kind == "content")
    assert "web_search" not in leaked
    assert "tc_0" not in leaked
    assert llm.chat.called

    sqlite.close()


def test_ws_stream_writer_drops_tool_calls_kind() -> None:
    """与 ws_handler.stream_writer 相同的 kind 契约：tool_calls/未知 kind 不入队。"""
    sent: list[dict] = []

    def stream_writer(kind: str, text: str) -> None:
        if kind == "tool_calls":
            return
        if kind == "thinking":
            sent.append({"delta_kind": "thinking", "delta": text})
        elif kind == "citations":
            sent.append({"delta_kind": "citations", "delta": text})
        elif kind == "content":
            sent.append({"delta_kind": "content", "delta": text})
        else:
            return

    stream_writer("content", "hello")
    stream_writer("tool_calls", json.dumps([{"id": "tc"}]))
    stream_writer("mystery", "nope")
    assert sent == [{"delta_kind": "content", "delta": "hello"}]
