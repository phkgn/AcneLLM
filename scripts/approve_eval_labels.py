"""Approve suggested eval labels into `relevant_chunk_ids`.

This takes the BM25-generated suggestion file and copies selected candidate IDs
into the canonical `relevant_chunk_ids` field so the eval runner can consume it.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

app = typer.Typer()


def _load_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@app.command()
def run(
    source: str = "data/eval_labels/suggested_eval_queries.jsonl",
    out: str = "data/eval_labels/approved_eval_queries.jsonl",
    mode: str = "copy_suggestions",
    top_k: int = 3,
):
    """Create an approved eval file.

    Modes:
    - copy_suggestions: move the top `top_k` suggested ids into relevant_chunk_ids
    - preserve: keep existing relevant_chunk_ids, only fill them if empty
    """
    src_path = Path(source)
    if not src_path.exists():
        logger.error(f"source not found: {source}")
        raise typer.Exit(1)

    rows = _load_jsonl(source)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    approved = 0
    preserved = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            existing = [cid for cid in row.get("relevant_chunk_ids", []) if cid]
            suggestions = [cid for cid in row.get("suggested_relevant_chunk_ids", []) if cid]

            if mode == "preserve" and existing:
                relevant = existing
                preserved += 1
            else:
                relevant = suggestions[:top_k] if suggestions else existing
                approved += 1 if relevant else 0

            row["relevant_chunk_ids"] = relevant
            row["labeling"] = {
                **row.get("labeling", {}),
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "approval_mode": mode,
                "approved_top_k": top_k,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = (
        f"# Approved eval labels\n\n"
        f"- Source: {src_path}\n"
        f"- Output: {out_path}\n"
        f"- Mode: {mode}\n"
        f"- Top-k: {top_k}\n"
        f"- Approved rows: {approved}\n"
        f"- Preserved rows: {preserved}\n"
    )
    out_path.with_suffix(".md").write_text(summary, encoding="utf-8")
    logger.success(f"✅ Approved eval labels written to {out_path}")


if __name__ == "__main__":
    app()
