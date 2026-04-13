from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class Budget:
    """
    单次 run 的硬预算（LLM 调用、工具轮次、墙钟、可选 token 上限）。
    耗尽时调用方应降级或中止。
    """

    max_llm_calls: int = 8
    max_tool_rounds: int = 4
    wall_clock_s: float = 120.0
    token_budget: int | None = None
    cancel_event: threading.Event | None = None  # WebSocket chat.stop 协作式中断

    llm_calls_used: int = 0
    tool_rounds_used: int = 0
    tokens_used: int = 0
    _t0: float = field(default_factory=time.monotonic)

    def elapsed_s(self) -> float:
        return time.monotonic() - self._t0

    def wall_clock_exceeded(self) -> bool:
        return self.elapsed_s() >= self.wall_clock_s

    def can_call_llm(self) -> bool:
        if self.wall_clock_exceeded():
            return False
        return self.llm_calls_used < self.max_llm_calls

    def record_llm_call(self, *, estimated_output_tokens: int = 0) -> None:
        self.llm_calls_used += 1
        if estimated_output_tokens:
            self.consume_tokens(estimated_output_tokens)

    def can_tool_round(self) -> bool:
        if self.wall_clock_exceeded():
            return False
        return self.tool_rounds_used < self.max_tool_rounds

    def record_tool_round(self) -> None:
        self.tool_rounds_used += 1

    def consume_tokens(self, n: int) -> None:
        if n <= 0:
            return
        self.tokens_used += n
        if self.token_budget is not None and self.tokens_used > self.token_budget:
            pass

    def token_budget_exceeded(self) -> bool:
        if self.token_budget is None:
            return False
        return self.tokens_used >= self.token_budget

    def is_cancelled(self) -> bool:
        ev = self.cancel_event
        return ev is not None and ev.is_set()
