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
