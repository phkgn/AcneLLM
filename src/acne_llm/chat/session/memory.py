"""SessionStore in-memory.

DOC KY: day KHONG phai duong chay production.

`di.py:94` wire `db.session_store.SQLiteSessionStore` vao `c.session_store`,
khong co nhanh du phong, va ca `intake.py` lan `runtime.py` deu doc
`c.session_store`. `get_session_store()` duoi day chi duoc TEST goi (17 cho),
khong mot dong production nao.

Docstring cu cua session.py ghi "Usage in runtime.py: store =
get_session_store()" -- sai, va da xoa. Hai store co interface trung khit 8
method (SQLite thua `close`), nen ban nay la test double, khong phai tang luu
tru chinh. Sua no khong sua production.

Thiet ke giu nguyen: khong phu thuoc ngoai, TTL het han lazy, mot RLock.
"""
from __future__ import annotations

import threading
import time

from .models import (
    MAX_HISTORY_TURNS,
    SESSION_TTL,
    ConversationTurn,
    Session,
)

# ── Store ────────────────────────────────────────────────────────────────────

class SessionStore:
    """Thread-safe in-memory session store.

    All public methods are no-ops when session_id is None or empty, which
    preserves the pre-history behavior of the chat pipeline exactly.
    """

    def __init__(
        self,
        ttl: float = SESSION_TTL,
        max_turns: int = MAX_HISTORY_TURNS,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()
        self.ttl = ttl
        self.max_turns = max_turns

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _is_valid_sid(self, session_id: str | None) -> bool:
        return bool(session_id and session_id.strip())

    def _expire_if_stale(self, session_id: str) -> bool:
        """Remove session if TTL exceeded. Returns True if removed."""
        sess = self._sessions.get(session_id)
        if sess is not None and sess.is_expired(self.ttl):
            del self._sessions[session_id]
            return True
        return False

    # ── Public API ────────────────────────────────────────────────────────────

    def get_or_create(self, session_id: str | None) -> Session | None:
        """Return existing session (if live) or create a new one.

        Returns None when session_id is falsy.
        """
        if not self._is_valid_sid(session_id):
            return None
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._expire_if_stale(sid)
            if sid not in self._sessions:
                self._sessions[sid] = Session(session_id=sid)
            sess = self._sessions[sid]
            sess.touch()
            return sess

    def get_history(self, session_id: str | None) -> list[ConversationTurn]:
        """Return the last max_turns turns for this session, oldest first.

        Returns [] when session_id is falsy or session does not exist / expired.
        """
        if not self._is_valid_sid(session_id):
            return []
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._expire_if_stale(sid)
            sess = self._sessions.get(sid)
            if sess is None:
                return []
            sess.touch()
            if self.max_turns and self.max_turns > 0:
                return list(sess.turns[-self.max_turns :])
            return list(sess.turns)

    def append_turn(
        self,
        session_id: str | None,
        turn: ConversationTurn,
    ) -> None:
        """Append a turn to the session's history.

        No-op when session_id is falsy.
        """
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._expire_if_stale(sid)
            if sid not in self._sessions:
                self._sessions[sid] = Session(session_id=sid)
            sess = self._sessions[sid]

            if turn.role == "assistant" and turn.mode == "clarify":
                sess.total_clarify_count += 1

            sess.turns.append(turn)
            # Keep only the last max_turns when an explicit bound is configured.
            if self.max_turns and self.max_turns > 0 and len(sess.turns) > self.max_turns:
                sess.turns = sess.turns[-self.max_turns :]
            sess.touch()

    def merge_user_context(
        self,
        session_id: str | None,
        context: dict,
    ) -> None:
        """Update confirmed profile with latest explicit values."""
        if not self._is_valid_sid(session_id) or not context:
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            sess = self._sessions.get(sid)
            if sess is None:
                return
            for k, v in context.items():
                if v is not None:
                    sess.user_context[k] = v

    def get_user_context(self, session_id: str | None) -> dict:
        """Return accumulated user context for session. Returns {} if not found."""
        if not self._is_valid_sid(session_id):
            return {}
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            sess = self._sessions.get(sid)
            return dict(sess.user_context) if sess else {}

    # ponytail: get_asked_fields / mark_fields_asked da bi xoa. Co che "dung hoi
    # lai field da hoi" bi go o runtime.py -- model doc duoc luot truoc no da hoi
    # gi. Cot `asked_fields` van con trong schema SQLite (DEFAULT '[]'), khong ton gi.

    def increment_followup_count(self, session_id: str | None, amount: float = 1.0) -> None:
        """Increment accumulated follow-up/progress score for this session."""
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            sess = self._sessions.get(sid)
            if sess is not None:
                sess.accumulated_clinical_score += float(amount)

    def delete(self, session_id: str | None) -> None:
        """Explicitly remove a session (e.g. on user logout)."""
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._sessions.pop(sid, None)

    def active_count(self) -> int:
        """Return number of non-expired sessions (for metrics/debug)."""
        with self._lock:
            now = time.time()
            return sum(
                1 for s in self._sessions.values()
                if (now - s.last_active) <= self.ttl
            )


# ── Module-level singleton ────────────────────────────────────────────────────

_store: SessionStore | None = None
_store_lock = threading.Lock()


def get_session_store() -> SessionStore:
    """Return the process-wide SessionStore singleton (lazy init)."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SessionStore()
    return _store
