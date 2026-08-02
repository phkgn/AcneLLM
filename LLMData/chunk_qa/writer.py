"""Build the final per-sample chat record and append it to the output JSONL.

Record format (matches plan §"Key Changes"):

    {
      "messages": [
        {"role": "system",    "content": "<final-answer policy>"},
        {"role": "user",      "content": "<raw_user_message>...</raw_user_message>\\n
                                          <normalized_case>{...}</normalized_case>\\n
                                          <guideline_context>...</guideline_context>"},
        {"role": "assistant", "content": "<final answer>"}
      ],
      "metadata": {
        "id": "...",
        "sample_type": "clinical_chat_response" | "<safety_kind>",
        "source_chunk_id": "...",
        "source_title": "...",
        "source_url": "...",
        "source_trust_level": "...",
        "guideline_refs": [...],
        "case_type": "...",
        "severity": "...",
        "safety_flags": [...],
        "confidence": "...",
        "rule_filter": {"passed": bool, "reason": "..."},
        "validator_version": "v1"
      }
    }

Public API:
    SYSTEM_CONTENT
    build_record(item, *, sample_type, source_chunk=None, rule_filter=...) -> dict
    build_user_prompt(raw_user_message, normalized_case, guideline_context) -> str
    DatasetWriter(path, dedup_ids=None)
        .write(record) -> bool   # False if duplicate
        .close()
    load_existing_ids(path) -> set[str]
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from pathlib import Path
from typing import Any, Iterable, Set, Union


VALIDATOR_VERSION = "v1"


# Final-answer policy. Compact summary of config/prompts/system.j2 — kept
# concise so we don't blow up token count for every sample.
SYSTEM_CONTENT = (
    "Bạn là AcneLLM, trợ lý tư vấn da mụn tiếng Việt. "
    "Trả lời như một người bạn có kiến thức da liễu đang nhắn tin: tự nhiên, "
    "gần gũi, đi thẳng vào ý chính ngay câu đầu, không chào hỏi hoặc dẫn dắt "
    "kiểu máy móc. Ca nhẹ/routine thì nói gọn và thực tế; ca phức tạp thì giải "
    "thích rõ hơn nhưng vẫn dễ đọc. Chỉ thêm cảnh báo khi thật sự cần, như thuốc "
    "kê đơn, mụn bọc/nang, sẹo, nhiễm trùng, thai kỳ hoặc cho con bú. Không chẩn "
    "đoán xác định, không kê đơn, không đưa liều thuốc kê đơn; thiếu thông tin thì "
    "hỏi thêm thay vì đoán. Ví dụ tone tốt: 'Mụn đầu đen ở mũi thường hợp với BHA "
    "hơn là kháng sinh.' hoặc 'Mụn bọc đau kiểu này dễ để lại sẹo, nên đi khám "
    "da liễu sớm.' Bám AAD 2024 + NICE NG198."
)


def build_user_prompt(
    raw_user_message: str,
    normalized_case: dict[str, Any] | str,
    guideline_context: str,
) -> str:
    """Wrap planner output + chunk context as the user message."""
    if isinstance(normalized_case, dict):
        case_text = json.dumps(normalized_case, ensure_ascii=False)
    else:
        case_text = str(normalized_case)
    return (
        f"<raw_user_message>{raw_user_message}</raw_user_message>\n"
        f"<normalized_case>{case_text}</normalized_case>\n"
        f"<guideline_context>{guideline_context}</guideline_context>"
    )


def _stable_id(
    source_chunk_id: str | None,
    raw_user_message: str,
    assistant_answer: str,
) -> str:
    h = hashlib.sha1()
    h.update((source_chunk_id or "").encode("utf-8"))
    h.update(b"\x00")
    h.update(raw_user_message.encode("utf-8"))
    h.update(b"\x00")
    h.update(assistant_answer.encode("utf-8"))
    return h.hexdigest()[:24]


def build_record(
    item: dict[str, Any],
    *,
    sample_type: str = "clinical_chat_response",
    source_chunk: dict | None = None,
    rule_filter: dict | None = None,
) -> dict:
    """Build a JSONL record from a validated item.

    `item` must already be in the canonical shape from
    `generator._validate_item()` — i.e. contain `raw_user_message`,
    `normalized_case`, `guideline_context`, `assistant_answer`, etc.
    """
    raw_user_message = item["raw_user_message"]
    normalized_case = item["normalized_case"]
    guideline_context = item["guideline_context"]
    assistant_answer = item["assistant_answer"]

    src_chunk_id = source_chunk.get("chunk_id") if source_chunk else None
    src_title = source_chunk.get("title") if source_chunk else None
    src_url = source_chunk.get("url") if source_chunk else None
    src_trust = source_chunk.get("trust_level") if source_chunk else None

    rid = _stable_id(src_chunk_id, raw_user_message, assistant_answer)

    user_prompt = build_user_prompt(raw_user_message, normalized_case, guideline_context)

    metadata = {
        "id": rid,
        "sample_type": sample_type,
        "source_chunk_id": src_chunk_id,
        "source_title": src_title,
        "source_url": src_url,
        "source_trust_level": src_trust,
        "case_type": item.get("case_type", "general"),
        "severity": item.get("severity", "unknown"),
        "safety_flags": item.get("safety_flags") or [],
        "guideline_refs": item.get("guideline_refs") or ["AAD_2024", "NICE_NG198"],
        "confidence": item.get("confidence", "medium"),
        "validator_version": VALIDATOR_VERSION,
    }
    if rule_filter is not None:
        metadata["rule_filter"] = rule_filter

    return {
        "sample_type": sample_type,
        "messages": [
            {"role": "system", "content": SYSTEM_CONTENT},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": assistant_answer},
        ],
        "metadata": metadata,
    }


class DatasetWriter:
    """Append-only JSONL writer with in-memory dedup by record id."""

    def __init__(
        self,
        path: Union[Path, str],
        dedup_ids: Iterable[str] | None = None,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fh = self.path.open("a", encoding="utf-8")
        self._seen: Set[str] = set(dedup_ids or [])

    def write(self, record: dict) -> bool:
        meta = record.get("metadata") or {}
        rid = meta.get("id")
        if not rid:
            rid = uuid.uuid4().hex[:24]
            meta["id"] = rid
            record["metadata"] = meta
        with self._lock:
            if rid in self._seen:
                return False
            self._seen.add(rid)
            self._fh.write(json.dumps(record, ensure_ascii=False))
            self._fh.write("\n")
            self._fh.flush()
        return True

    def close(self) -> None:
        with self._lock:
            try:
                self._fh.close()
            except Exception:
                pass

    def __enter__(self) -> "DatasetWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def load_existing_ids(path: Union[Path, str]) -> Set[str]:
    """Read existing JSONL and return the set of metadata.id values."""
    ids: Set[str] = set()
    p = Path(path)
    if not p.exists():
        return ids
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = (obj.get("metadata") or {}).get("id")
            if rid:
                ids.add(rid)
    return ids
