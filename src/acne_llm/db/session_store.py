"""SQLite-backed SessionStore — drop-in replacement cho in-memory SessionStore.

Interface giữ nguyên hoàn toàn với chat/session.py để runtime.py không cần sửa.
"""
from __future__ import annotations

import json
import time
import threading
from typing import TYPE_CHECKING

from loguru import logger

from .base import DBConnection
from ..chat.session import (
    ConversationTurn,
    NormalizedSnapshot,
    Session,
    SESSION_TTL,
    MAX_HISTORY_TURNS,
)

if TYPE_CHECKING:
    pass


class SQLiteSessionStore:
    """Thread-safe SQLite session store.

    Thay thế SessionStore (in-memory) trong chat/session.py.
    Tất cả public method giữ nguyên signature để runtime.py không đổi.
    """

    def __init__(
        self,
        db_path: str,
        ttl: float = SESSION_TTL,
        max_turns: int = MAX_HISTORY_TURNS,
    ) -> None:
        self._db = DBConnection(db_path)
        self.ttl = ttl
        self.max_turns = max_turns
        self._lock = threading.RLock()
        logger.info(f"[SessionStore] SQLite @ {db_path}")

    # ── helpers ──────────────────────────────────────────────────────────────

    def _is_valid_sid(self, session_id: str | None) -> bool:
        return bool(session_id and session_id.strip())

    def _touch(self, sid: str) -> None:
        now = time.time()
        self._db.execute(
            "UPDATE sessions SET last_active=? WHERE session_id=?", (now, sid)
        )
        self._db.commit()

    def _is_expired(self, last_active: float) -> bool:
        return (time.time() - last_active) > self.ttl

    def _ensure_session(self, sid: str) -> None:
        """Tạo session nếu chưa có, hoặc expire nếu quá TTL."""
        row = self._db.execute(
            "SELECT last_active FROM sessions WHERE session_id=?", (sid,)
        ).fetchone()
        now = time.time()
        if row is None:
            self._db.execute(
                "INSERT INTO sessions(session_id, created_at, last_active, user_context)"
                " VALUES (?,?,?,?)",
                (sid, now, now, "{}"),
            )
            self._db.commit()
        elif self._is_expired(row["last_active"]):
            # Xoá session cũ (CASCADE sẽ xoá turns + asked_fields)
            self._db.execute("DELETE FROM sessions WHERE session_id=?", (sid,))
            self._db.execute(
                "INSERT INTO sessions(session_id, created_at, last_active, user_context)"
                " VALUES (?,?,?,?)",
                (sid, now, now, "{}"),
            )
            self._db.commit()

    def _row_to_turn(self, row) -> ConversationTurn:
        snap = None
        if row["normalized_snapshot"]:
            try:
                d = json.loads(row["normalized_snapshot"])
                snap = NormalizedSnapshot(
                    context=d.get("context", {}),
                    clinical=d.get("clinical", {}),
                    clean_text=d.get("clean_text", ""),
                )
            except Exception:
                pass
        return ConversationTurn(
            role=row["role"],
            content=row["content"],
            timestamp=row["timestamp"],
            mode=row["mode"],
            used_chunks=json.loads(row["used_chunks"] or "[]"),
            normalized_snapshot=snap,
        )

    # ── Public API (cùng interface với SessionStore) ──────────────────────────

    def get_or_create(self, session_id: str | None) -> Session | None:
        if not self._is_valid_sid(session_id):
            return None
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._ensure_session(sid)
            self._touch(sid)
            row = self._db.execute(
                "SELECT * FROM sessions WHERE session_id=?", (sid,)
            ).fetchone()
            turns = self.get_history(sid)
            return Session(
                session_id=sid,
                turns=turns,
                created_at=row["created_at"],
                last_active=row["last_active"],
                user_context=json.loads(row["user_context"] or "{}"),
                asked_fields=set(self.get_asked_fields(sid)),
            )

    def get_history(self, session_id: str | None) -> list[ConversationTurn]:
        if not self._is_valid_sid(session_id):
            return []
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            if self.max_turns and self.max_turns > 0:
                rows = self._db.execute(
                    "SELECT * FROM turns WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                    (sid, self.max_turns),
                ).fetchall()
                rows = list(reversed(rows))
            else:
                rows = self._db.execute(
                    "SELECT * FROM turns WHERE session_id=? ORDER BY timestamp ASC",
                    (sid,),
                ).fetchall()
            turns = [self._row_to_turn(r) for r in rows]
            return turns

    def append_turn(
        self,
        session_id: str | None,
        turn: ConversationTurn,
    ) -> None:
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._ensure_session(sid)
            snap_json = None
            if turn.normalized_snapshot is not None:
                snap_json = json.dumps({
                    "context": turn.normalized_snapshot.context,
                    "clinical": turn.normalized_snapshot.clinical,
                    "clean_text": turn.normalized_snapshot.clean_text,
                }, ensure_ascii=False)
            self._db.execute(
                "INSERT INTO turns(session_id, role, content, timestamp, mode, used_chunks, normalized_snapshot)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    sid,
                    turn.role,
                    turn.content,
                    turn.timestamp,
                    turn.mode,
                    json.dumps(turn.used_chunks, ensure_ascii=False),
                    snap_json,
                ),
            )
            # Giữ chỉ max_turns mới nhất khi cấu hình explicit bound.
            if self.max_turns and self.max_turns > 0:
                self._db.execute(
                    """
                    DELETE FROM turns WHERE session_id=? AND id NOT IN (
                        SELECT id FROM turns WHERE session_id=?
                        ORDER BY timestamp DESC LIMIT ?
                    )
                    """,
                    (sid, sid, self.max_turns),
                )
            self._touch(sid)

    def merge_user_context(
        self,
        session_id: str | None,
        context: dict,
    ) -> None:
        if not self._is_valid_sid(session_id) or not context:
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            row = self._db.execute(
                "SELECT user_context FROM sessions WHERE session_id=?", (sid,)
            ).fetchone()
            if row is None:
                return
            existing = json.loads(row["user_context"] or "{}")
            # First write wins — không overwrite key đã có
            for k, v in context.items():
                if v is not None and k not in existing:
                    existing[k] = v
            self._db.execute(
                "UPDATE sessions SET user_context=? WHERE session_id=?",
                (json.dumps(existing, ensure_ascii=False), sid),
            )
            self._db.commit()

    def get_user_context(self, session_id: str | None) -> dict:
        if not self._is_valid_sid(session_id):
            return {}
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            row = self._db.execute(
                "SELECT user_context FROM sessions WHERE session_id=?", (sid,)
            ).fetchone()
            if row is None:
                return {}
            return json.loads(row["user_context"] or "{}")

    def get_asked_fields(self, session_id: str | None) -> set:
        if not self._is_valid_sid(session_id):
            return set()
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            rows = self._db.execute(
                "SELECT field FROM asked_fields WHERE session_id=?", (sid,)
            ).fetchall()
            return {r["field"] for r in rows}

    def mark_fields_asked(self, session_id: str | None, fields: list[str]) -> None:
        if not self._is_valid_sid(session_id) or not fields:
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._db.executemany(
                "INSERT OR IGNORE INTO asked_fields(session_id, field) VALUES (?,?)",
                [(sid, f) for f in fields],
            )
            self._db.commit()

    def delete(self, session_id: str | None) -> None:
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._db.execute("DELETE FROM sessions WHERE session_id=?", (sid,))
            self._db.commit()

    def active_count(self) -> int:
        cutoff = time.time() - self.ttl
        row = self._db.execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE last_active > ?", (cutoff,)
        ).fetchone()
        return row["cnt"] if row else 0

    def close(self) -> None:
        self._db.close()
