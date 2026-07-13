"""Audit log — ghi nhận mọi tư vấn y tế cho trách nhiệm pháp lý và debug."""
from __future__ import annotations

import json
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from .base import DBConnection


@dataclass
class AuditEntry:
    user_message: str
    assistant_response: str
    used_chunk_ids: list[str] = field(default_factory=list)
    scope_decision: str = ""
    latency_ms: int = 0
    model_used: str = ""
    temperature: Optional[float] = None
    session_id: Optional[str] = None
    normalized_query: str = ""
    extracted_entities: dict = field(default_factory=dict)
    pii_detected: bool = False
    teencode_replaced: list[str] = field(default_factory=list)
    citation_compliance: Optional[bool] = None
    timestamp: float = field(default_factory=time.time)


class AuditStore:
    """Thread-safe audit log store dùng chung DBConnection với session store."""

    def __init__(self, db: DBConnection) -> None:
        self._db = db
        self._lock = threading.Lock()

    def log(self, entry: AuditEntry) -> None:
        """Ghi một audit entry. Non-blocking, lỗi chỉ warning không raise."""
        try:
            with self._lock:
                self._db.execute(
                    """INSERT INTO audit_log
                       (timestamp, session_id, user_message, assistant_response,
                        used_chunk_ids, scope_decision, latency_ms, model_used, temperature,
                        normalized_query, extracted_entities, pii_detected, teencode_replaced,
                        citation_compliance)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        entry.timestamp,
                        entry.session_id,
                        entry.user_message,
                        entry.assistant_response,
                        json.dumps(entry.used_chunk_ids, ensure_ascii=False),
                        entry.scope_decision,
                        entry.latency_ms,
                        entry.model_used,
                        entry.temperature,
                        entry.normalized_query,
                        json.dumps(entry.extracted_entities, ensure_ascii=False),
                        1 if entry.pii_detected else 0,
                        json.dumps(entry.teencode_replaced, ensure_ascii=False),
                        None if entry.citation_compliance is None else int(entry.citation_compliance),
                    ),
                )
                self._db.commit()
        except Exception as e:
            logger.warning(f"[AuditStore] Failed to log entry: {e}")

    def query(
        self,
        session_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Trả về audit entries gần nhất, mới nhất trước."""
        if session_id:
            rows = self._db.execute(
                """SELECT * FROM audit_log WHERE session_id=?
                   ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                (session_id, limit, offset),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["used_chunk_ids"] = json.loads(d.get("used_chunk_ids") or "[]")
            d["extracted_entities"] = json.loads(d.get("extracted_entities") or "{}")
            d["teencode_replaced"] = json.loads(d.get("teencode_replaced") or "[]")
            d["pii_detected"] = bool(d.get("pii_detected"))
            if d.get("citation_compliance") is not None:
                d["citation_compliance"] = bool(d["citation_compliance"])
            result.append(d)
        return result

    def count(self, session_id: Optional[str] = None) -> int:
        if session_id:
            row = self._db.execute(
                "SELECT COUNT(*) as cnt FROM audit_log WHERE session_id=?",
                (session_id,),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT COUNT(*) as cnt FROM audit_log"
            ).fetchone()
        return row["cnt"] if row else 0

    # ── Feedback ──────────────────────────────────────────────────────────────

    def log_feedback(
        self,
        message_id: str,
        rating: str,
        session_id: Optional[str] = None,
        audit_id: Optional[int] = None,
        comment: str = "",
    ) -> int:
        """Ghi một feedback entry. Trả về rowid vừa insert."""
        if rating not in ("up", "down"):
            raise ValueError(f"rating phải là 'up' hoặc 'down', nhận được: {rating!r}")
        try:
            with self._lock:
                cur = self._db.execute(
                    """INSERT INTO feedback
                       (timestamp, session_id, message_id, audit_id, rating, comment)
                       VALUES (?,?,?,?,?,?)""",
                    (time.time(), session_id, message_id, audit_id, rating, comment or ""),
                )
                self._db.commit()
                return cur.lastrowid or 0
        except Exception as e:
            logger.warning(f"[AuditStore] Failed to log feedback: {e}")
            return 0

    def feedback_stats(self) -> dict:
        """Tổng hợp nhanh: tổng up/down và tỉ lệ."""
        row = self._db.execute(
            """SELECT
               SUM(CASE WHEN rating='up'   THEN 1 ELSE 0 END) as up_count,
               SUM(CASE WHEN rating='down' THEN 1 ELSE 0 END) as down_count,
               COUNT(*) as total
               FROM feedback"""
        ).fetchone()
        if not row or not row["total"]:
            return {"up": 0, "down": 0, "total": 0, "satisfaction_rate": None}
        up = row["up_count"] or 0
        down = row["down_count"] or 0
        total = row["total"] or 0
        return {
            "up": up,
            "down": down,
            "total": total,
            "satisfaction_rate": round(up / total, 4) if total else None,
        }

    def recent_feedback(
        self,
        rating: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Trả về feedback gần nhất, mới nhất trước. Có thể filter theo rating."""
        if rating:
            rows = self._db.execute(
                """SELECT * FROM feedback WHERE rating=?
                   ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                (rating, limit, offset),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM feedback ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]
