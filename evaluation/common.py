"""Shared helpers for the evaluation harness.

Standalone từ legacy eval (scripts/eval_*.py). Chỉ phụ thuộc stdlib + pyyaml.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # repo root
EVAL_DIR = ROOT / "evaluation"
REPORTS_DIR = EVAL_DIR / "reports"
DATASETS_DIR = EVAL_DIR / "datasets"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{i} invalid JSON: {exc}") from exc
    return rows


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def corpus_versions() -> dict:
    """Snapshot version của KB artifacts (R9 trong blueprint)."""
    out: dict = {}
    bm25 = ROOT / "data" / "bm25_index.pkl"
    if bm25.exists():
        out["bm25_sha256"] = sha256_file(bm25)
    chroma = ROOT / "data" / "chroma_db"
    if chroma.exists():
        files = sorted(p for p in chroma.rglob("*") if p.is_file())
        h = hashlib.sha256()
        for p in files:
            h.update(p.name.encode())
            h.update(str(p.stat().st_size).encode())
        out["chroma_fingerprint"] = h.hexdigest()
        out["chroma_num_files"] = len(files)
    return out


def build_run_meta(extra: dict | None = None) -> dict:
    meta = {
        "timestamp": utcnow(),
        "git_commit": git_commit(),
        "python": sys.version,
        "platform": os.name,
        **corpus_versions(),
    }
    if extra:
        meta.update(extra)
    return meta


def ensure_repo_importable() -> None:
    """Cho phép import acne_llm khi chạy từ repo root mà chưa pip install -e."""
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
