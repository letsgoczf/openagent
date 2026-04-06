from __future__ import annotations

import time

from backend.kernel.budget import Budget


def test_budget_llm_calls_exhausted() -> None:
    b = Budget(max_llm_calls=2)
    assert b.can_call_llm()
    b.record_llm_call()
    b.record_llm_call()
    assert not b.can_call_llm()


def test_budget_wall_clock() -> None:
    b = Budget(wall_clock_s=0.05)
    assert not b.wall_clock_exceeded()
    time.sleep(0.08)
    assert b.wall_clock_exceeded()


def test_budget_tool_rounds() -> None:
    b = Budget(max_tool_rounds=1)
    assert b.can_tool_round()
    b.record_tool_round()
    assert not b.can_tool_round()


def test_token_budget() -> None:
    b = Budget(token_budget=10)
    assert not b.token_budget_exceeded()
    b.consume_tokens(10)
    assert b.token_budget_exceeded()
