"""
Phase D（最小实现）：从单次 run 的 trace 事件列表聚合记忆子系统可观测指标，供 eval / 离线分析。
不依赖 LLM judge；与 ``backend/eval_/README_DESIGN`` 中的 L0 类计数兼容扩展。
"""

from __future__ import annotations

from typing import Any


def summarize_memory_trace_events(
    events: list[tuple[str, dict[str, Any] | None]],
) -> dict[str, Any]:
    """
    ``events``：``(event_type, payload)`` 列表，通常来自 ``trace_event`` 表解析后的 payload。

    返回可 JSON 序列化的摘要 dict。
    """
    summary: dict[str, Any] = {
        "memory_read_count": 0,
        "memory_write_count": 0,
        "memory_consolidate_ok": 0,
        "memory_consolidate_skipped": 0,
        "memory_consolidate_failed": 0,
        "memory_fragments_write_total": 0,
        "memory_fragment_extract_llm_ok": 0,
        "memory_fragment_extract_llm_fail": 0,
        "memory_reconstruct_llm_ok": 0,
        "memory_reconstruct_llm_fail": 0,
        "rolling_summary_chars_max": 0,
        "reconstructed_fragment_chars_max": 0,
        "history_messages_max": 0,
    }

    for et, payload in events:
        p = payload or {}
        if et == "memory_read":
            summary["memory_read_count"] += 1
            summary["rolling_summary_chars_max"] = max(
                summary["rolling_summary_chars_max"],
                int(p.get("rolling_summary_chars") or 0),
            )
            summary["reconstructed_fragment_chars_max"] = max(
                summary["reconstructed_fragment_chars_max"],
                int(p.get("reconstructed_fragment_chars") or 0),
            )
            summary["history_messages_max"] = max(
                summary["history_messages_max"],
                int(p.get("history_messages") or 0),
            )
        elif et == "memory_write":
            summary["memory_write_count"] += 1
        elif et == "memory_consolidate":
            if p.get("ok") is True:
                summary["memory_consolidate_ok"] += 1
            elif p.get("skipped"):
                summary["memory_consolidate_skipped"] += 1
            else:
                summary["memory_consolidate_failed"] += 1
        elif et == "memory_fragments_write":
            summary["memory_fragments_write_total"] += int(p.get("count") or 0)
        elif et == "memory_fragment_extract_llm":
            if p.get("ok") is True:
                summary["memory_fragment_extract_llm_ok"] += 1
            else:
                summary["memory_fragment_extract_llm_fail"] += 1
        elif et == "memory_reconstruct_llm":
            if p.get("ok") is True:
                summary["memory_reconstruct_llm_ok"] += 1
            else:
                summary["memory_reconstruct_llm_fail"] += 1

    return summary
