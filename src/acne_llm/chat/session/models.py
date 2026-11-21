"""Kieu du lieu va hang so cua session. Khong phu thuoc module nao khac.

Tach khoi session.py o Phase 7. Ly do: `ConversationTurn` duoc import o 13 noi,
va truoc day moi noi trong so do phai keo theo ca 714 dong -- gom session store,
fold_history_facts va render prompt -- chi de lay mot dataclass.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

# ── Constants ────────────────────────────────────────────────────────────────

SESSION_TTL: float = 1800.0        # seconds idle before session expires
MAX_HISTORY_TURNS: int = 6         # keep last N turns (0 = unlimited)
SESSION_SCHEMA_VERSION: int = 2
# Nguồn sự thật duy nhất cho ngân sách ký tự lịch sử.
HISTORY_CHAR_BUDGET: int = 2000    # ~570 tokens; prompt thực đo được 828 tokens / ctx 3072

# Nguồn sự thật duy nhất cho cửa sổ lịch sử đưa vào prompt.
HISTORY_WINDOW_TURNS: int = 6      # 3 lượt hỏi-đáp; budget chars mới là giới hạn thật


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class NormalizedSnapshot:
    """Structured facts extracted from one user turn.

    Stored beside the raw/clean turn text so later turns can fold memory
    without re-running regex normalization over the whole history.
    """
    context: dict = field(default_factory=dict)
    clinical: dict = field(default_factory=dict)
    clean_text: str = ""


@dataclass
class ConversationTurn:
    role: Literal["user", "assistant"]
    content: str                            # raw text of the turn
    timestamp: float = field(default_factory=time.time)
    mode: str = "hybrid"                    # pipeline mode that produced this turn
    used_chunks: list[str] = field(default_factory=list)
    normalized_snapshot: NormalizedSnapshot | None = None
    metadata: dict = field(default_factory=dict)
    # ponytail: intent_label / intent_confidence / turn_type da bi xoa. Chung chi
    # từng được ghi nhưng không có consumer; SQLite không khôi phục các field cũ.
    # Du lieu intent van con nguyen trong `metadata`.


@dataclass
class Session:
    session_id: str
    turns: list[ConversationTurn] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    # Accumulated user context across turns (age, skin_type, etc.)
    # Populated by callers; never overwritten, only merged.
    user_context: dict = field(default_factory=dict)
    # Tracks which follow-up fields have already been asked to avoid repeating.
    # e.g. {"lesion_types", "distribution", "duration_weeks"}
    asked_fields: set = field(default_factory=set)
    # ── Session-level intent tracking (task #6) ──────────────────────────────
    total_clarify_count: int = 0    # số lần bot hỏi clarify trong session này
    accumulated_clinical_score: float = 0.0  # tổng score completeness tích lũy
    schema_version: int = SESSION_SCHEMA_VERSION

    def is_expired(self, ttl: float = SESSION_TTL) -> bool:
        return (time.time() - self.last_active) > ttl

    def touch(self) -> None:
        self.last_active = time.time()
