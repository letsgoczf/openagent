"""内置工具：web_search 等对 DuckDuckGo 响应的解析。"""

from __future__ import annotations

import json
from unittest.mock import patch

from backend.registry.builtin_tools import web_search


def test_web_search_empty_query() -> None:
    out = web_search("   ")
    assert out["ok"] is False


@patch("backend.registry.builtin_tools.urlopen")
def test_web_search_parses_abstract(mock_urlopen) -> None:
    payload = {
        "AbstractText": "Hello world summary",
        "AbstractURL": "https://example.com",
        "Heading": "Topic",
    }
    body = json.dumps(payload).encode()

    class _Resp:
        def read(self) -> bytes:
            return body

    class _CM:
        def __enter__(self) -> _Resp:
            return _Resp()

        def __exit__(self, *a: object) -> None:
            return None

    mock_urlopen.return_value = _CM()

    out = web_search("test query")
    assert out["ok"] is True
    assert out["query"] == "test query"
    assert len(out["results"]) >= 1
    assert "Hello world summary" in out["results"][0]["snippet"]


@patch("backend.registry.builtin_tools.urlopen")
def test_web_search_network_error(mock_urlopen) -> None:
    mock_urlopen.side_effect = OSError("boom")
    out = web_search("x")
    assert out["ok"] is False
    assert "results" in out
