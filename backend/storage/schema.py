"""SQLite DDL: core tables + FTS5 on chunk_text + sync triggers."""

# Applied in order. FTS5 uses chunk.rowid per SQLite external-content pattern.
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS document (
    doc_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS document_version (
    version_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    tokenizer_id TEXT NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(doc_id, content_hash)
);

CREATE TABLE IF NOT EXISTS chunk (
    chunk_id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES document_version(version_id) ON DELETE CASCADE,
    origin_type TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    source_span_json TEXT NOT NULL,
    evidence_entry_tokens_v1 INTEGER,
    evidence_snippet_text_v1 TEXT,
    page_number INTEGER,
    slide_number INTEGER,
    table_id TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    chunk_text,
    content='chunk',
    content_rowid='rowid',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS chunk_ai AFTER INSERT ON chunk BEGIN
    INSERT INTO chunk_fts(rowid, chunk_text) VALUES (new.rowid, new.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS chunk_ad AFTER DELETE ON chunk BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, chunk_text) VALUES('delete', old.rowid, old.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS chunk_au AFTER UPDATE OF chunk_text ON chunk BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, chunk_text) VALUES('delete', old.rowid, old.chunk_text);
    INSERT INTO chunk_fts(rowid, chunk_text) VALUES (new.rowid, new.chunk_text);
END;

CREATE TABLE IF NOT EXISTS page_stats (
    version_id TEXT NOT NULL REFERENCES document_version(version_id) ON DELETE CASCADE,
    unit_type TEXT NOT NULL,
    unit_number INTEGER NOT NULL,
    effective_text_tokens INTEGER NOT NULL,
    has_text INTEGER NOT NULL,
    table_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (version_id, unit_type, unit_number)
);

CREATE TABLE IF NOT EXISTS trace_event (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    sequence_num INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_trace_event_run ON trace_event(run_id, sequence_num);
CREATE INDEX IF NOT EXISTS idx_chunk_version ON chunk(version_id);

CREATE TABLE IF NOT EXISTS chat_session_turn (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    run_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    token_estimate INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chat_session_turn_session_id ON chat_session_turn(session_id, id);

CREATE TABLE IF NOT EXISTS chat_session_summary (
    session_id TEXT PRIMARY KEY,
    summary_text TEXT NOT NULL,
    covers_until_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memory_fragment (
    fragment_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    run_id TEXT,
    fragment_type TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_memory_fragment_session_id ON memory_fragment(session_id);

-- 前端聊天 UI 会话（与 chat_session_turn 记忆表独立；按 session_id 与 WS 对齐）
CREATE TABLE IF NOT EXISTS ui_chat_session (
    session_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ui_preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def apply_schema(conn) -> None:
    """Execute bundled DDL on a sqlite3 connection."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
