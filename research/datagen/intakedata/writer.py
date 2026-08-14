"""Append-only JSONL writer with content-ID dedup and audit logging."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterator


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            yield value


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Atomically replace a derived JSONL artifact such as a train/val split."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
    temporary.replace(path)


class DatasetWriter:
    """Thread-safe append writer that resumes from existing deterministic IDs."""

    def __init__(self, path: Path, audit_path: Path) -> None:
        self.path = Path(path)
        self.audit_path = Path(audit_path)
        self._ids: set[str] = set()
        self._handle = None
        self._audit_handle = None
        self._lock = threading.Lock()

    def load_existing_ids(self) -> set[str]:
        ids: set[str] = set()
        for record in iter_jsonl(self.path):
            record_id = record.get("id")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"Record without a valid id in {self.path}")
            if record_id in ids:
                raise ValueError(f"Duplicate id {record_id!r} in {self.path}")
            ids.add(record_id)
        self._ids = ids
        return set(ids)

    @property
    def existing_ids(self) -> set[str]:
        return set(self._ids)

    def __enter__(self) -> "DatasetWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.load_existing_ids()
        self._handle = self.path.open("a", encoding="utf-8", newline="\n")
        self._audit_handle = self.audit_path.open("a", encoding="utf-8", newline="\n")
        return self

    def append(self, record: dict[str, Any]) -> bool:
        if self._handle is None:
            raise RuntimeError("DatasetWriter must be used as a context manager")
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("record.id must be a non-empty string")
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            if record_id in self._ids:
                return False
            self._handle.write(payload + "\n")
            self._handle.flush()
            self._ids.add(record_id)
        return True

    def audit(self, entry: dict[str, Any]) -> None:
        if self._audit_handle is None:
            raise RuntimeError("DatasetWriter must be used as a context manager")
        payload = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._audit_handle.write(payload + "\n")
            self._audit_handle.flush()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        if self._audit_handle is not None:
            self._audit_handle.close()
            self._audit_handle = None
