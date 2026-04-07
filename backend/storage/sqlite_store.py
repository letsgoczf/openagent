from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.storage.schema import apply_schema


class SQLiteStore:
    """SQLite persistence for documents, chunks (with FTS5), page_stats, trace_event."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        apply_schema(self._conn)

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def insert_document(
        self,
        doc_id: str,
        file_path: str,
        file_name: str,
        file_type: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO document (doc_id, file_path, file_name, file_type)
            VALUES (?, ?, ?, ?)
            """,
            (doc_id, file_path, file_name, file_type),
        )
        self._conn.commit()

    def insert_document_version(
        self,
        version_id: str,
        doc_id: str,
        content_hash: str,
        extraction_version: str,
        tokenizer_id: str,
        status: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO document_version (
                version_id, doc_id, content_hash, extraction_version, tokenizer_id, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (version_id, doc_id, content_hash, extraction_version, tokenizer_id, status),
        )
        self._conn.commit()

    def update_document_version_status(self, version_id: str, *, status: str) -> None:
        self._conn.execute(
            """
            UPDATE document_version
            SET status = ?
            WHERE version_id = ?
            """,
            (status, version_id),
        )
        self._conn.commit()

    def insert_chunk(
        self,
        chunk_id: str,
        version_id: str,
        origin_type: str,
        chunk_index: int,
        chunk_text: str,
        source_span: dict[str, Any],
        evidence_entry_tokens_v1: int | None = None,
        evidence_snippet_text_v1: str | None = None,
        page_number: int | None = None,
        slide_number: int | None = None,
        table_id: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO chunk (
                chunk_id, version_id, origin_type, chunk_index, chunk_text,
                source_span_json, evidence_entry_tokens_v1, evidence_snippet_text_v1,
                page_number, slide_number, table_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                version_id,
                origin_type,
                chunk_index,
                chunk_text,
                json.dumps(source_span, ensure_ascii=False),
                evidence_entry_tokens_v1,
                evidence_snippet_text_v1,
                page_number,
                slide_number,
                table_id,
            ),
        )
        self._conn.commit()

    def get_chunk_by_id(self, chunk_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM chunk WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["source_span"] = json.loads(d.pop("source_span_json"))
        return d

    def query_fts5(
        self,
        query: str,
        *,
        limit: int = 10,
        version_ids: list[str] | None = None,
        origin_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Keyword search over chunk_text; bm25 score (lower is better). Optional version / origin filter."""
        cond_version = ""
        cond_origin = ""
        extra_args: list[Any] = []
        if version_ids:
            placeholders = ",".join("?" * len(version_ids))
            cond_version = f" AND c.version_id IN ({placeholders})"
            extra_args.extend(version_ids)
        if origin_types:
            ph = ",".join("?" * len(origin_types))
            cond_origin = f" AND c.origin_type IN ({ph})"
            extra_args.extend(origin_types)

        sql = f"""
            SELECT c.chunk_id, bm25(chunk_fts) AS score
            FROM chunk_fts
            JOIN chunk c ON c.rowid = chunk_fts.rowid
            WHERE chunk_fts MATCH ?{cond_version}{cond_origin}
            ORDER BY score
            LIMIT ?
        """
        cur = self._conn.execute(sql, (query, *extra_args, limit))
        return [{"chunk_id": r["chunk_id"], "score": r["score"]} for r in cur.fetchall()]

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Return chunk_id -> row dicts (with ``source_span`` parsed)."""
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" * len(chunk_ids))
        rows = self._conn.execute(
            f"SELECT * FROM chunk WHERE chunk_id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            d = dict(row)
            d["source_span"] = json.loads(d.pop("source_span_json"))
            out[d["chunk_id"]] = d
        return out

    def update_chunk_evidence_cache(
        self,
        chunk_id: str,
        *,
        evidence_entry_tokens_v1: int,
        evidence_snippet_text_v1: str,
    ) -> None:
        self._conn.execute(
            """
            UPDATE chunk SET evidence_entry_tokens_v1 = ?, evidence_snippet_text_v1 = ?
            WHERE chunk_id = ?
            """,
            (evidence_entry_tokens_v1, evidence_snippet_text_v1, chunk_id),
        )
        self._conn.commit()

    def insert_page_stats(
        self,
        version_id: str,
        unit_type: str,
        unit_number: int,
        effective_text_tokens: int,
        has_text: bool,
        table_count: int = 0,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO page_stats (
                version_id, unit_type, unit_number,
                effective_text_tokens, has_text, table_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(version_id, unit_type, unit_number) DO UPDATE SET
                effective_text_tokens = excluded.effective_text_tokens,
                has_text = excluded.has_text,
                table_count = excluded.table_count
            """,
            (
                version_id,
                unit_type,
                unit_number,
                effective_text_tokens,
                1 if has_text else 0,
                table_count,
            ),
        )
        self._conn.commit()

    def insert_trace_event(
        self,
        event_id: str,
        run_id: str,
        sequence_num: int,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO trace_event (event_id, run_id, sequence_num, event_type, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event_id,
                run_id,
                sequence_num,
                event_type,
                json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            ),
        )
        self._conn.commit()

    def get_trace_events(
        self,
        run_id: str,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch ordered trace events for a run_id (for `/v1/traces/{run_id}`)."""
        sql = """
            SELECT event_id, sequence_num, event_type, payload_json, created_at
            FROM trace_event
            WHERE run_id = ?
            ORDER BY sequence_num ASC
        """
        args: list[Any] = [run_id]
        if limit is not None and limit > 0:
            sql += " LIMIT ?"
            args.append(limit)
        cur = self._conn.execute(sql, args)
        out: list[dict[str, Any]] = []
        for row in cur.fetchall():
            payload_raw = row["payload_json"]
            payload: dict[str, Any] | None = None
            if payload_raw is not None:
                payload = json.loads(payload_raw)
            out.append(
                {
                    "event_id": row["event_id"],
                    "sequence_num": row["sequence_num"],
                    "event_type": row["event_type"],
                    "payload": payload,
                    "created_at": row["created_at"],
                }
            )
        return out

    def list_document_summaries(self) -> list[dict[str, Any]]:
        """
        文档列表：每条为最新 ``document_version``（按 rowid 最大）与 ``document`` 元数据。
        """
        sql = """
            SELECT
                d.doc_id,
                d.file_name,
                d.file_type,
                d.created_at AS doc_created_at,
                v.version_id,
                v.status AS version_status,
                v.content_hash
            FROM document d
            LEFT JOIN document_version v ON v.version_id = (
                SELECT version_id FROM document_version
                WHERE doc_id = d.doc_id
                ORDER BY rowid DESC
                LIMIT 1
            )
            ORDER BY d.created_at DESC
        """
        cur = self._conn.execute(sql)
        return [dict(row) for row in cur.fetchall()]

    def get_document_summary(self, doc_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT doc_id, file_name, file_type, created_at
            FROM document
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_version_ids_by_doc_id(self, doc_id: str) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT version_id
            FROM document_version
            WHERE doc_id = ?
            ORDER BY rowid ASC
            """,
            (doc_id,),
        ).fetchall()
        return [str(r["version_id"]) for r in rows]

    def delete_document(self, doc_id: str) -> bool:
        """
        删除 document 及其关联版本/chunk/page_stats（依赖 FK CASCADE）。
        返回是否实际删除了记录。
        """
        cur = self._conn.execute("DELETE FROM document WHERE doc_id = ?", (doc_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def get_last_trace_event(
        self,
        run_id: str,
        *,
        event_types: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Get latest trace event (by sequence_num) optionally filtered by event_types."""
        if event_types:
            ph = ",".join("?" * len(event_types))
            sql = f"""
                SELECT event_id, sequence_num, event_type, payload_json, created_at
                FROM trace_event
                WHERE run_id = ? AND event_type IN ({ph})
                ORDER BY sequence_num DESC
                LIMIT 1
            """
            args: list[Any] = [run_id, *event_types]
        else:
            sql = """
                SELECT event_id, sequence_num, event_type, payload_json, created_at
                FROM trace_event
                WHERE run_id = ?
                ORDER BY sequence_num DESC
                LIMIT 1
            """
            args = [run_id]

        row = self._conn.execute(sql, args).fetchone()
        if row is None:
            return None
        payload_raw = row["payload_json"]
        payload: dict[str, Any] | None = None
        if payload_raw is not None:
            payload = json.loads(payload_raw)
        return {
            "event_id": row["event_id"],
            "sequence_num": row["sequence_num"],
            "event_type": row["event_type"],
            "payload": payload,
            "created_at": row["created_at"],
        }
