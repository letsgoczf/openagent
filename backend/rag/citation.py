from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.rag.evidence_builder import EvidenceEntry, build_location_summary
from backend.storage.sqlite_store import SQLiteStore


class Citation(BaseModel):
    chunk_id: str
    version_id: str
    source_span: dict[str, Any]
    location_summary: str


def build_citations(entries: list[EvidenceEntry], sqlite: SQLiteStore) -> list[Citation]:
    """每条 evidence 对应一条可溯源 citation（SQLite ``source_span``）。"""
    rows = sqlite.get_chunks_by_ids([e.chunk_id for e in entries])
    cites: list[Citation] = []
    for e in entries:
        row = rows.get(e.chunk_id)
        if row is None:
            continue
        cites.append(
            Citation(
                chunk_id=e.chunk_id,
                version_id=e.version_id,
                source_span=dict(row["source_span"]),
                location_summary=build_location_summary(row),
            )
        )
    return cites


def citation_chunk_ids_subset(evidence_chunk_ids: set[str], citation_chunk_ids: list[str]) -> bool:
    return set(citation_chunk_ids) <= evidence_chunk_ids
