"""工具结果必须回传模型，否则 tool_calls 轮次只会留下空/无用回答。"""

from __future__ import annotations

import json
from typing import Any
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
from backend.models.base import ChatResponse, LLMAdapter
from backend.rag.service import RetrievalResult
from backend.registry.tool_gateway import ToolGateway
from backend.registry.tool_registry import ToolDefinition, ToolRegistry
from backend.runners.chat_runner import ChatRunner
from backend.runners.tool_loop import chat_until_no_tools, format_tool_results_for_llm
from backend.storage.sqlite_store import SQLiteStore


class _ScriptedLLM(LLMAdapter):
    def __init__(self, responses: list[ChatResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        self.calls.append(list(messages))
        if not self._responses:
            return ChatResponse(content="")
        return self._responses.pop(0)


def test_format_tool_results_includes_payload() -> None:
    text = format_tool_results_for_llm(
        [
            {
                "tool_call_id": "tc1",
                "tool": "add",
                "result": True,
                "code": "ok",
                "payload": 7,
            }
        ]
    )
    assert "Tool results:" in text
    assert '"payload": 7' in text
    assert "add" in text


def test_chat_until_no_tools_feeds_actual_results_not_tool_calls() -> None:
    reg = ToolRegistry()
    reg.register(ToolDefinition(name="add", description="", input_schema={}))
    gw = ToolGateway(reg)
    gw.register_handler("add", lambda a=0, b=0: a + b)

    seen_user_payloads: list[str] = []

    def llm_complete(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]] | None]:
        for m in messages:
            if m.get("role") == "user" and str(m.get("content", "")).startswith("Tool results:"):
                seen_user_payloads.append(str(m["content"]))
        if len(seen_user_payloads) == 0:
            return "", [
                {
                    "id": "tc1",
                    "function": {
                        "name": "add",
                        "arguments": json.dumps({"a": 3, "b": 4}),
                    },
                }
            ]
        return "sum is 7", None

    out = chat_until_no_tools(
        messages=[{"role": "user", "content": "add 3 and 4"}],
        budget=Budget(max_llm_calls=4, max_tool_rounds=3),
        blackboard=Blackboard(),
        llm_complete=llm_complete,
        gateway=gw,
    )
    assert out == "sum is 7"
    assert seen_user_payloads, "expected tool results to be appended for the follow-up LLM call"
    assert '"payload": 7' in seen_user_payloads[0]
    # 旧 bug：把原始 tool_calls 请求当结果回传
    assert '"arguments"' not in seen_user_payloads[0]


@patch("backend.runners.chat_runner.embed_text", return_value=[1.0, 0.0, 0.0, 0.0])
@patch("backend.runners.chat_runner.RetrievalService")
def test_chat_runner_continues_after_tools(
    mock_rs_cls: MagicMock,
    _mock_embed: MagicMock,
    tmp_path,
) -> None:
    mock_rs_cls.return_value.retrieve.return_value = RetrievalResult(
        evidence_entries=[],
        citations=[],
        retrieval_state={"dense_hits": 0, "keyword_hits": 0},
        candidate_debug=None,
    )

    reg = ToolRegistry()
    reg.register(ToolDefinition(name="echo", description="", input_schema={}))
    gw = ToolGateway(reg)
    gw.register_handler("echo", lambda text="": f"echo:{text}")

    llm = _ScriptedLLM(
        [
            ChatResponse(
                content="",
                tool_calls=[
                    {
                        "id": "tc1",
                        "function": {
                            "name": "echo",
                            "arguments": json.dumps({"text": "hi"}),
                        },
                    }
                ],
            ),
            ChatResponse(content="heard: echo:hi"),
        ]
    )

    settings = OpenAgentSettings(
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
        storage=StorageConfig(sqlite_path=str(tmp_path / "tool_loop.db")),
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
    sqlite = SQLiteStore(settings.storage.sqlite_path)
    try:
        registry = MagicMock()
        registry.tool_gateway = gw
        registry.rag_registry.get_allowed_ids.return_value = None

        runner = ChatRunner(
            settings,
            sqlite,
            MagicMock(),
            llm,  # type: ignore[arg-type]
            MagicMock(count_tokens=lambda _t: 1),
            registry=registry,
            tool_schemas=[{"type": "function", "function": {"name": "echo"}}],
        )
        ctx = RunContext(
            run_id="run_tool_loop",
            session_id="s1",
            budget=Budget(max_llm_calls=4, max_tool_rounds=3),
        )
        trace = TraceWriter(sqlite, "run_tool_loop")
        result = runner.run(ctx, "please echo hi", trace, Blackboard())

        assert result.answer == "heard: echo:hi"
        assert len(llm.calls) == 2
        followup = llm.calls[1]
        tool_msgs = [
            m for m in followup if m.get("role") == "user" and "Tool results:" in str(m.get("content", ""))
        ]
        assert tool_msgs
        assert "echo:hi" in str(tool_msgs[0]["content"])
    finally:
        sqlite.close()
