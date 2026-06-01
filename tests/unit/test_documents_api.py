from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.api.routes import documents


class _DummySqlite:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.closed = False

    def get_document_summary(self, doc_id: str) -> dict[str, str]:
        self.calls.append("get_document")
        return {"doc_id": doc_id}

    def list_version_ids_by_doc_id(self, doc_id: str) -> list[str]:
        self.calls.append("list_versions")
        return [f"{doc_id}-v1"]

    def delete_document(self, doc_id: str) -> bool:
        self.calls.append("sqlite_delete")
        return True

    def close(self) -> None:
        self.closed = True


class _DummyQdrant:
    def __init__(self, calls: list[str], *, fail: bool = False) -> None:
        self.calls = calls
        self.fail = fail
        self.closed = False

    def delete_by_version_ids(self, version_ids: list[str]) -> None:
        self.calls.append("qdrant_delete")
        assert version_ids == ["doc1-v1"]
        if self.fail:
            raise RuntimeError("qdrant unavailable")

    def close(self) -> None:
        self.closed = True


def _patch_delete_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sqlite: _DummySqlite,
    qdrant: _DummyQdrant,
) -> None:
    cfg = SimpleNamespace(
        storage=SimpleNamespace(
            sqlite_path=":memory:",
            qdrant=SimpleNamespace(collection_name="chunks"),
        )
    )
    monkeypatch.setattr(documents, "load_config", lambda: cfg)
    monkeypatch.setattr(documents, "_resolve_embedding_dim", lambda _cfg: 3)
    monkeypatch.setattr(documents, "build_qdrant_client", lambda _qcfg: object())
    monkeypatch.setattr(documents, "SQLiteStore", lambda _path: sqlite)
    monkeypatch.setattr(
        documents,
        "QdrantStore",
        lambda _name, vector_size, client, owns_client=False: qdrant,
    )


def test_delete_document_deletes_vectors_before_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    sqlite = _DummySqlite(calls)
    qdrant = _DummyQdrant(calls)
    _patch_delete_dependencies(monkeypatch, sqlite=sqlite, qdrant=qdrant)

    result = asyncio.run(documents.delete_document("doc1"))

    assert result == {"ok": True, "doc_id": "doc1", "deleted_versions": 1}
    assert calls == ["get_document", "list_versions", "qdrant_delete", "sqlite_delete"]
    assert sqlite.closed is True
    assert qdrant.closed is True


def test_delete_document_keeps_sqlite_when_vector_delete_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    sqlite = _DummySqlite(calls)
    qdrant = _DummyQdrant(calls, fail=True)
    _patch_delete_dependencies(monkeypatch, sqlite=sqlite, qdrant=qdrant)

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        asyncio.run(documents.delete_document("doc1"))

    assert calls == ["get_document", "list_versions", "qdrant_delete"]
    assert sqlite.closed is True
    assert qdrant.closed is True
