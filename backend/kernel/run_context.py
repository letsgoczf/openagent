from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.kernel.budget import Budget


@dataclass
class RunContext:
    """单次 chat run 的标识、预算与可变状态（供 runner / trace 使用）。"""

    run_id: str
    session_id: str
    budget: Budget
    state: dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    degrade_reason: str | None = None

    def mark_degraded(self, reason: str) -> None:
        self.degraded = True
        self.degrade_reason = reason
