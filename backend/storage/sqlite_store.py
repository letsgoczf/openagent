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

    def append_chat_session_turn(
        self,
        session_id: str,
        run_id: str | None,
        role: str,
        content: str,
        token_estimate: int | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO chat_session_turn (session_id, run_id, role, content, token_estimate)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, run_id, role, content, token_estimate),
        )
        self._conn.commit()

    def fetch_chat_session_turns_recent(self, session_id: str, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        cur = self._conn.execute(
            """
            SELECT id, session_id, run_id, role, content, token_estimate, created_at
            FROM chat_session_turn
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        )
        rows = [dict(r) for r in cur.fetchall()]
        rows.reverse()
        return rows

    def fetch_chat_session_turns_after(
        self, session_id: str, after_id: int
    ) -> list[dict[str, Any]]:
        """按 id 升序返回 ``id > after_id`` 的会话行（Phase B 摘要后的 verbatim 窗口）。"""
        cur = self._conn.execute(
            """
            SELECT id, session_id, run_id, role, content, token_estimate, created_at
            FROM chat_session_turn
            WHERE session_id = ? AND id > ?
            ORDER BY id ASC
            """,
            (session_id, after_id),
        )
        return [dict(r) for r in cur.fetchall()]

    def count_chat_session_turns(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM chat_session_turn WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["c"]) if row else 0

    def get_chat_session_summary(self, session_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT session_id, summary_text, covers_until_id, updated_at
            FROM chat_session_summary
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def insert_memory_fragment(
        self,
        fragment_id: str,
        session_id: str,
        run_id: str | None,
        fragment_type: str,
        text: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO memory_fragment (fragment_id, session_id, run_id, fragment_type, text)
            VALUES (?, ?, ?, ?, ?)
            """,
            (fragment_id, session_id, run_id, fragment_type, text),
        )
        self._conn.commit()

    def get_memory_fragment(self, fragment_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM memory_fragment WHERE fragment_id = ?",
            (fragment_id,),
        ).fetchone()
        return dict(row) if row else None

    def upsert_chat_session_summary(
        self,
        session_id: str,
        summary_text: str,
        covers_until_id: int,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO chat_session_summary (session_id, summary_text, covers_until_id)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                summary_text = excluded.summary_text,
                covers_until_id = excluded.covers_until_id,
                updated_at = datetime('now')
            """,
            (session_id, summary_text, covers_until_id),
        )
        self._conn.commit()

    # --- 前端 Chat UI 会话（整会话 JSON 快照，与 localStorage 结构对齐）---

    def get_ui_chat_state(self) -> tuple[str | None, list[dict[str, Any]]]:
        """返回 (active_session_id 或 None, sessions 列表，结构与前端 ChatSessionPersisted 一致)。"""
        row = self._conn.execute(
            "SELECT value FROM ui_preferences WHERE key = ?",
            ("active_chat_session_id",),
        ).fetchone()
        active_raw = (row["value"] if row else "") or ""
        active = active_raw.strip() or None
        cur = self._conn.execute(
            """
            SELECT session_id, title, updated_at_ms, payload_json
            FROM ui_chat_session
            ORDER BY updated_at_ms DESC
            """
        )
        sessions: list[dict[str, Any]] = []
        for r in cur.fetchall():
            try:
                payload = json.loads(r["payload_json"] or "{}")
            except json.JSONDecodeError:
                payload = {}
            sessions.append(
                {
                    "id": r["session_id"],
                    "title": r["title"] or "新会话",
                    "updatedAt": int(r["updated_at_ms"] or 0),
                    "messages": payload.get("messages") or [],
                    "lastEvidenceEntries": payload.get("lastEvidenceEntries") or [],
                    "lastCitations": payload.get("lastCitations") or [],
                }
            )
        return active, sessions

    def put_ui_chat_state(
        self,
        *,
        active_session_id: str | None,
        sessions: list[dict[str, Any]],
    ) -> None:
        """全量替换 UI 会话表（单用户；事务）。"""
        self._conn.execute("BEGIN")
        try:
            self._conn.execute("DELETE FROM ui_chat_session")
            for s in sessions:
                sid = str(s.get("id") or "").strip()
                if not sid:
                    continue
                title = str(s.get("title") or "新会话")
                updated = int(s.get("updatedAt") or 0)
                payload = {
                    "messages": s.get("messages") or [],
                    "lastEvidenceEntries": s.get("lastEvidenceEntries") or [],
                    "lastCitations": s.get("lastCitations") or [],
                }
                self._conn.execute(
                    """
                    INSERT INTO ui_chat_session (session_id, title, updated_at_ms, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (sid, title, updated, json.dumps(payload, ensure_ascii=False)),
                )
            self._conn.execute(
                """
                INSERT INTO ui_preferences (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("active_chat_session_id", active_session_id or ""),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
