"""SQLite-backed SessionStore — một file sessions.db thay cho nhiều file JSONL.

Session store duy nhất của hệ thống: một file sessions.db, giao tiếp qua
interface ổn định cho di.py/runtime.py. Tự quản schema riêng (bảng sessions + turns)
trong file DB độc lập, không phụ thuộc audit schema ở db/base.py.

Ngữ nghĩa:
- TTL: session idle > ttl bị coi là hết hạn, xoá lazy khi truy cập.
- schema_version lệch → reset session.
- Lịch sử append-only; get_history trả max_turns turn mới nhất (0 = toàn bộ).
- user_context: last-write-wins theo từng key.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from loguru import logger

from ..chat.session import (
    ConversationTurn,
    NormalizedSnapshot,
    Session,
    SESSION_TTL,
    SESSION_SCHEMA_VERSION,
)

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sessions (
    session_id                  TEXT    PRIMARY KEY,
    created_at                  REAL    NOT NULL,
    last_active                 REAL    NOT NULL,
    user_context                TEXT    NOT NULL DEFAULT '{}',
    asked_fields                TEXT    NOT NULL DEFAULT '[]',
    total_clarify_count         INTEGER NOT NULL DEFAULT 0,
    accumulated_clinical_score  REAL    NOT NULL DEFAULT 0.0,
    schema_version              INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS turns (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT    NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role                TEXT    NOT NULL,
    content             TEXT    NOT NULL,
    timestamp           REAL    NOT NULL,
    mode                TEXT    NOT NULL DEFAULT 'hybrid',
    used_chunks         TEXT    NOT NULL DEFAULT '[]',
    normalized_snapshot TEXT,
    metadata            TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, timestamp);
"""


class SQLiteSessionStore:
    """Thread-safe SQLite session store (một connection per thread)."""

    def __init__(
        self,
        db_path: str,
        ttl: float = SESSION_TTL,
        max_turns: int = 0,
    ) -> None:
        self._db_path = db_path
        self.ttl = ttl
        self.max_turns = max_turns
        self._local = threading.local()
        self._lock = threading.RLock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.executescript(_SCHEMA)
        logger.info(f"[SessionStore] SQLite @ {db_path}")

    # ── connection ────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        if getattr(self._local, "conn", None) is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    # ── helpers ───────────────────────────────────────────────────────────────

    def _is_valid_sid(self, session_id: str | None) -> bool:
        return bool(session_id and session_id.strip())

    def _is_expired(self, last_active: float) -> bool:
        return (time.time() - float(last_active or 0)) > self.ttl

    def _row(self, sid: str):
        return self._conn().execute(
            "SELECT * FROM sessions WHERE session_id=?", (sid,)
        ).fetchone()

    def _delete(self, sid: str) -> None:
        c = self._conn()
        c.execute("DELETE FROM sessions WHERE session_id=?", (sid,))
        c.commit()

    def _create(self, sid: str) -> None:
        now = time.time()
        c = self._conn()
        c.execute(
            "INSERT INTO sessions(session_id, created_at, last_active, user_context,"
            " asked_fields, total_clarify_count, accumulated_clinical_score, schema_version)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (sid, now, now, "{}", "[]", 0, 0.0, SESSION_SCHEMA_VERSION),
        )
        c.commit()

    def _stale(self, row) -> bool:
        """Row cần reset: hết hạn hoặc schema_version lệch."""
        if row is None:
            return False
        if self._is_expired(row["last_active"]):
            return True
        return int(row["schema_version"] or 0) != SESSION_SCHEMA_VERSION

    def _ensure(self, sid: str):
        """Đảm bảo có session hợp lệ (tạo mới nếu thiếu/hết hạn/lệch schema)."""
        row = self._row(sid)
        if row is None or self._stale(row):
            self._delete(sid)
            self._create(sid)
            row = self._row(sid)
        return row

    def _touch(self, sid: str) -> None:
        c = self._conn()
        c.execute("UPDATE sessions SET last_active=? WHERE session_id=?", (time.time(), sid))
        c.commit()

    def _row_to_turn(self, r) -> ConversationTurn:
        snap = None
        if r["normalized_snapshot"]:
            try:
                d = json.loads(r["normalized_snapshot"])
                snap = NormalizedSnapshot(
                    context=d.get("context", {}),
                    clinical=d.get("clinical", {}),
                    clean_text=d.get("clean_text", ""),
                )
            except (ValueError, TypeError):
                pass
        try:
            meta = json.loads(r["metadata"] or "{}")
        except (ValueError, TypeError):
            meta = {}
        return ConversationTurn(
            role=r["role"],
            content=r["content"],
            timestamp=r["timestamp"],
            mode=r["mode"],
            used_chunks=json.loads(r["used_chunks"] or "[]"),
            normalized_snapshot=snap,
            metadata=meta,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def get_or_create(self, session_id: str | None) -> Session | None:
        if not self._is_valid_sid(session_id):
            return None
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            row = self._ensure(sid)
            self._touch(sid)
            row = self._row(sid)
            return Session(
                session_id=sid,
                turns=self.get_history(sid),
                created_at=row["created_at"],
                last_active=row["last_active"],
                user_context=json.loads(row["user_context"] or "{}"),
                asked_fields=set(json.loads(row["asked_fields"] or "[]")),
                total_clarify_count=int(row["total_clarify_count"] or 0),
                accumulated_clinical_score=float(row["accumulated_clinical_score"] or 0.0),
                schema_version=SESSION_SCHEMA_VERSION,
            )

    def get_history(self, session_id: str | None) -> list[ConversationTurn]:
        if not self._is_valid_sid(session_id):
            return []
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            row = self._row(sid)
            if row is None:
                return []
            if self._stale(row):
                self._delete(sid)
                return []
            if self.max_turns and self.max_turns > 0:
                rows = self._conn().execute(
                    "SELECT * FROM turns WHERE session_id=? ORDER BY timestamp DESC, id DESC LIMIT ?",
                    (sid, self.max_turns),
                ).fetchall()
                rows = list(reversed(rows))
            else:
                rows = self._conn().execute(
                    "SELECT * FROM turns WHERE session_id=? ORDER BY timestamp ASC, id ASC",
                    (sid,),
                ).fetchall()
            return [self._row_to_turn(r) for r in rows]

    def append_turn(self, session_id: str | None, turn: ConversationTurn) -> None:
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._ensure(sid)
            snap_json = None
            if turn.normalized_snapshot is not None:
                snap_json = json.dumps({
                    "context": turn.normalized_snapshot.context,
                    "clinical": turn.normalized_snapshot.clinical,
                    "clean_text": turn.normalized_snapshot.clean_text,
                }, ensure_ascii=False)
            c = self._conn()
            c.execute(
                "INSERT INTO turns(session_id, role, content, timestamp, mode, used_chunks,"
                " normalized_snapshot, metadata) VALUES (?,?,?,?,?,?,?,?)",
                (
                    sid, turn.role, turn.content, turn.timestamp, turn.mode,
                    json.dumps(turn.used_chunks, ensure_ascii=False),
                    snap_json,
                    json.dumps(turn.metadata or {}, ensure_ascii=False),
                ),
            )
            if turn.role == "assistant" and turn.mode == "clarify":
                c.execute(
                    "UPDATE sessions SET total_clarify_count=total_clarify_count+1"
                    " WHERE session_id=?", (sid,),
                )
            c.commit()
            self._touch(sid)

    def merge_user_context(self, session_id: str | None, context: dict) -> None:
        if not self._is_valid_sid(session_id) or not context:
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            row = self._row(sid)
            if row is None or self._is_expired(row["last_active"]):
                if row is not None:
                    self._delete(sid)
                return
            existing = json.loads(row["user_context"] or "{}")
            updated = False
            for k, v in context.items():
                if v is not None and existing.get(k) != v:
                    existing[k] = v
                    updated = True
            if updated:
                c = self._conn()
                c.execute(
                    "UPDATE sessions SET user_context=? WHERE session_id=?",
                    (json.dumps(existing, ensure_ascii=False), sid),
                )
                c.commit()

    def get_user_context(self, session_id: str | None) -> dict:
        if not self._is_valid_sid(session_id):
            return {}
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            row = self._row(sid)
            if row is None:
                return {}
            if self._is_expired(row["last_active"]):
                self._delete(sid)
                return {}
            return json.loads(row["user_context"] or "{}")

    # ponytail: get_asked_fields / mark_fields_asked da bi xoa (co che bi go o
    # runtime.py). Cot `asked_fields` giu lai trong schema -- DEFAULT '[]',
    # khong ton gi, va tranh mot lan migration.

    def increment_followup_count(self, session_id: str | None, amount: float = 1.0) -> None:
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            row = self._row(sid)
            if row is None or self._is_expired(row["last_active"]):
                if row is not None:
                    self._delete(sid)
                return
            c = self._conn()
            c.execute(
                "UPDATE sessions SET accumulated_clinical_score=accumulated_clinical_score+?"
                " WHERE session_id=?", (float(amount), sid),
            )
            c.commit()

    def delete(self, session_id: str | None) -> None:
        if not self._is_valid_sid(session_id):
            return
        with self._lock:
            self._delete(session_id.strip())  # type: ignore[union-attr]

    def active_count(self) -> int:
        cutoff = time.time() - self.ttl
        row = self._conn().execute(
            "SELECT COUNT(*) AS cnt FROM sessions WHERE last_active > ?", (cutoff,)
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
