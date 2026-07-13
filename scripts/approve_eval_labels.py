"""Helpers for approving human-reviewed retrieval labels."""
from __future__ import annotations

import json
from pathlib import Path


def _load_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
