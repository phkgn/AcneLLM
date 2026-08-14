"""Append-only JSONL writer with ID deduplication."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterable


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or (record.get("metadata") or {}).get("id") or "").strip()


def load_existing_ids(path: Path | str) -> set[str]:
    ids: set[str] = set()
    source = Path(path)
    if not source.exists():
        return ids
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                sample_id = _record_id(record)
                if sample_id:
                    ids.add(sample_id)
    return ids


class DatasetWriter:
    """Thread-safe context manager that flushes every accepted record."""

    def __init__(self, path: Path | str, dedup_ids: Iterable[str] | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen = set(dedup_ids or load_existing_ids(self.path))
        self._lock = threading.Lock()
        self._handle = None

    def __enter__(self) -> "DatasetWriter":
        self._handle = self.path.open("a", encoding="utf-8", newline="\n")
        return self

    def write(self, record: dict[str, Any]) -> bool:
        sample_id = _record_id(record)
        if not sample_id:
            raise ValueError("Record thiếu id")
        with self._lock:
            if sample_id in self._seen:
                return False
            if self._handle is None:
                raise RuntimeError("DatasetWriter phải được dùng như context manager")
            self._handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._handle.flush()
            self._seen.add(sample_id)
            return True

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                self._handle.close()
                self._handle = None

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
