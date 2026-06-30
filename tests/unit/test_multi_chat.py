from __future__ import annotations

from backend.kernel.blackboard import Blackboard
from backend.kernel.budget import Budget
from backend.kernel.multi_chat import run_sequential_two_agent
from backend.kernel.run_context import RunContext
from backend.kernel.trace import TraceWriter
from backend.runners.chat_runner import ChatRunResult
from backend.storage.sqlite_store import SQLiteStore


def test_multi_agent_cancelled_analyst_skips_synthesizer(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "trace.db")
    trace = TraceWriter(store, "run_cancel")

    class Runner:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, *args, **kwargs) -> ChatRunResult:
            self.calls += 1
            if self.calls > 1:
                raise AssertionError("synthesizer should not run after cancellation")
            return ChatRunResult(
                answer="partial",
                citations=[],
                evidence_entries=[],
                degraded=True,
                run_id="run_cancel",
                retrieval_state={"phase": "cancelled"},
                degrade_reason="user_cancelled",
            )

    runner = Runner()
    result = run_sequential_two_agent(
        runner=runner,  # type: ignore[arg-type]
        ctx=RunContext(run_id="run_cancel", session_id="s1", budget=Budget()),
        trace=trace,
        blackboard=Blackboard(),
        effective_query="hello",
        version_scope=None,
        stream=False,
        stream_writer=None,
        prompt_addons=None,
    )

    assert runner.calls == 1
    assert result.degraded is True
    assert result.degrade_reason == "user_cancelled"
    assert result.retrieval_state["multi_agent"] is True
    store.close()
