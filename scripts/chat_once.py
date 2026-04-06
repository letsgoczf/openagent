#!/usr/bin/env python3
"""P4 端到端：query → 检索 → 组装 prompt → LLM → citations（需配置 LLM 与可选 Qdrant/SQLite 数据）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许自源码根目录运行：python scripts/chat_once.py
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.config_loader import resolve_repo_relative_path
from backend.kernel.budget import Budget
from backend.kernel.engine import KernelEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAgent single-shot chat (P4)")
    parser.add_argument("--query", "-q", required=True, help="User query")
    parser.add_argument(
        "--constitution",
        type=Path,
        default=None,
        help="覆盖 openagent.yaml 的 constitution_path（相对路径相对于仓库根）",
    )
    parser.add_argument("--max-llm-calls", type=int, default=8)
    parser.add_argument("--wall-clock", type=float, default=120.0, help="Seconds")
    parser.add_argument("--max-tool-rounds", type=int, default=4)
    parser.add_argument(
        "--stream",
        action="store_true",
        help="流式输出 thinking（若模型支持）与正文；Citations 在文末",
    )
    args = parser.parse_args()

    cpath: Path | None = None
    if args.constitution is not None:
        cpath = resolve_repo_relative_path(str(args.constitution))
    eng = KernelEngine(constitution_path=cpath)
    bud = Budget(
        max_llm_calls=args.max_llm_calls,
        wall_clock_s=args.wall_clock,
        max_tool_rounds=args.max_tool_rounds,
    )
    stream_state = {"in_thinking": False}
    writer = None
    if args.stream:

        def stream_sink(kind: str, text: str) -> None:
            if kind == "thinking":
                if not stream_state["in_thinking"]:
                    print("\n--- Thinking ---\n", end="", flush=True)
                    stream_state["in_thinking"] = True
                print(text, end="", flush=True)
            elif kind == "content":
                if stream_state["in_thinking"]:
                    print("\n--- /Thinking ---\n", end="", flush=True)
                    stream_state["in_thinking"] = False
                print(text, end="", flush=True)
            else:
                if stream_state["in_thinking"]:
                    print("\n--- /Thinking ---\n", end="", flush=True)
                    stream_state["in_thinking"] = False
                print(text, end="", flush=True)

        writer = stream_sink
    result = eng.run_chat(
        args.query,
        budget=bud,
        stream=args.stream,
        stream_writer=writer,
    )
    if args.stream and not result.degraded:
        if stream_state["in_thinking"]:
            print("\n--- /Thinking ---\n", end="", flush=True)
        print()
    else:
        print(result.answer)
    if result.degraded:
        print(f"\n[degraded] {result.degrade_reason}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
