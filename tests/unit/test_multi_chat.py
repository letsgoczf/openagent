from __future__ import annotations

import threading
from unittest.mock import MagicMock

from backend.kernel.blackboard import Blackboard
from backend.kernel.budget import Budget
from backend.kernel.multi_chat import run_sequential_two_agent
from backend.kernel.run_context import RunContext
from backend.runners.chat_runner import ChatRunResult


class _CancellingRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, ctx: RunContext, *args, **kwargs) -> ChatRunResult:
        self.calls += 1
        assert ctx.budget.cancel_event is not None
        ctx.budget.cancel_event.set()
        return ChatRunResult(
            answer="partial analyst draft",
            citations=[],
            evidence_entries=[],
            degraded=True,
            run_id=ctx.run_id,
            retrieval_state={"phase": "analyst"},
            degrade_reason="user_cancelled",
        )


def test_multi_chat_cancel_after_analyst_does_not_start_synthesizer() -> None:
    runner = _CancellingRunner()
    ctx = RunContext(
        run_id="run_cancel",
        session_id="s1",
        budget=Budget(cancel_event=threading.Event()),
    )

    result = run_sequential_two_agent(
        runner=runner,  # type: ignore[arg-type]
        ctx=ctx,
        trace=MagicMock(),
        blackboard=Blackboard(),
        effective_query="question",
        version_scope=None,
        stream=True,
        stream_writer=MagicMock(),
        prompt_addons=[],
    )

    assert runner.calls == 1
    assert result.answer == "partial analyst draft"
    assert result.degrade_reason == "user_cancelled"
