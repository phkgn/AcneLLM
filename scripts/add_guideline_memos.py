"""Merge curated internal guideline memos into data/raw/documents.jsonl.

This avoids recrawling web sources when we need high-trust guideline chunks for
RAG. The memo file must contain DocumentRaw-shaped JSONL records.

Usage:
    python -m scripts.add_guideline_memos
    python -m scripts.add_guideline_memos --force
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from acne_llm.schemas.kb import DocumentRaw


DEFAULT_MEMO_PATH = ROOT / "data" / "guidelines" / "acne_guideline_memo.jsonl"
DEFAULT_DOCS_PATH = ROOT / "data" / "raw" / "documents.jsonl"

app = typer.Typer(add_completion=False)


def _load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


@app.command()
def run(
    memo_path: Path = typer.Option(DEFAULT_MEMO_PATH, help="Guideline memo JSONL"),
    docs_path: Path = typer.Option(DEFAULT_DOCS_PATH, help="Target documents.jsonl"),
    force: bool = typer.Option(False, "--force", help="Replace existing memo docs by doc_id"),
) -> None:
    memo_records = _load_jsonl(memo_path)
    if not memo_records:
        raise typer.BadParameter(f"No memo records found: {memo_path}")

    memos: list[DocumentRaw] = []
    for record in memo_records:
        memos.append(DocumentRaw.model_validate(record))

    docs_path.parent.mkdir(parents=True, exist_ok=True)
    existing_records = _load_jsonl(docs_path)
    memo_ids = {m.doc_id for m in memos}

    if force:
        kept_existing = [
            record for record in existing_records
            if record.get("doc_id") not in memo_ids
        ]
    else:
        existing_ids = {record.get("doc_id") for record in existing_records}
        memos = [m for m in memos if m.doc_id not in existing_ids]
        kept_existing = existing_records

    tmp_path = docs_path.with_name(f"{docs_path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for record in kept_existing:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        for memo in memos:
            f.write(memo.model_dump_json() + "\n")
    tmp_path.replace(docs_path)

    logger.success(
        "Merged guideline memos: added_or_replaced={} target={}",
        len(memos),
        docs_path,
    )
    if not force and not memos:
        logger.info("All memo doc_ids already exist. Use --force to replace them.")


if __name__ == "__main__":
    app()
