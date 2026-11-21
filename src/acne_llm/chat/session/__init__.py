"""Bo nho hoi thoai nhieu luot.

Package nay duoc tach tu mot file 714 dong o Phase 7. Bon nhom ben trong thay
doi vi bon ly do khac nhau, nen chung o bon file khac nhau:

    models.py   kieu du lieu + hang so        gan nhu khong doi
    view.py     chon + render cho prompt      doi khi prompt doi
    fold.py     gop du kien qua cac luot      doi khi luat gop doi

Production persistence lives in ``db.session_store.SQLiteSessionStore``.
In-memory stores belong to test helpers and are intentionally not exported.
"""
from __future__ import annotations

from .fold import (
    fold_history_facts,
    snapshot_from_user,
)
from .models import (
    HISTORY_CHAR_BUDGET,
    HISTORY_WINDOW_TURNS,
    MAX_HISTORY_TURNS,
    SESSION_SCHEMA_VERSION,
    SESSION_TTL,
    ConversationTurn,
    NormalizedSnapshot,
    Session,
)
from .view import (
    CONTEXT_FIELD_THRESHOLD,
    build_confirmed_profile,
    format_history_block,
    select_relevant_history,
)

__all__ = [
    "HISTORY_CHAR_BUDGET", "HISTORY_WINDOW_TURNS", "MAX_HISTORY_TURNS",
    "SESSION_SCHEMA_VERSION", "SESSION_TTL", "CONTEXT_FIELD_THRESHOLD",
    "ConversationTurn", "NormalizedSnapshot", "Session",
    "select_relevant_history", "build_confirmed_profile",
    "snapshot_from_user", "fold_history_facts", "format_history_block",
]
