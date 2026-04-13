from __future__ import annotations

from backend.kernel.budget import Budget
from backend.memory.eval_report import summarize_memory_trace_events
from backend.memory.fragment_llm import (
    extract_fragments_via_llm,
    parse_fragments_json,
    reconstruct_context_via_llm,
)
from backend.models.base import ChatResponse
from backend.models.tokenizer import TokenizerService


def test_parse_fragments_json_object() -> None:
    raw = '{"fragments": ["a", "b"]}'
    assert parse_fragments_json(raw) == ["a", "b"]


def test_parse_fragments_json_array_and_fence() -> None:
    raw = '```json\n["x", "y"]\n```'
    assert parse_fragments_json(raw) == ["x", "y"]


def test_summarize_memory_trace_events() -> None:
    ev = [
        ("memory_read", {"history_messages": 2, "rolling_summary_chars": 10, "reconstructed_fragment_chars": 20}),
        ("memory_write", {}),
        ("memory_fragments_write", {"count": 3}),
        ("memory_fragment_extract_llm", {"ok": True}),
        ("memory_reconstruct_llm", {"ok": True}),
        ("memory_consolidate", {"ok": True}),
        ("memory_consolidate", {"skipped": True, "reason": "budget"}),
        ("memory_consolidate", {"ok": False, "error": "x"}),
    ]
    s = summarize_memory_trace_events(ev)
    assert s["memory_read_count"] == 1
    assert s["memory_fragments_write_total"] == 3
    assert s["memory_fragment_extract_llm_ok"] == 1
    assert s["memory_reconstruct_llm_ok"] == 1
    assert s["memory_consolidate_ok"] == 1
    assert s["memory_consolidate_skipped"] == 1
    assert s["memory_consolidate_failed"] == 1


class _StubLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def chat(self, messages, stream=False, max_tokens=None, tools=None):
        return ChatResponse(content=self._content)


def test_reconstruct_context_via_llm_success() -> None:
    from backend.config_loader import MemoryConfig

    cfg = MemoryConfig(
        reconstruct_llm_enabled=True,
        fragment_context_max_tokens=500,
    )

    llm = _StubLLM("Fused: user likes tea and morning runs.")
    tok = TokenizerService(model_id="gpt-4o-mini")
    budget = Budget(max_llm_calls=2)
    out = reconstruct_context_via_llm(
        llm=llm,  # type: ignore[arg-type]
        budget=budget,
        cfg=cfg,
        query="What do you remember?",
        template_blob="• tea\n• morning run",
        tokenizer=tok,
        trace=None,
    )
    assert out and "tea" in out.lower()
    assert budget.llm_calls_used == 1


def test_extract_fragments_via_llm_json() -> None:
    from backend.config_loader import MemoryConfig

    cfg = MemoryConfig(
        fragment_llm_extraction_enabled=True,
        fragments_extract_max=4,
        fragment_max_chars=200,
        fragment_llm_extraction_max_tokens=200,
    )
    llm = _StubLLM('{"fragments": ["snippet_a", "snippet_b"]}')
    budget = Budget(max_llm_calls=2)
    fr = extract_fragments_via_llm(
        llm=llm,  # type: ignore[arg-type]
        budget=budget,
        cfg=cfg,
        user_text="Remember X",
        assistant_text="X is important.",
        trace=None,
    )
    assert fr == ["snippet_a", "snippet_b"]
    assert budget.llm_calls_used == 1
