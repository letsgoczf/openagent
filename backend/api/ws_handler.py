from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.kernel.budget import Budget
from backend.kernel.engine import KernelEngine


ws_router = APIRouter()

def _normalize_answer_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (int, float, bool)):
        return str(raw)
    # bytes-like
    if isinstance(raw, (bytes, bytearray)):
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return str(raw)
    # dict/list/other objects
    try:
        return json.dumps(raw, ensure_ascii=False)
    except TypeError:
        return str(raw)


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
        raw_sid = data.get("session_id")
        session_id = (
            str(raw_sid).strip()
            if raw_sid is not None and str(raw_sid).strip()
            else None
        )
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
                "citation_context": "chat.citation_context",
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

        cancel_ev = threading.Event()
        budget = Budget(cancel_event=cancel_ev)

        async def sender() -> None:
            while True:
                item = await q.get()
                await ws.send_json(item)
                if item.get("_done"):
                    return

        async def run_kernel() -> None:
            nonlocal delta_stream_state
            try:
                result = await asyncio.to_thread(
                    KernelEngine().run_chat,
                    query,
                    session_id=session_id,
                    budget=budget,
                    stream=stream,
                    stream_writer=stream_writer if stream else None,
                    trace_sink=trace_sink if stream else trace_sink,
                )
                delta_stream_state["run_id"] = result.run_id

                thinking = getattr(result, "thinking", None)
                payload_cm: dict[str, Any] = {
                    "type": "chat.completed",
                    "run_id": result.run_id,
                    "answer": _normalize_answer_text(getattr(result, "answer", "")),
                    "degraded": result.degraded,
                    "degrade_reason": result.degrade_reason,
                    "citations": [c.model_dump() for c in result.citations],
                    "evidence_entries": [
                        e.model_dump() for e in result.evidence_entries
                    ],
                    "retrieval_state": result.retrieval_state,
                    "_done": True,
                }
                if thinking:
                    payload_cm["thinking"] = thinking
                enqueue(payload_cm)
            except Exception as e:  # noqa: BLE001
                enqueue(
                    {
                        "type": "chat.failed",
                        "client_request_id": client_request_id,
                        "error": {"message": str(e)},
                        "_done": True,
                    }
                )

        async def listen_stop() -> None:
            try:
                while True:
                    raw = await ws.receive_text()
                    try:
                        pkt = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if pkt.get("type") != "chat.stop":
                        continue
                    if str(pkt.get("client_request_id") or "") != client_request_id:
                        continue
                    cancel_ev.set()
                    return
            except WebSocketDisconnect:
                cancel_ev.set()

        sender_task = asyncio.create_task(sender())
        kernel_task = asyncio.create_task(run_kernel())
        listen_task = asyncio.create_task(listen_stop())

        await asyncio.wait(
            {kernel_task, listen_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if listen_task.done() and not kernel_task.done():
            await kernel_task

        if not listen_task.done():
            listen_task.cancel()
            try:
                await listen_task
            except asyncio.CancelledError:
                pass

        await sender_task

