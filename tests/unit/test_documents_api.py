from __future__ import annotations

import asyncio
import uuid

import pytest

from backend.api.errors import ApiException
from backend.api.routes import documents
from backend.config_loader import (
    EmbeddingConfig,
    GenerationConfig,
    ModelsConfig,
    OpenAgentSettings,
    StorageConfig,
)
from backend.storage.sqlite_store import SQLiteStore


def _settings(tmp_path) -> OpenAgentSettings:
    return OpenAgentSettings(
        models=ModelsConfig(
            generation=GenerationConfig(
                provider="ollama",
                model_id="tiny",
                base_url="http://127.0.0.1:11434",
            ),
            embedding=EmbeddingConfig(
                provider="ollama",
                model_id="nomic-embed-text",
                base_url="http://127.0.0.1:11434",
                vector_dimensions=4,
            ),
        ),
        storage=StorageConfig(sqlite_path=str(tmp_path / "documents.db")),
    )


def test_delete_document_keeps_sqlite_rows_when_vector_delete_fails(
    tmp_path, monkeypatch
) -> None:
    settings = _settings(tmp_path)
    store = SQLiteStore(settings.storage.sqlite_path)
    doc_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    store.insert_document(doc_id, "/tmp/a.pdf", "a.pdf", "application/pdf")
    store.insert_document_version(
        version_id,
        doc_id,
        "hash",
        "extract-v1",
        "tok",
        "completed",
    )
    store.close()

    class FailingQdrant:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def delete_by_version_ids(self, version_ids: list[str]) -> None:
            assert version_ids == [version_id]
            raise RuntimeError("qdrant unavailable")

        def close(self) -> None:
            pass

    monkeypatch.setattr(documents, "load_config", lambda: settings)
    monkeypatch.setattr(documents, "build_qdrant_client", lambda _cfg: object())
    monkeypatch.setattr(documents, "QdrantStore", FailingQdrant)

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        asyncio.run(documents.delete_document(doc_id))

    check = SQLiteStore(settings.storage.sqlite_path)
    try:
        assert check.get_document_summary(doc_id) is not None
        assert check.list_version_ids_by_doc_id(doc_id) == [version_id]
    finally:
        check.close()


def test_import_document_rejects_uploads_over_limit(monkeypatch) -> None:
    class FakeUpload:
        filename = "big.txt"
        content_type = "text/plain"

        def __init__(self) -> None:
            self._chunks = [b"abcd", b"ef"]

        async def read(self, _size: int = -1) -> bytes:
            if not self._chunks:
                return b""
            return self._chunks.pop(0)

    monkeypatch.setattr(documents, "MAX_DOCUMENT_UPLOAD_BYTES", 5)
    monkeypatch.setattr(documents, "DOCUMENT_UPLOAD_CHUNK_BYTES", 4)

    with pytest.raises(ApiException) as exc:
        asyncio.run(documents.import_document(FakeUpload()))  # type: ignore[arg-type]

    assert exc.value.status_code == 413
    assert exc.value.code == "document.upload_too_large"
