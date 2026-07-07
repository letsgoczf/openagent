from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.api.routes.documents import delete_document


@patch("backend.api.routes.documents.QdrantStore")
@patch("backend.api.routes.documents.build_qdrant_client", return_value=MagicMock())
@patch("backend.api.routes.documents._resolve_embedding_dim", return_value=4)
@patch("backend.api.routes.documents.SQLiteStore")
@patch("backend.api.routes.documents.load_config")
def test_delete_document_preserves_sqlite_when_vector_delete_fails(
    mock_load_config,
    mock_sqlite_cls,
    _mock_dim,
    _mock_qclient,
    mock_qdrant_cls,
) -> None:
    cfg = SimpleNamespace(
        storage=SimpleNamespace(sqlite_path=":memory:", qdrant=SimpleNamespace(collection_name="c"))
    )
    mock_load_config.return_value = cfg

    sqlite = MagicMock()
    sqlite.get_document_summary.return_value = {"doc_id": "doc_1"}
    sqlite.list_version_ids_by_doc_id.return_value = ["ver_1"]
    mock_sqlite_cls.return_value = sqlite

    qdrant = MagicMock()
    qdrant.delete_by_version_ids.side_effect = RuntimeError("qdrant unavailable")
    mock_qdrant_cls.return_value = qdrant

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        asyncio.run(delete_document("doc_1"))

    qdrant.delete_by_version_ids.assert_called_once_with(["ver_1"])
    sqlite.delete_document.assert_not_called()
    qdrant.close.assert_called_once()
    sqlite.close.assert_called_once()
