"""WebSocket /ws：chat.start → chat.completed 序列（Kernel 打桩）。"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.rag.citation import Citation
from backend.runners.chat_runner import ChatRunResult


def _fake_run_chat(_self, query: str, **kwargs):
    return ChatRunResult(
        answer="stub answer",
        citations=[
            Citation(
                chunk_id="c1",
                version_id="v1",
                source_span={},
                location_summary="p.1",
            )
        ],
        evidence_entries=[],
        degraded=False,
        run_id="run-test-1",
        retrieval_state={"phase": "done"},
        degrade_reason=None,
    )


def _fake_run_chat_answer_object(_self, query: str, **kwargs):
    return ChatRunResult(
        answer={"content": "structured answer", "meta": {"q": query}},
        citations=[],
        evidence_entries=[],
        degraded=False,
        run_id="run-test-obj",
        retrieval_state={"phase": "done"},
        degrade_reason=None,
    )


def _fake_run_chat_capture_kwargs(captured: dict[str, object]):
    def _fake(_self, query: str, **kwargs):
        captured.update(kwargs)
        return ChatRunResult(
            answer=f"scoped {query}",
            citations=[],
            evidence_entries=[],
            degraded=False,
            run_id="run-test-scope",
            retrieval_state={"phase": "done"},
            degrade_reason=None,
        )

    return _fake


@patch("backend.api.ws_handler.KernelEngine.run_chat", _fake_run_chat)
def test_ws_chat_start_completes() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            {
                "type": "chat.start",
                "client_request_id": "req_e2e",
                "query": "hello",
                "stream": True,
            }
        )
        types: list[str] = []
        for _ in range(50):
            msg = ws.receive_json()
            types.append(msg.get("type", ""))
            if msg.get("type") == "chat.completed":
                assert msg.get("run_id") == "run-test-1"
                assert msg.get("answer") == "stub answer"
                break
        else:
            raise AssertionError("no chat.completed")

        assert "chat.delta" in types or "chat.completed" in types
        assert "chat.completed" in types


def test_ws_chat_start_passes_version_scope() -> None:
    captured: dict[str, object] = {}
    client = TestClient(app)
    with patch(
        "backend.api.ws_handler.KernelEngine.run_chat",
        _fake_run_chat_capture_kwargs(captured),
    ):
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "chat.start",
                    "client_request_id": "req_scope",
                    "query": "hello",
                    "version_scope": [" v1 ", "v2"],
                    "stream": False,
                }
            )
            for _ in range(50):
                msg = ws.receive_json()
                if msg.get("type") == "chat.completed":
                    assert msg.get("run_id") == "run-test-scope"
                    break
            else:
                raise AssertionError("no chat.completed")

    assert captured["version_scope"] == ["v1", "v2"]


@patch("backend.api.ws_handler.KernelEngine.run_chat", _fake_run_chat_answer_object)
def test_ws_chat_completed_answer_is_string() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            {
                "type": "chat.start",
                "client_request_id": "req_e2e2",
                "query": "hello",
                "stream": True,
            }
        )
        for _ in range(50):
            msg = ws.receive_json()
            if msg.get("type") == "chat.completed":
                ans = msg.get("answer")
                assert isinstance(ans, str)
                assert "structured answer" in ans
                break
        else:
            raise AssertionError("no chat.completed")
