from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.kernel.budget import Budget
from backend.kernel.engine import KernelEngine


ws_router = APIRouter()


@ws_router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()

    # Note: 本实现只支持单次连接串行处理（收到 chat.start 后，直到 chat.completed 才接收下一条）。
    while True:
        try:
            msg_text = await ws.receive_text()
        except WebSocketDisconnect:
            return

        try:
            data = json.loads(msg_text)
        except json.JSONDecodeError:
            await ws.send_json({"type": "error", "message": "invalid json"})
            continue

        if data.get("type") != "chat.start":
            await ws.send_json({"type": "error", "message": "expected chat.start"})
            continue

        client_request_id = str(data.get("client_request_id") or "req_unknown")
        query = str(data.get("query") or "")
        stream = bool(data.get("stream", True))
        if not query:
            await ws.send_json(
                {
                    "type": "chat.failed",
                    "client_request_id": client_request_id,
                    "error": {"message": "query is required"},
                }
            )
            continue

        send_seq = 0
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        loop = asyncio.get_running_loop()

        def enqueue(payload: dict[str, Any]) -> None:
            nonlocal send_seq
            send_seq += 1
            payload["sequence"] = send_seq
            payload["client_request_id"] = client_request_id
            loop.call_soon_threadsafe(q.put_nowait, payload)

        def trace_sink(
            run_id: str,
            event_type: str,
            payload: dict[str, Any] | None,
            sequence_num: int,
            _event_id: str,
        ) -> None:
            if delta_stream_state["run_id"] is None:
                delta_stream_state["run_id"] = run_id
            # 将 trace_event 事件映射为 chat.* WS 事件。
            # 注意：这里的 mapping 是“最小可用 + P6 对齐”，便于前端做实时展示与断点恢复。
            mapping: dict[str, str] = {
                "run_started": "chat.run_started",
                "mode_selected": "chat.mode_selected",
                "retrieval_update": "chat.retrieval_update",
                "evidence_update": "chat.evidence_update",
                "tool_call_started": "chat.tool_call_started",
                "tool_call_finished": "chat.tool_call_finished",
                "tool_call_failed": "chat.tool_call_failed",
                "agent_spawned": "chat.agent_spawned",
                "agent_progress": "chat.agent_progress",
                "agent_completed": "chat.agent_completed",
                "agent_failed": "chat.agent_failed",
                "merge_started": "chat.merge_started",
            }

            ws_type = mapping.get(event_type)
            if ws_type:
                enqueue(
                    {
                        "type": ws_type,
                        "run_id": run_id,
                        "sequence_num": sequence_num,
                        "payload": payload or {},
                    }
                )

        # 让 chat.delta 也携带 run_id：runner 完成后我们会发 chat.completed（包含 run_id）。
        # 运行中 run_id 在 trace_sink 中可得；这里只对 delta 做序列流输出。
        delta_stream_state = {"run_id": None}

        def stream_writer(kind: str, text: str) -> None:
            # kind: thinking/content/citations
            rid = delta_stream_state["run_id"] or "pending"

            if kind == "thinking":
                enqueue(
                    {
                        "type": "chat.delta",
                        "run_id": rid,
                        "delta_kind": "thinking",
                        "delta": text,
                    }
                )
            elif kind == "citations":
                enqueue(
                    {
                        "type": "chat.delta",
                        "run_id": rid,
                        "delta_kind": "citations",
                        "delta": text,
                    }
                )
            else:
                enqueue(
                    {
                        "type": "chat.delta",
                        "run_id": rid,
                        "delta_kind": "content",
                        "delta": text,
                    }
                )

        async def sender() -> None:
            while True:
                item = await q.get()
                await ws.send_json(item)
                if item.get("_done"):
                    return

        sender_task = asyncio.create_task(sender())

        # 用线程跑同步 KernelEngine，避免阻塞事件循环
        async def run_kernel() -> None:
            nonlocal delta_stream_state
            try:
                budget = Budget()
                # KernelEngine 返回的 run_id 在 result 中；我们用它回填 delta 的 run_id
                # （trace_sink 会率先推 evidence 事件并带 run_id）
                result = await asyncio.to_thread(
                    KernelEngine().run_chat,
                    query,
                    budget=budget,
                    stream=stream,
                    stream_writer=stream_writer if stream else None,
                    trace_sink=trace_sink if stream else trace_sink,
                )
                delta_stream_state["run_id"] = result.run_id

                enqueue(
                    {
                        "type": "chat.completed",
                        "run_id": result.run_id,
                        "answer": result.answer,
                        "degraded": result.degraded,
                        "degrade_reason": result.degrade_reason,
                        "citations": [c.model_dump() for c in result.citations],
                        "evidence_entries": [
                            e.model_dump() for e in result.evidence_entries
                        ],
                        "retrieval_state": result.retrieval_state,
                        "_done": True,
                    }
                )
            except Exception as e:  # noqa: BLE001
                enqueue(
                    {
                        "type": "chat.failed",
                        "error": {"message": str(e)},
                        "_done": True,
                    }
                )

        await run_kernel()
        await sender_task

