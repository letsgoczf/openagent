from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


class Blackboard:
    """Append-only 事件流 + 按命名空间分段；供 tool loop / 多阶段共享快照。"""

    def __init__(self) -> None:
        self._stream: list[dict[str, Any]] = []
        self._by_ns: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def append(self, namespace: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        ev: dict[str, Any] = {
            "t": time.time(),
            "namespace": namespace,
            "type": event_type,
            "payload": payload or {},
        }
        self._stream.append(ev)
        self._by_ns[namespace].append(ev)

    @property
    def stream(self) -> list[dict[str, Any]]:
        return list(self._stream)

    def snapshot(self) -> dict[str, Any]:
        return {
            "event_count": len(self._stream),
            "namespaces": {k: len(v) for k, v in self._by_ns.items()},
            "last": self._stream[-1] if self._stream else None,
        }
