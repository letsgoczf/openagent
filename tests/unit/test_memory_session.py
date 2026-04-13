from __future__ import annotations

import tempfile
from pathlib import Path

from backend.config_loader import MemoryConfig
from backend.kernel.budget import Budget
from backend.memory.consolidation import run_consolidation_if_needed
from backend.memory.session_store import (
    fetch_history_messages,
    persist_user_assistant_turns,
    trim_history_messages_to_budget,
)
from backend.models.base import ChatResponse
from backend.models.tokenizer import TokenizerService
from backend.runners.composer import (
    build_messages,
    strip_citations_footer_from_answer,
)
from backend.storage.sqlite_store import SQLiteStore


def test_strip_citations_footer_from_answer() -> None:
    raw = "Hello\n---\nCitations:\n  [1] chunk_id=x"
    assert strip_citations_footer_from_answer(raw) == "Hello"


def test_build_messages_with_rolling_summary() -> None:
    msgs = build_messages(
        constitution="C",
        query="Q",
        evidence_block="(none)",
        rolling_summary="User asked about X; we agreed on Y.",
    )
    assert "[Earlier conversation summary" in msgs[0]["content"]
    assert "User asked about X" in msgs[0]["content"]


def test_build_messages_with_conversation_history() -> None:
    msgs = build_messages(
        constitution="C",
        query="Q2",
        evidence_block="(none)",
        conversation_history=[
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ],
    )
    assert msgs[0]["role"] == "system"
    assert "[Memory]" in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "Q1"}
    assert msgs[2] == {"role": "assistant", "content": "A1"}
    assert msgs[3]["role"] == "user"
    assert "USER QUESTION:\nQ2" in msgs[3]["content"]


def test_fetch_and_persist_roundtrip() -> None:
    tok = TokenizerService(model_id="gpt-4o-mini")
    cfg = MemoryConfig(
        enabled=True,
        session_max_turns=8,
        session_max_history_tokens=8000,
    )
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        store = SQLiteStore(db)
        sid = "sess_test"
        persist_user_assistant_turns(
            store, cfg, sid, "run_1", "hi", "hello back", tok
        )
        rows = store.fetch_chat_session_turns_recent(sid, 10)
        assert len(rows) == 2
        assert rows[0]["role"] == "user" and rows[0]["content"] == "hi"
        assert rows[1]["role"] == "assistant"
        hist, summary = fetch_history_messages(store, cfg, sid, tok)
        assert summary is None
        assert len(hist) == 2
        store.close()


def test_fetch_with_summary_and_verbatim_tail() -> None:
    tok = TokenizerService(model_id="gpt-4o-mini")
    cfg = MemoryConfig(
        enabled=True,
        consolidation_enabled=True,
        session_max_turns=32,
        session_max_history_tokens=8000,
    )
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        store = SQLiteStore(db)
        sid = "s1"
        store.upsert_chat_session_summary(sid, "Old topics A,B.", covers_until_id=0)
        # id>0: these two rows visible as verbatim when covers=0 — actually covers=0 means id>0, so id must be >0
        store.append_chat_session_turn(sid, "r1", "user", "u1", 1)
        store.append_chat_session_turn(sid, "r1", "assistant", "a1", 1)
        row = store.fetch_chat_session_turns_after(sid, 0)
        assert len(row) == 2
        first_id = row[0]["id"]
        store.upsert_chat_session_summary(sid, "Summary", covers_until_id=first_id)
        tail = store.fetch_chat_session_turns_after(sid, first_id)
        assert len(tail) == 1
        assert tail[0]["role"] == "assistant"
        msgs, summ = fetch_history_messages(store, cfg, sid, tok)
        assert summ and "Summary" in summ
        assert len(msgs) == 1
        store.close()


class _FakeLLM:
    def chat(self, messages, stream=False, max_tokens=None, tools=None):
        return ChatResponse(content="folded summary line")


def test_consolidation_writes_summary_row() -> None:
    tok = TokenizerService(model_id="gpt-4o-mini")
    cfg = MemoryConfig(
        enabled=True,
        consolidation_enabled=True,
        consolidate_after_turns=2,
        keep_recent_rounds=2,
        consolidation_max_output_tokens=256,
    )
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        store = SQLiteStore(db)
        sid = "sx"
        budget = Budget(max_llm_calls=4)
        for i in range(3):
            store.append_chat_session_turn(sid, f"r{i}", "user", f"q{i}", 1)
            store.append_chat_session_turn(sid, f"r{i}", "assistant", f"a{i}", 1)
        assert store.count_chat_session_turns(sid) == 6
        run_consolidation_if_needed(
            store=store,
            cfg=cfg,
            session_id=sid,
            budget=budget,
            llm=_FakeLLM(),  # type: ignore[arg-type]
            tokenizer=tok,
            trace=None,
        )
        row = store.get_chat_session_summary(sid)
        assert row is not None
        assert "folded summary" in row["summary_text"]
        assert int(row["covers_until_id"]) > 0
        tail = store.fetch_chat_session_turns_after(sid, int(row["covers_until_id"]))
        assert len(tail) == 4
        store.close()


def test_trim_history_messages_to_budget_keeps_newest_suffix() -> None:
    tok = TokenizerService(model_id="gpt-4o-mini")
    old = "paragraph " * 2000
    messages = [
        {"role": "user", "content": old},
        {"role": "assistant", "content": "new"},
    ]
    trimmed = trim_history_messages_to_budget(messages, tok, max_tokens=24)
    assert len(trimmed) == 1
    assert trimmed[0]["content"] == "new"
