from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import app


def test_document_import_rejects_oversized_upload(monkeypatch) -> None:
    monkeypatch.setattr("backend.api.routes.documents.MAX_DOCUMENT_UPLOAD_BYTES", 4)
    monkeypatch.setattr("backend.api.routes.documents.UPLOAD_READ_CHUNK_BYTES", 2)
    client = TestClient(app)

    response = client.post(
        "/v1/documents/import",
        files={"file": ("too-large.txt", b"12345", "text/plain")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "document.upload_too_large"
