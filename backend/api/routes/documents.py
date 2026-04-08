from __future__ import annotations

import hashlib
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, UploadFile

from backend.api.errors import ApiException
from backend.config_loader import OpenAgentSettings, load_config
from backend.kernel.trace import TraceWriter
from backend.ingestion.chunking import chunk_text_by_tokens
from backend.ingestion.document_extract import DocumentExtractionError, extract_document_pages
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

        try:
            pages = extract_document_pages(file_bytes, filename)
        except DocumentExtractionError as e:
            trace.emit("job_failed", {"error": str(e)})
            sqlite.update_document_version_status(version_id, status="failed")
            return
        if not pages:
            trace.emit("job_failed", {"error": "no extractable text in document"})
            sqlite.update_document_version_status(version_id, status="failed")
            return
        total_units = len(pages)

        processed_chunks = 0
        chunk_index = 0

        is_pdf = filename.lower().endswith(".pdf") or file_bytes.startswith(b"%PDF-")

        for unit_index, unit_text in enumerate(pages, start=1):
            unit_text = (unit_text or "").strip()
            # PDF：空页保留页码占位；非 PDF：空段直接跳过
            if not unit_text and not is_pdf:
                trace.emit(
                    "job_progress",
                    {
                        "page": unit_index,
                        "total_pages": total_units,
                        "processed_chunks": processed_chunks,
                    },
                )
                continue

            # 二次分段：按 token 预算切小块 + overlap
            sub_chunks = chunk_text_by_tokens(
                unit_text,
                tokenizer,
                max_chunk_tokens=800,
                overlap_tokens=80,
            )
            if not sub_chunks and unit_text:
                sub_chunks = [unit_text]

            for sub_i, chunk_text in enumerate(sub_chunks):
                chunk_text = (chunk_text or "").strip()
                if not chunk_text:
                    continue

                chunk_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"openagent:chunk:{version_id}:u{unit_index}:c{sub_i}",
                    )
                )
                origin_type = "text"
                source_span: dict[str, Any] = (
                    {"page_number": unit_index, "subchunk_index": sub_i}
                    if is_pdf
                    else {"unit_index": unit_index, "subchunk_index": sub_i}
                )

                sqlite.insert_chunk(
                    chunk_id=chunk_id,
                    version_id=version_id,
                    origin_type=origin_type,
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    source_span=source_span,
                    evidence_entry_tokens_v1=None,
                    evidence_snippet_text_v1=None,
                    page_number=(unit_index if is_pdf else None),
                    slide_number=None,
                    table_id=None,
                )

                vec = embed_text(chunk_text, settings=cfg)
                qdrant.upsert_embedding(
                    vec,
                    chunk_id=chunk_id,
                    version_id=version_id,
                    origin_type=origin_type,
                    unit_type=("page" if is_pdf else "unit"),
                    unit_number=unit_index,
                )

                processed_chunks += 1
                chunk_index += 1

            trace.emit(
                "job_progress",
                {
                    "page": unit_index,
                    "total_pages": total_units,
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
    filename = file.filename or "upload.bin"
    file_type = file.content_type or "application/octet-stream"

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


@router.delete("/{doc_id}", response_model=dict)
async def delete_document(doc_id: str) -> dict[str, Any]:
    cfg = load_config()
    sqlite = SQLiteStore(cfg.storage.sqlite_path)
    dim = _resolve_embedding_dim(cfg)
    qclient = build_qdrant_client(cfg.storage.qdrant)
    qdrant = QdrantStore(cfg.storage.qdrant.collection_name, vector_size=dim, client=qclient)
    try:
        doc = sqlite.get_document_summary(doc_id)
        if doc is None:
            raise ApiException(
                code="document.not_found",
                message="document not found",
                status_code=404,
                detail={"doc_id": doc_id},
            )
        version_ids = sqlite.list_version_ids_by_doc_id(doc_id)
        sqlite.delete_document(doc_id)
        qdrant.delete_by_version_ids(version_ids)
        return {"ok": True, "doc_id": doc_id, "deleted_versions": len(version_ids)}
    finally:
        qdrant.close()
        sqlite.close()

