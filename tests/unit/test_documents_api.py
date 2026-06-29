from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.api.routes.documents import delete_document
from backend.storage.sqlite_store import SQLiteStore


def test_delete_document_keeps_sqlite_when_vector_delete_fails(
    monkeypatch, tmp_path
) -> None:
    db_path = tmp_path / "docs.db"
    store = SQLiteStore(db_path)
    doc_id = "doc_delete"
    version_id = "ver_delete"
    store.insert_document(doc_id, "/tmp/x.pdf", "x.pdf", "pdf")
    store.insert_document_version(
        version_id, doc_id, "hash", "ext-v1", "tiktoken:test", "completed"
    )
    store.close()

    monkeypatch.setattr(
        "backend.api.routes.documents.load_config",
        lambda: SimpleNamespace(
            storage=SimpleNamespace(
                sqlite_path=str(db_path),
                qdrant=SimpleNamespace(collection_name="chunks"),
            )
        ),
    )
    monkeypatch.setattr("backend.api.routes.documents._resolve_embedding_dim", lambda _cfg: 4)
    monkeypatch.setattr("backend.api.routes.documents.build_qdrant_client", lambda _cfg: object())

    class FailingQdrant:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def delete_by_version_ids(self, _version_ids) -> None:
            raise RuntimeError("qdrant unavailable")

        def close(self) -> None:
            return None

    monkeypatch.setattr("backend.api.routes.documents.QdrantStore", FailingQdrant)

    try:
        asyncio.run(delete_document(doc_id))
    except RuntimeError as exc:
        assert str(exc) == "qdrant unavailable"
    else:
        raise AssertionError("delete_document should propagate vector deletion failure")

    verify = SQLiteStore(db_path)
    try:
        assert verify.get_document_summary(doc_id) is not None
        assert verify.list_version_ids_by_doc_id(doc_id) == [version_id]
    finally:
        verify.close()
