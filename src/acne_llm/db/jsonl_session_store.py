"""JSONL-backed SessionStore — lưu mỗi session thành một file .jsonl.

Đơn giản hơn SQLite, dễ đọc/debug, zero external dependency.
Interface giữ nguyên hoàn toàn với SQLiteSessionStore để di.py không cần sửa nhiều.

Format file: data/sessions/<session_id>.jsonl
Mỗi dòng là một JSON object với field "type":
  {"type": "meta",  "created_at": ..., "last_active": ..., "user_context": {...}, "asked_fields": [...]}
  {"type": "turn",  "role": "user", "content": "...", "timestamp": ..., "mode": "hybrid",
                    "used_chunks": [...], "normalized_snapshot": {...} | null, "metadata": {...}}

Khi đọc history: load tất cả dòng type=turn; max_turns=0 nghĩa là lấy toàn bộ.
TTL: kiểm tra last_active trong meta khi get_history / append_turn.
"""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path

from loguru import logger

from ..chat.session import (
    ConversationTurn,
    NormalizedSnapshot,
    Session,
    SESSION_TTL,
    MAX_HISTORY_TURNS,
)


class JsonlSessionStore:
    """Thread-safe JSONL session store.

    Mỗi session = một file <sessions_dir>/<session_id>.jsonl.
    Dòng đầu tiên (type=meta) chứa metadata; các dòng tiếp theo là turns.
    Append-only: không rewrite toàn bộ file khi ghi turn mới.
    Compact (rewrite) chỉ chạy khi max_turns > 0.
    """

    def __init__(
        self,
        sessions_dir: str,
        ttl: float = SESSION_TTL,
        max_turns: int = MAX_HISTORY_TURNS,
    ) -> None:
        self._dir = Path(sessions_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self.max_turns = max_turns
        self._lock = threading.RLock()
        logger.info(f"[SessionStore] JSONL @ {sessions_dir}")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _is_valid_sid(self, session_id: str | None) -> bool:
        return bool(session_id and session_id.strip())

    def _path(self, sid: str) -> Path:
        # Sanitize: chỉ cho phép alnum, dash, underscore để tránh path traversal
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)
        return self._dir / f"{safe}.jsonl"

    def _read_lines(self, sid: str) -> list[dict]:
        """Đọc tất cả dòng JSON hợp lệ từ file session."""
        p = self._path(sid)
        if not p.exists():
            return []
        lines: list[dict] = []
        try:
            with p.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # bỏ qua dòng corrupt
        except OSError:
            pass
        return lines

    def _read_meta(self, sid: str) -> dict | None:
        """Đọc dòng meta (dòng đầu type=meta). Trả None nếu không tồn tại."""
        for obj in self._read_lines(sid):
            if obj.get("type") == "meta":
                return obj
        return None

    def _delete_file(self, sid: str) -> None:
        try:
            self._path(sid).unlink(missing_ok=True)
        except OSError as e:
            logger.warning(f"[SessionStore] delete failed for {sid}: {e}")

    def _is_expired(self, meta: dict | None) -> bool:
        if meta is None:
            return False
        return (time.time() - meta.get("last_active", 0)) > self.ttl

    def _write_line(self, sid: str, obj: dict) -> None:
        """Append một dòng JSON vào file session."""
        p = self._path(sid)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def _init_session(self, sid: str) -> None:
        """Tạo file mới với dòng meta."""
        now = time.time()
        self._write_line(sid, {
            "type": "meta",
            "created_at": now,
            "last_active": now,
            "user_context": {},
            "asked_fields": [],
        })

    def _touch(self, sid: str) -> None:
        """Cập nhật last_active bằng cách append dòng meta mới.

        Khi đọc, dòng meta sau cùng (theo thứ tự file) được dùng.
        """
        self._write_line(sid, {
            "type": "meta",
            "last_active": time.time(),
        })

    def _compact_if_needed(self, sid: str, all_lines: list[dict]) -> None:
        """Rewrite file nếu quá nhiều turn (compact để tránh file phình to)."""
        if not self.max_turns or self.max_turns <= 0:
            return
        turn_count = sum(1 for l in all_lines if l.get("type") == "turn")
        if turn_count <= self.max_turns * 2:
            return
        # Lấy meta mới nhất
        meta_merged: dict = {}
        for obj in all_lines:
            if obj.get("type") == "meta":
                meta_merged.update({k: v for k, v in obj.items() if k != "type"})
        # Lấy max_turns turn mới nhất
        turns = [l for l in all_lines if l.get("type") == "turn"]
        turns_keep = turns[-self.max_turns:]
        # Rewrite
        p = self._path(sid)
        tmp = p.with_suffix(".jsonl.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                f.write(json.dumps({"type": "meta", **meta_merged}, ensure_ascii=False) + "\n")
                for t in turns_keep:
                    f.write(json.dumps(t, ensure_ascii=False) + "\n")
            tmp.replace(p)
        except OSError as e:
            logger.warning(f"[SessionStore] compact failed for {sid}: {e}")
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _get_merged_meta(self, all_lines: list[dict]) -> dict:
        """Merge tất cả dòng meta (last write wins cho từng field)."""
        merged: dict = {}
        for obj in all_lines:
            if obj.get("type") == "meta":
                merged.update({k: v for k, v in obj.items() if k != "type"})
        return merged

    def _row_to_turn(self, obj: dict) -> ConversationTurn:
        snap = None
        snap_data = obj.get("normalized_snapshot")
        if snap_data:
            snap = NormalizedSnapshot(
                context=snap_data.get("context", {}),
                clinical=snap_data.get("clinical", {}),
                clean_text=snap_data.get("clean_text", ""),
            )
        return ConversationTurn(
            role=obj.get("role", "user"),
            content=obj.get("content", ""),
            timestamp=obj.get("timestamp", time.time()),
            mode=obj.get("mode", "hybrid"),
            used_chunks=obj.get("used_chunks", []),
            normalized_snapshot=snap,
            metadata=obj.get("metadata", {}) or {},
        )

    # ── Public API (cùng interface với SQLiteSessionStore) ────────────────────

    def get_or_create(self, session_id: str | None) -> Session | None:
        if not self._is_valid_sid(session_id):
            return None
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            all_lines = self._read_lines(sid)
            meta = self._get_merged_meta(all_lines)
            if not meta or self._is_expired(meta):
                # Tạo mới (hoặc reset nếu expired)
                self._delete_file(sid)
                self._init_session(sid)
                all_lines = self._read_lines(sid)
                meta = self._get_merged_meta(all_lines)
            else:
                self._touch(sid)
                all_lines = self._read_lines(sid)
                meta = self._get_merged_meta(all_lines)
            turns = self.get_history(sid)
            return Session(
                session_id=sid,
                turns=turns,
                created_at=meta.get("created_at", time.time()),
                last_active=meta.get("last_active", time.time()),
                user_context=meta.get("user_context", {}),
                asked_fields=set(meta.get("asked_fields", [])),
            )

    def get_history(self, session_id: str | None) -> list[ConversationTurn]:
        if not self._is_valid_sid(session_id):
            return []
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            all_lines = self._read_lines(sid)
            meta = self._get_merged_meta(all_lines)
            if self._is_expired(meta):
                self._delete_file(sid)
                return []
            turn_lines = [l for l in all_lines if l.get("type") == "turn"]
            # Lấy max_turns mới nhất khi cấu hình explicit bound.
            if self.max_turns and self.max_turns > 0:
                turn_lines = turn_lines[-self.max_turns:]
            return [self._row_to_turn(l) for l in turn_lines]

    def append_turn(
        self,
        session_id: str | None,
        turn: ConversationTurn,
    ) -> None:
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            all_lines = self._read_lines(sid)
            meta = self._get_merged_meta(all_lines)
            p = self._path(sid)
            if not p.exists() or self._is_expired(meta):
                self._delete_file(sid)
                self._init_session(sid)
            snap_data = None
            if turn.normalized_snapshot is not None:
                snap_data = {
                    "context": turn.normalized_snapshot.context,
                    "clinical": turn.normalized_snapshot.clinical,
                    "clean_text": turn.normalized_snapshot.clean_text,
                }
            self._write_line(sid, {
                "type": "turn",
                "role": turn.role,
                "content": turn.content,
                "timestamp": turn.timestamp,
                "mode": turn.mode,
                "used_chunks": turn.used_chunks,
                "normalized_snapshot": snap_data,
                "metadata": turn.metadata or {},
            })
            self._touch(sid)
            # Compact nếu file quá lớn
            self._compact_if_needed(sid, self._read_lines(sid))

    def merge_user_context(
        self,
        session_id: str | None,
        context: dict,
    ) -> None:
        if not self._is_valid_sid(session_id) or not context:
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            all_lines = self._read_lines(sid)
            meta = self._get_merged_meta(all_lines)
            if not meta:
                return
            if self._is_expired(meta):
                self._delete_file(sid)
                return
            existing: dict = meta.get("user_context", {})
            # First write wins — không overwrite key đã có
            updated = False
            for k, v in context.items():
                if v is not None and k not in existing:
                    existing[k] = v
                    updated = True
            if updated:
                self._write_line(sid, {
                    "type": "meta",
                    "user_context": existing,
                })

    def get_user_context(self, session_id: str | None) -> dict:
        if not self._is_valid_sid(session_id):
            return {}
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            all_lines = self._read_lines(sid)
            meta = self._get_merged_meta(all_lines)
            if self._is_expired(meta):
                self._delete_file(sid)
                return {}
            return dict(meta.get("user_context", {}))

    def get_asked_fields(self, session_id: str | None) -> set:
        if not self._is_valid_sid(session_id):
            return set()
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            all_lines = self._read_lines(sid)
            meta = self._get_merged_meta(all_lines)
            if self._is_expired(meta):
                self._delete_file(sid)
                return set()
            return set(meta.get("asked_fields", []))

    def mark_fields_asked(self, session_id: str | None, fields: list[str]) -> None:
        if not self._is_valid_sid(session_id) or not fields:
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            all_lines = self._read_lines(sid)
            meta = self._get_merged_meta(all_lines)
            if not meta:
                return
            if self._is_expired(meta):
                self._delete_file(sid)
                return
            existing = set(meta.get("asked_fields", []))
            new_fields = [f for f in fields if f not in existing]
            if new_fields:
                existing.update(new_fields)
                self._write_line(sid, {
                    "type": "meta",
                    "asked_fields": list(existing),
                })

    def delete(self, session_id: str | None) -> None:
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._delete_file(sid)

    def active_count(self) -> int:
        cutoff = time.time() - self.ttl
        count = 0
        try:
            for p in self._dir.glob("*.jsonl"):
                meta = self._read_meta(p.stem)
                if meta and meta.get("last_active", 0) > cutoff:
                    count += 1
        except OSError:
            pass
        return count

    def close(self) -> None:
        pass
