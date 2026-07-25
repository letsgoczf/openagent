"""Regression: import worker setup failures must terminate the job as failed."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from backend.api.routes.documents import _run_document_import_job
from backend.api.routes.jobs import _latest_job_payload
from backend.config_loader import (
    EmbeddingConfig,
    GenerationConfig,
    ModelsConfig,
    OpenAgentSettings,
    StorageConfig,
    TokenizationConfig,
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
        storage=StorageConfig(sqlite_path=str(tmp_path / "import.db")),
        tokenization=TokenizationConfig(provider="hf"),
    )


def test_setup_failure_before_job_started_marks_job_failed(tmp_path) -> None:
    """Tokenizer/provider setup used to run outside try → job stuck as queued."""
    settings = _settings(tmp_path)
    job_id = str(uuid.uuid4())

    with patch("backend.api.routes.documents.load_config", return_value=settings):
        _run_document_import_job(
            job_id,
            b"plain text document body",
            "note.txt",
            "text/plain",
        )

    store = SQLiteStore(settings.storage.sqlite_path)
    try:
        event_type, payload = _latest_job_payload(store, job_id)
        assert event_type == "job_failed"
        assert payload is not None
        assert "not implemented" in str(payload.get("error", "")).lower()
    finally:
        store.close()


def test_embedding_probe_failure_marks_job_failed(tmp_path) -> None:
    settings = _settings(tmp_path)
    settings.tokenization = TokenizationConfig(provider="auto")
    settings.models.embedding.vector_dimensions = None
    job_id = str(uuid.uuid4())

    with (
        patch("backend.api.routes.documents.load_config", return_value=settings),
        patch(
            "backend.api.routes.documents._resolve_embedding_dim",
            side_effect=RuntimeError("embedding service unavailable"),
        ),
    ):
        _run_document_import_job(
            job_id,
            b"plain text document body",
            "note.txt",
            "text/plain",
        )

    store = SQLiteStore(settings.storage.sqlite_path)
    try:
        event_type, payload = _latest_job_payload(store, job_id)
        assert event_type == "job_failed"
        assert "embedding service unavailable" in str((payload or {}).get("error", ""))
    finally:
        store.close()
