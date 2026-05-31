from __future__ import annotations

import uuid

import pytest

from backend.storage.qdrant_store import QdrantStore
from backend.storage.sqlite_store import SQLiteStore


@pytest.fixture
def sqlite_db(tmp_path):
    path = tmp_path / "t.db"
    store = SQLiteStore(path)
    yield store
    store.close()


def _seed_doc(store: SQLiteStore, text: str) -> tuple[str, str, str]:
    doc_id = str(uuid.uuid4())
    ver_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    store.insert_document(doc_id, "/tmp/x.pdf", "x.pdf", "pdf")
    store.insert_document_version(ver_id, doc_id, "hash1", "ext-v1", "tiktoken:test", "ready")
    store.insert_chunk(
        chunk_id,
        ver_id,
        "text",
        0,
        text,
        {"page_number": 1},
        page_number=1,
    )
    return doc_id, ver_id, chunk_id


def test_sqlite_insert_and_get_chunk(sqlite_db: SQLiteStore) -> None:
    _, ver_id, chunk_id = _seed_doc(sqlite_db, "hello persistent world")
    row = sqlite_db.get_chunk_by_id(chunk_id)
    assert row is not None
    assert row["chunk_id"] == chunk_id
    assert row["version_id"] == ver_id
    assert "persistent" in row["chunk_text"]


def test_sqlite_fts5_returns_chunk_id(sqlite_db: SQLiteStore) -> None:
    _, _, chunk_id = _seed_doc(sqlite_db, "alpha beta gamma uniqueword")
    hits = sqlite_db.query_fts5("uniqueword", limit=5)
    assert any(h["chunk_id"] == chunk_id for h in hits)


def test_list_document_summaries(sqlite_db: SQLiteStore) -> None:
    _seed_doc(sqlite_db, "doc body")
    rows = sqlite_db.list_document_summaries()
    assert len(rows) == 1
    assert rows[0]["file_name"] == "x.pdf"
    assert rows[0]["version_status"] == "ready"


def test_sqlite_delete_document_cascade(sqlite_db: SQLiteStore) -> None:
    doc_id, ver_id, chunk_id = _seed_doc(sqlite_db, "to be deleted")
    assert sqlite_db.get_chunk_by_id(chunk_id) is not None
    assert sqlite_db.get_document_summary(doc_id) is not None
    assert sqlite_db.list_version_ids_by_doc_id(doc_id) == [ver_id]

    deleted = sqlite_db.delete_document(doc_id)
    assert deleted is True
    assert sqlite_db.get_document_summary(doc_id) is None
    assert sqlite_db.list_version_ids_by_doc_id(doc_id) == []
    assert sqlite_db.get_chunk_by_id(chunk_id) is None


def test_qdrant_upsert_and_search() -> None:
    store = QdrantStore("test_chunks", vector_size=4, location=":memory:")
    store.ensure_collection()
    v = [0.0, 0.0, 0.0, 1.0]
    q = [0.0, 0.0, 0.0, 1.0]
    store.upsert_embedding(
        v,
        chunk_id="c1",
        version_id="v1",
        origin_type="text",
        unit_type="pdf_page",
        unit_number=1,
    )
    results = store.search(q, limit=3)
    assert len(results) >= 1
    top = max(results, key=lambda r: r["score"] or 0)
    assert top["chunk_id"] == "c1"

    filtered = store.search(q, limit=3, version_id="v1")
    assert all(r.get("version_id") == "v1" for r in filtered if r.get("chunk_id"))

    store.close()


def test_qdrant_version_filter_excludes() -> None:
    store = QdrantStore("t2", vector_size=3, location=":memory:")
    store.ensure_collection()
    vec = [1.0, 0.0, 0.0]
    store.upsert_embedding(
        vec,
        chunk_id="ca",
        version_id="v_a",
        origin_type="text",
        unit_type="pdf_page",
        unit_number=1,
    )
    out = store.search(vec, limit=5, version_id="other")
    assert not any(r.get("chunk_id") == "ca" for r in out)
    store.close()


def test_qdrant_delete_by_version_ids() -> None:
    store = QdrantStore("t3", vector_size=3, location=":memory:")
    store.ensure_collection()
    vec = [0.2, 0.3, 0.4]
    store.upsert_embedding(
        vec,
        chunk_id="c_keep",
        version_id="v_keep",
        origin_type="text",
        unit_type="page",
        unit_number=1,
    )
    store.upsert_embedding(
        vec,
        chunk_id="c_drop",
        version_id="v_drop",
        origin_type="text",
        unit_type="page",
        unit_number=1,
    )
    store.delete_by_version_ids(["v_drop"])
    out = store.search(vec, limit=10)
    ids = {r.get("chunk_id") for r in out}
    assert "c_drop" not in ids
    assert "c_keep" in ids
    store.close()


def test_qdrant_delete_memory_fragments_by_session_id() -> None:
    store = QdrantStore("mem", vector_size=3, location=":memory:")
    store.ensure_collection()
    vec = [0.0, 1.0, 0.0]
    store.upsert_memory_fragment(vec, fragment_id="f_drop", session_id="s_drop")
    store.upsert_memory_fragment(vec, fragment_id="f_keep", session_id="s_keep")

    store.delete_memory_fragments_by_session_id("s_drop")

    dropped = store.search_memory_fragments(vec, session_id="s_drop", limit=5)
    kept = store.search_memory_fragments(vec, session_id="s_keep", limit=5)
    assert not any(r.get("fragment_id") == "f_drop" for r in dropped)
    assert any(r.get("fragment_id") == "f_keep" for r in kept)
    store.close()


def test_ui_chat_state_roundtrip(sqlite_db: SQLiteStore) -> None:
    active, sessions = sqlite_db.get_ui_chat_state()
    assert active is None
    assert sessions == []
    sqlite_db.put_ui_chat_state(
        active_session_id="s_1",
        sessions=[
            {
                "id": "s_1",
                "title": "hi",
                "updatedAt": 42,
                "messages": [{"id": "m1", "role": "user", "content": "x"}],
                "lastEvidenceEntries": [],
                "lastCitations": [],
            }
        ],
    )
    active, rows = sqlite_db.get_ui_chat_state()
    assert active == "s_1"
    assert len(rows) == 1
    assert rows[0]["id"] == "s_1"
    assert rows[0]["title"] == "hi"
    assert rows[0]["updatedAt"] == 42
    assert rows[0]["messages"][0]["content"] == "x"


def test_clear_chat_session_memory_removes_only_target_session(
    sqlite_db: SQLiteStore,
) -> None:
    sqlite_db.append_chat_session_turn("s_drop", "r1", "user", "secret", 1)
    sqlite_db.append_chat_session_turn("s_drop", "r1", "assistant", "answer", 1)
    sqlite_db.upsert_chat_session_summary("s_drop", "secret summary", covers_until_id=1)
    sqlite_db.insert_memory_fragment("f_drop", "s_drop", "r1", "episodic", "secret")
    sqlite_db.append_chat_session_turn("s_keep", "r2", "user", "keep", 1)
    sqlite_db.insert_memory_fragment("f_keep", "s_keep", "r2", "episodic", "keep")

    deleted = sqlite_db.clear_chat_session_memory("s_drop")

    assert deleted == {"turns": 2, "summaries": 1, "fragments": 1}
    assert sqlite_db.fetch_chat_session_turns_recent("s_drop", 10) == []
    assert sqlite_db.get_chat_session_summary("s_drop") is None
    assert sqlite_db.get_memory_fragment("f_drop") is None
    assert len(sqlite_db.fetch_chat_session_turns_recent("s_keep", 10)) == 1
    assert sqlite_db.get_memory_fragment("f_keep") is not None
