from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from backend.api.routes import documents
from backend.storage.sqlite_store import SQLiteStore


def test_delete_document_keeps_sqlite_rows_when_qdrant_delete_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "docs.db"
    store = SQLiteStore(db_path)
    doc_id, version_id, chunk_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    store.insert_document(doc_id, "/tmp/a.txt", "a.txt", "text/plain")
    store.insert_document_version(version_id, doc_id, "hash", "ev1", "tok", "completed")
    store.insert_chunk(chunk_id, version_id, "text", 0, "body", {"unit_index": 1})
    store.close()

    class FailingQdrantStore:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def delete_by_version_ids(self, version_ids: list[str]) -> None:
            assert version_ids == [version_id]
            raise RuntimeError("qdrant unavailable")

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        documents,
        "load_config",
        lambda: SimpleNamespace(
            storage=SimpleNamespace(
                sqlite_path=str(db_path),
                qdrant=SimpleNamespace(collection_name="chunks"),
            )
        ),
    )
    monkeypatch.setattr(documents, "_resolve_embedding_dim", lambda _cfg: 4)
    monkeypatch.setattr(documents, "build_qdrant_client", lambda _cfg: object())
    monkeypatch.setattr(documents, "QdrantStore", FailingQdrantStore)

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        asyncio.run(documents.delete_document(doc_id))

    after = SQLiteStore(db_path)
    try:
        assert after.get_document_summary(doc_id) is not None
        assert after.get_chunk_by_id(chunk_id) is not None
        assert after.list_version_ids_by_doc_id(doc_id) == [version_id]
    finally:
        after.close()
