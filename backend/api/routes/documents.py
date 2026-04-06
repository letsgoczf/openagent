from __future__ import annotations

import hashlib
import io
import threading
import uuid
from pathlib import Path
from typing import Any

import pdfplumber
from fastapi import APIRouter, File, UploadFile

from backend.config_loader import OpenAgentSettings, load_config
from backend.api.errors import ApiException
from backend.kernel.trace import TraceWriter
from backend.models.embeddings import embed_text
from backend.models.factory import create_tokenizer_service
from backend.storage.factory import build_qdrant_client
from backend.storage.qdrant_store import QdrantStore
from backend.storage.sqlite_store import SQLiteStore


router = APIRouter(prefix="/v1/documents", tags=["documents"])


def _resolve_embedding_dim(cfg: OpenAgentSettings) -> int:
    dim = cfg.models.embedding.vector_dimensions
    if dim is not None:
        return dim
    # 兜底：探测 embedding 维度（会发起一次 embedding 请求）
    return len(embed_text("ping", settings=cfg))


def _extract_pdf_pages(file_bytes: bytes) -> list[str]:
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for p in pdf.pages:
            txt = p.extract_text() or ""
            pages.append(txt)
    return pages


def _run_document_import_job(
    job_id: str,
    file_bytes: bytes,
    filename: str,
    file_type: str,
) -> None:
    cfg = load_config()
    sqlite = SQLiteStore(cfg.storage.sqlite_path)

    dim = _resolve_embedding_dim(cfg)
    qclient = build_qdrant_client(cfg.storage.qdrant)
    qdrant = QdrantStore(cfg.storage.qdrant.collection_name, vector_size=dim, client=qclient)

    trace = TraceWriter(sqlite, job_id)
    tokenizer = create_tokenizer_service(cfg)

    doc_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    extraction_version = "v1"

    try:
        trace.emit("job_started", {"filename": filename, "file_type": file_type})

        # 先写入 document/document_version，后续 chunk 外键依赖 document_version
        sqlite.insert_document(
            doc_id=doc_id,
            file_path=str(Path("uploads") / filename),
            file_name=filename,
            file_type=file_type,
        )
        sqlite.insert_document_version(
            version_id=version_id,
            doc_id=doc_id,
            content_hash=content_hash,
            extraction_version=extraction_version,
            tokenizer_id=tokenizer.tokenizer_id,
            status="processing",
        )

        pages = _extract_pdf_pages(file_bytes)
        total_pages = len(pages)

        processed_chunks = 0
        for page_index, page_text in enumerate(pages, start=1):
            page_text = (page_text or "").strip()
            if not page_text:
                trace.emit(
                    "job_progress",
                    {
                        "page": page_index,
                        "total_pages": total_pages,
                        "processed_chunks": processed_chunks,
                    },
                )
                continue

            chunk_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"openagent:chunk:{version_id}:p{page_index}")
            )
            chunk_index = page_index - 1
            origin_type = "text"
            source_span: dict[str, Any] = {"page_number": page_index}

            sqlite.insert_chunk(
                chunk_id=chunk_id,
                version_id=version_id,
                origin_type=origin_type,
                chunk_index=chunk_index,
                chunk_text=page_text,
                source_span=source_span,
                evidence_entry_tokens_v1=None,
                evidence_snippet_text_v1=None,
                page_number=page_index,
                slide_number=None,
                table_id=None,
            )

            vec = embed_text(page_text, settings=cfg)
            qdrant.upsert_embedding(
                vec,
                chunk_id=chunk_id,
                version_id=version_id,
                origin_type=origin_type,
                unit_type="page",
                unit_number=page_index,
            )

            processed_chunks += 1
            trace.emit(
                "job_progress",
                {
                    "page": page_index,
                    "total_pages": total_pages,
                    "processed_chunks": processed_chunks,
                },
            )

        sqlite.update_document_version_status(version_id, status="completed")
        trace.emit("job_completed", {"doc_id": doc_id, "version_id": version_id})
    except Exception as e:  # noqa: BLE001
        trace.emit("job_failed", {"error": str(e)})
        try:
            sqlite.update_document_version_status(version_id, status="failed")
        except Exception:  # noqa: BLE001
            pass
    finally:
        qdrant.close()
        sqlite.close()


@router.post("/import", response_model=dict)
async def import_document(file: UploadFile = File(...)) -> dict[str, Any]:
    file_bytes = await file.read()
    filename = file.filename or "upload.pdf"
    file_type = file.content_type or "application/pdf"

    if not filename.lower().endswith(".pdf") and "pdf" not in file_type.lower():
        raise ApiException(code="document.unsupported_type", message="only PDF supported in P5")

    job_id = str(uuid.uuid4())
    t = threading.Thread(
        target=_run_document_import_job,
        args=(job_id, file_bytes, filename, file_type),
        daemon=True,
    )
    t.start()
    return {"job_id": job_id, "status": "queued"}


@router.get("")
async def list_documents() -> list[dict[str, Any]]:
    """列出已导入文档及当前最新版本状态。"""
    cfg = load_config()
    sqlite = SQLiteStore(cfg.storage.sqlite_path)
    try:
        return sqlite.list_document_summaries()
    finally:
        sqlite.close()

