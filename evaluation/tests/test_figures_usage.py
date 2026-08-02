from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from evaluation.analysis.figures_usage import generate


def _write_sessions(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE turns ("
        "id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, "
        "timestamp REAL, mode TEXT, metadata TEXT)"
    )
    connection.executemany(
        "INSERT INTO turns(session_id, role, content, timestamp, mode, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                "s1",
                "user",
                "Email tôi là test@example.com, số 0912345678, hỏi về adapalene",
                1_720_000_000,
                "hybrid",
                json.dumps({"primary_intent": "knowledge"}),
            ),
            (
                "s1",
                "assistant",
                "response",
                1_720_000_010,
                "hybrid",
                "{}",
            ),
            (
                "s2",
                "user",
                "Mụn viêm đỏ cần hỏi thêm",
                1_720_604_800,
                "hybrid",
                json.dumps({"primary_intent": "clarify"}),
            ),
        ],
    )
    connection.commit()
    connection.close()


def _write_audit(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE audit_log ("
        "id INTEGER PRIMARY KEY, timestamp REAL, session_id TEXT, "
        "user_message TEXT, scope_decision TEXT)"
    )
    connection.execute(
        "INSERT INTO audit_log(timestamp, session_id, user_message, scope_decision) "
        "VALUES (?, ?, ?, ?)",
        (
            1_720_604_900,
            "s3",
            "Số điện thoại +84987654321 hỏi cách làm bánh",
            "out_of_scope",
        ),
    )
    connection.commit()
    connection.close()


def test_figures_usage_masks_pii_and_empty_db_is_graceful(
    tmp_path: Path,
) -> None:
    _write_sessions(tmp_path / "data" / "sessions.db")
    _write_audit(tmp_path / "data" / "audit.db")
    dataset = tmp_path / "evaluation" / "datasets" / "v1" / "dev_tuning.jsonl"
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(
        json.dumps({"sample_id": "1", "intent_label": "knowledge"}) + "\n",
        encoding="utf-8",
    )

    output_root = tmp_path / "artifacts"
    stale_dir = output_root / "usage"
    stale_dir.mkdir(parents=True)
    (stale_dir / "obsolete-figure.pdf").write_bytes(b"stale")

    manifest_path = generate(
        root=tmp_path,
        output_root=output_root,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifact_policy"] == "fresh_compute_no_figure_reuse"
    assert all(
        figure["status"] == "ok" for figure in manifest["figures"]
    )
    terms_path = tmp_path / "artifacts" / "usage" / "query_terms.json"
    terms = terms_path.read_text(encoding="utf-8")
    assert "test@example.com" not in terms
    assert "0912345678" not in terms
    assert "+84987654321" not in terms
    assert not (stale_dir / "obsolete-figure.pdf").exists()

    empty_manifest_path = generate(
        root=tmp_path / "empty",
        output_root=tmp_path / "empty-artifacts",
    )
    empty_manifest = json.loads(
        empty_manifest_path.read_text(encoding="utf-8")
    )
    assert all(
        figure["status"] == "skipped"
        for figure in empty_manifest["figures"]
    )
