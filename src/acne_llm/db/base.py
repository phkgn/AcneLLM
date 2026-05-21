"""SQLite connection + schema init dùng chung cho session store và audit log."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

# DDL — chỉ chứa audit_log và feedback
# NOTE: sessions và turns đã chuyển sang JSONL (data/sessions/<id>.jsonl).
#       Các bảng sessions/turns/asked_fields đã được loại bỏ khỏi schema này.
_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS audit_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         REAL    NOT NULL,
    session_id        TEXT,                    -- nullable (anonymous request)
    user_message      TEXT    NOT NULL,
    assistant_response TEXT   NOT NULL,
    used_chunk_ids    TEXT    NOT NULL DEFAULT '[]',   -- JSON
    scope_decision    TEXT    NOT NULL DEFAULT '',
    latency_ms        INTEGER NOT NULL DEFAULT 0,
    model_used        TEXT    NOT NULL DEFAULT '',
    temperature       REAL
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_session   ON audit_log(session_id);

CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   REAL    NOT NULL,
    session_id  TEXT,                       -- nullable
    message_id  TEXT    NOT NULL,           -- frontend UUID của assistant message
    audit_id    INTEGER REFERENCES audit_log(id) ON DELETE SET NULL,
    rating      TEXT    NOT NULL CHECK(rating IN ('up', 'down')),
    comment     TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_rating  ON feedback(rating);
"""


class DBConnection:
    """Thread-safe SQLite connection wrapper (một connection per thread via threading.local)."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._local = threading.local()
        # Tạo schema ngay khi khởi tạo (dùng dedicated connection)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.executescript(_SCHEMA)

    def _get_conn(self) -> sqlite3.Connection:
        """Trả về connection riêng cho thread hiện tại."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._get_conn().execute(sql, params)

    def executemany(self, sql: str, params_seq) -> sqlite3.Cursor:
        return self._get_conn().executemany(sql, params_seq)

    def commit(self) -> None:
        self._get_conn().commit()

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
