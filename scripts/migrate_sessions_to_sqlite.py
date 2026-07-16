"""One-off: gộp toàn bộ data/sessions/*.jsonl vào một file sessions.db.

Usage:
    python scripts/migrate_sessions_to_sqlite.py [--sessions-dir DIR] [--db PATH] [--delete]

--delete: xoá các file .jsonl sau khi migrate thành công (mặc định giữ lại).
Bảo toàn created_at/last_active/counts gốc; KHÔNG áp TTL (giữ nguyên cả session cũ).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from acne_llm.chat.session import SESSION_SCHEMA_VERSION  # noqa: E402
from acne_llm.db.session_store import SQLiteSessionStore, _SCHEMA  # noqa: E402


def merge_meta(lines: list[dict]) -> dict:
    merged: dict = {}
    for obj in lines:
        if obj.get("type") == "meta":
            merged.update({k: v for k, v in obj.items() if k != "type"})
    return merged


def parse_file(p: Path) -> tuple[dict, list[dict]]:
    lines: list[dict] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    meta = merge_meta(lines)
    turns = [o for o in lines if o.get("type") == "turn"]
    return meta, turns


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions-dir", default="./data/sessions")
    ap.add_argument("--db", default="./data/sessions.db")
    ap.add_argument("--delete", action="store_true")
    args = ap.parse_args()

    src = Path(args.sessions_dir)
    files = sorted(src.glob("*.jsonl"))
    if not files:
        print(f"No .jsonl files in {src}")
        return 0

    # Khởi tạo schema qua store rồi ghi bulk bằng raw connection.
    SQLiteSessionStore(args.db).close()
    conn = sqlite3.connect(args.db)
    conn.executescript(_SCHEMA)

    n_sess = n_turn = n_skip = 0
    for p in files:
        sid = p.stem
        meta, turns = parse_file(p)
        if not meta and not turns:
            n_skip += 1
            continue
        ts = [t.get("timestamp", 0) for t in turns if t.get("timestamp")]
        created = meta.get("created_at") or (min(ts) if ts else 0.0)
        last_active = meta.get("last_active") or (max(ts) if ts else created)
        conn.execute(
            "INSERT OR REPLACE INTO sessions(session_id, created_at, last_active, user_context,"
            " asked_fields, total_clarify_count, accumulated_clinical_score, schema_version)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                sid, float(created), float(last_active),
                json.dumps(meta.get("user_context", {}), ensure_ascii=False),
                json.dumps(list(meta.get("asked_fields", [])), ensure_ascii=False),
                int(meta.get("total_clarify_count", 0) or 0),
                float(meta.get("accumulated_clinical_score", 0.0) or 0.0),
                int(meta.get("schema_version", SESSION_SCHEMA_VERSION) or SESSION_SCHEMA_VERSION),
            ),
        )
        conn.execute("DELETE FROM turns WHERE session_id=?", (sid,))
        for t in turns:
            snap = t.get("normalized_snapshot")
            conn.execute(
                "INSERT INTO turns(session_id, role, content, timestamp, mode, used_chunks,"
                " normalized_snapshot, metadata) VALUES (?,?,?,?,?,?,?,?)",
                (
                    sid, t.get("role", "user"), t.get("content", ""),
                    float(t.get("timestamp", 0) or 0), t.get("mode", "hybrid"),
                    json.dumps(t.get("used_chunks", []), ensure_ascii=False),
                    json.dumps(snap, ensure_ascii=False) if snap else None,
                    json.dumps(t.get("metadata", {}) or {}, ensure_ascii=False),
                ),
            )
            n_turn += 1
        n_sess += 1
    conn.commit()
    conn.close()

    print(f"Migrated {n_sess} sessions, {n_turn} turns (skipped {n_skip} empty) -> {args.db}")

    if args.delete:
        removed = 0
        for p in files:
            try:
                p.unlink()
                removed += 1
            except OSError as e:
                print(f"  delete failed {p.name}: {e}")
        print(f"Deleted {removed} .jsonl files from {src}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
