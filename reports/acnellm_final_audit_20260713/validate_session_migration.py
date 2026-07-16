"""Validate the staged JSONL-to-SQLite migrator using disposable fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPT = ROOT / "scripts" / "migrate_sessions_to_sqlite.py"
OUT = HERE / "session_migration_validation.json"


def run_migration(src: Path, db: Path, delete: bool = False) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(SCRIPT), "--sessions-dir", str(src), "--db", str(db)]
    if delete:
        args.append("--delete")
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def write_fixtures(src: Path) -> None:
    valid = [
        {
            "type": "meta",
            "created_at": 100.0,
            "last_active": 200.0,
            "user_context": {"age": 24},
            "asked_fields": ["age"],
            "total_clarify_count": 1,
            "accumulated_clinical_score": 2.0,
            "schema_version": 2,
        },
        {
            "type": "turn",
            "role": "user",
            "content": "mụn ở cằm",
            "timestamp": 150.0,
            "mode": "hybrid",
            "used_chunks": ["c1"],
            "metadata": {"primary_intent": "advise"},
        },
    ]
    (src / "valid.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in valid) + "\n",
        encoding="utf-8",
    )
    (src / "malformed.jsonl").write_text("{this is not json}\n", encoding="utf-8")


def main() -> None:
    with TemporaryDirectory(prefix="acnellm-migration-audit-") as tmp:
        tmp_path = Path(tmp)
        keep_src = tmp_path / "keep"
        keep_src.mkdir()
        write_fixtures(keep_src)
        keep_db = tmp_path / "keep.db"
        keep_run = run_migration(keep_src, keep_db)
        conn = sqlite3.connect(keep_db)
        try:
            session_row = conn.execute(
                "SELECT session_id, created_at, last_active, user_context, asked_fields, "
                "total_clarify_count, accumulated_clinical_score, schema_version FROM sessions"
            ).fetchone()
            turn_row = conn.execute(
                "SELECT session_id, role, content, timestamp, mode, used_chunks, metadata FROM turns"
            ).fetchone()
        finally:
            conn.close()

        delete_src = tmp_path / "delete"
        delete_src.mkdir()
        write_fixtures(delete_src)
        delete_db = tmp_path / "delete.db"
        delete_run = run_migration(delete_src, delete_db, delete=True)

        result = {
            "keep_run": {
                "returncode": keep_run.returncode,
                "stdout": keep_run.stdout.strip(),
                "stderr": keep_run.stderr.strip(),
            },
            "valid_session_preserved": bool(
                session_row
                and session_row[0] == "valid"
                and session_row[1] == 100.0
                and session_row[2] == 200.0
                and json.loads(session_row[3]) == {"age": 24}
                and json.loads(session_row[4]) == ["age"]
                and session_row[5] == 1
                and session_row[6] == 2.0
                and session_row[7] == 2
            ),
            "valid_turn_preserved": bool(
                turn_row
                and turn_row[0] == "valid"
                and turn_row[1] == "user"
                and turn_row[2] == "mụn ở cằm"
                and turn_row[3] == 150.0
                and turn_row[4] == "hybrid"
                and json.loads(turn_row[5]) == ["c1"]
                and json.loads(turn_row[6]) == {"primary_intent": "advise"}
            ),
            "malformed_skipped_without_delete": (keep_src / "malformed.jsonl").exists(),
            "delete_run": {
                "returncode": delete_run.returncode,
                "stdout": delete_run.stdout.strip(),
                "stderr": delete_run.stderr.strip(),
            },
            "valid_deleted_with_delete": not (delete_src / "valid.jsonl").exists(),
            "malformed_deleted_with_delete": not (delete_src / "malformed.jsonl").exists(),
            "risk": (
                "--delete removes malformed/skipped JSONL files too; preserve or quarantine "
                "unparsed files before deletion"
            ),
        }
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
