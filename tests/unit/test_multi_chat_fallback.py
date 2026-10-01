"""Synthesizer 失败时必须保留 analyst 草稿，而不是用空串或错误占位覆盖。"""

from __future__ import annotations

from backend.kernel.blackboard import Blackboard
from backend.kernel.budget import Budget
from backend.kernel.multi_chat import run_sequential_two_agent
from backend.kernel.run_context import RunContext
from backend.kernel.trace import TraceWriter
from backend.rag.citation import Citation
from backend.rag.evidence_builder import EvidenceEntry
from backend.runners.chat_runner import ChatRunResult
from backend.storage.sqlite_store import SQLiteStore


def _cite(chunk_id: str) -> Citation:
    return Citation(
        chunk_id=chunk_id,
        version_id="v1",
        source_span={"page_number": 1},
        location_summary="Page 1",
    )


def _entry(chunk_id: str) -> EvidenceEntry:
    return EvidenceEntry(
        chunk_id=chunk_id,
        version_id="v1",
        origin_type="text",
        location_summary="Page 1",
        evidence_snippet_text_v1="年假 5 天",
        evidence_entry_tokens_v1=4,
    )


def _result(
    answer: str,
    *,
    chunk_id: str,
    degraded: bool = False,
    degrade_reason: str | None = None,
) -> ChatRunResult:
    return ChatRunResult(
        answer=answer,
        citations=[_cite(chunk_id)],
        evidence_entries=[_entry(chunk_id)],
        degraded=degraded,
        run_id="run-1",
        retrieval_state={"phase": chunk_id},
        degrade_reason=degrade_reason,
        thinking=None,
    )


class _ScriptedRunner:
    def __init__(self, results: list[ChatRunResult]) -> None:
        self._results = results
        self.calls = 0

    def run(self, *_args: object, **_kwargs: object) -> ChatRunResult:
        result = self._results[self.calls]
        self.calls += 1
        return result


def _run(results: list[ChatRunResult]) -> ChatRunResult:
    store = SQLiteStore(":memory:")
    try:
        runner = _ScriptedRunner(results)
        return run_sequential_two_agent(
            runner=runner,  # type: ignore[arg-type]
            ctx=RunContext(run_id="run-1", session_id="s1", budget=Budget()),
            trace=TraceWriter(store, "run-1"),
            blackboard=Blackboard(),
            effective_query="员工手册里年假有几天？",
            version_scope=None,
            stream=True,
            stream_writer=None,
            prompt_addons=None,
        )
    finally:
        store.close()


def test_llm_error_placeholder_keeps_analyst_draft() -> None:
    analyst = _result("年假为 5 天。[1]", chunk_id="analyst-chunk")
    synth = _result(
        "[LLM error: context length exceeded]\n",
        chunk_id="synth-chunk",
        degraded=True,
        degrade_reason="context length exceeded",
    )
    out = _run([analyst, synth])
    assert out.answer == analyst.answer
    assert [c.chunk_id for c in out.citations] == ["analyst-chunk"]
    assert out.retrieval_state["synthesizer_fallback"] == "context length exceeded"
    assert out.degraded is False


def test_empty_synthesizer_after_wall_clock_keeps_analyst_draft() -> None:
    analyst = _result("草稿里已经写明年假 5 天。", chunk_id="analyst-chunk")
    synth = _result("", chunk_id="synth-chunk", degraded=True, degrade_reason="wall_clock")
    out = _run([analyst, synth])
    assert out.answer == analyst.answer
    assert out.retrieval_state["synthesizer_fallback"] == "wall_clock"


def test_budget_placeholder_keeps_analyst_draft() -> None:
    analyst = _result("保留这份初稿。", chunk_id="analyst-chunk")
    synth = _result(
        "[Degraded: LLM budget exhausted]\n",
        chunk_id="synth-chunk",
        degraded=True,
        degrade_reason="llm_or_token_budget",
    )
    out = _run([analyst, synth])
    assert out.answer == analyst.answer


def test_usable_synthesizer_answer_is_kept() -> None:
    analyst = _result("初稿。", chunk_id="analyst-chunk")
    synth = _result("终稿：年假 5 天。[1]", chunk_id="synth-chunk")
    out = _run([analyst, synth])
    assert out.answer == synth.answer
    assert "synthesizer_fallback" not in out.retrieval_state
    assert [c.chunk_id for c in out.citations] == ["analyst-chunk", "synth-chunk"]
