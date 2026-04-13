"""内置工具：web_search 等对 DuckDuckGo 响应的解析。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from backend.registry.builtin_tools import read_skill_reference_file, web_search


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


def test_read_skill_reference_ok(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    pkg = root / "demo-skill"
    (pkg / "references").mkdir(parents=True)
    (pkg / "references" / "note.md").write_text("hello", encoding="utf-8")
    out = read_skill_reference_file(
        "demo-skill",
        "references/note.md",
        skills_root=root,
    )
    assert out["ok"] is True
    assert out["content"] == "hello"


def test_read_skill_reference_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    pkg = root / "demo-skill"
    (pkg / "references").mkdir(parents=True)
    (pkg / "references" / "x.md").write_text("x", encoding="utf-8")
    out = read_skill_reference_file(
        "demo-skill",
        "references/../../etc/passwd",
        skills_root=root,
    )
    assert out["ok"] is False


def test_read_skill_reference_rejects_scripts(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    (root / "demo-skill").mkdir(parents=True)
    out = read_skill_reference_file(
        "demo-skill",
        "scripts/run.sh",
        skills_root=root,
    )
    assert out["ok"] is False


@patch("backend.registry.builtin_tools.urlopen")
def test_web_search_network_error(mock_urlopen) -> None:
    mock_urlopen.side_effect = OSError("boom")
    out = web_search("x")
    assert out["ok"] is False
    assert "results" in out
