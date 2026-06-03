from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from backend.api.routes import documents
from backend.storage.sqlite_store import SQLiteStore


class FailingQdrant:
    def __init__(self) -> None:
        self.deleted_version_ids: list[str] | None = None
        self.closed = False

    def delete_by_version_ids(self, version_ids: list[str]) -> None:
        self.deleted_version_ids = list(version_ids)
        raise RuntimeError("qdrant down")

    def close(self) -> None:
        self.closed = True


def test_delete_document_preserves_sqlite_when_qdrant_delete_fails(
    tmp_path, monkeypatch
) -> None:
    db = tmp_path / "docs.db"
    doc_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    store = SQLiteStore(db)
    store.insert_document(doc_id, "/tmp/doc.pdf", "doc.pdf", "pdf")
    store.insert_document_version(version_id, doc_id, "hash", "ext-v1", "tok", "completed")
    store.insert_chunk(
        chunk_id,
        version_id,
        "text",
        0,
        "important content",
        {"page_number": 1},
        page_number=1,
    )
    store.close()

    cfg = SimpleNamespace(
        storage=SimpleNamespace(
            sqlite_path=str(db),
            qdrant=SimpleNamespace(collection_name="chunks"),
        )
    )
    qdrant = FailingQdrant()
    monkeypatch.setattr(documents, "load_config", lambda: cfg)
    monkeypatch.setattr(documents, "_resolve_embedding_dim", lambda _cfg: 4)
    monkeypatch.setattr(documents, "build_qdrant_client", lambda _qdrant_cfg: object())
    monkeypatch.setattr(documents, "QdrantStore", lambda *args, **kwargs: qdrant)

    with pytest.raises(RuntimeError, match="qdrant down"):
        asyncio.run(documents.delete_document(doc_id))

    reopened = SQLiteStore(db)
    try:
        assert reopened.get_document_summary(doc_id) is not None
        assert reopened.get_chunk_by_id(chunk_id) is not None
        assert reopened.list_version_ids_by_doc_id(doc_id) == [version_id]
    finally:
        reopened.close()
    assert qdrant.deleted_version_ids == [version_id]
    assert qdrant.closed is True
