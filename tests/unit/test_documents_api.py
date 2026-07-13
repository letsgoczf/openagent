from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.api.routes import documents


def test_delete_document_preserves_sqlite_when_vector_delete_fails(monkeypatch) -> None:
    class FakeSQLite:
        deleted = False

        def get_document_summary(self, doc_id: str) -> dict[str, str]:
            return {"doc_id": doc_id}

        def list_version_ids_by_doc_id(self, _doc_id: str) -> list[str]:
            return ["v1"]

        def delete_document(self, _doc_id: str) -> bool:
            self.deleted = True
            return True

        def close(self) -> None:
            return

    class FailingQdrant:
        def delete_by_version_ids(self, _version_ids: list[str]) -> None:
            raise RuntimeError("qdrant delete failed")

        def close(self) -> None:
            return

    fake_sqlite = FakeSQLite()
    monkeypatch.setattr(
        documents,
        "load_config",
        lambda: SimpleNamespace(
            storage=SimpleNamespace(sqlite_path=":memory:", qdrant=SimpleNamespace(collection_name="c")),
            models=SimpleNamespace(embedding=SimpleNamespace(vector_dimensions=4)),
        ),
    )
    monkeypatch.setattr(documents, "SQLiteStore", lambda _path: fake_sqlite)
    monkeypatch.setattr(documents, "build_qdrant_client", lambda _cfg: object())
    monkeypatch.setattr(documents, "QdrantStore", lambda *args, **kwargs: FailingQdrant())

    with pytest.raises(RuntimeError, match="qdrant delete failed"):
        asyncio.run(documents.delete_document("doc1"))

    assert fake_sqlite.deleted is False
