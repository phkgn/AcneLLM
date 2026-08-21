"""Export the training split to a parity-verified LLaMA-Factory dataset."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from ..anchor import anchor_sha256, assert_parity
from ..config import Config
from ..gates import schema_valid
from ..writer import iter_jsonl


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _token_estimate(messages: list[dict[str, str]]) -> tuple[int, int]:
    """Return a deterministic character-based token estimate for the dataset card."""
    input_chars = sum(len(message["content"]) for message in messages if message["role"] != "assistant")
    output_chars = sum(len(message["content"]) for message in messages if message["role"] == "assistant")
    return (input_chars + 3) // 4, (output_chars + 3) // 4


def _dataset_card(
    *,
    count: int,
    case_counts: Counter[str],
    anchor_hash: str,
    input_tokens: int,
    output_tokens: int,
    seed: int,
) -> str:
    distribution = "\n".join(
        f"| {case} | {case_counts[case]} |" for case in sorted(case_counts)
    )
    coverage = "\n".join(
        [
            "| Role identity and limits | R1, R6, R8 |",
            "| Audience depth and tone | R2, R3, R4, R5, R7, R9 |",
            "| Special-population safety | R10 |",
            "| Grounding and abstention | B1, B2, B3, B4, B5 |",
            "| Knowledge preservation | K1 |",
        ]
    )
    return f"""# AcneLLM ROLE LoRA dataset

- Format: LLaMA-Factory ShareGPT messages (`system`, `user`, `assistant`)
- Training records: {count}
- Split seed: {seed}
- Generated card date: {date.today().isoformat()}
- Anchor SHA-256: `{anchor_hash}`
- Estimated input tokens: {input_tokens}
- Estimated output tokens: {output_tokens}

## Training distribution

| Case | Records |
|---|---:|
{distribution}

## Coverage matrix

| Rule family | Cases |
|---|---|
{coverage}

Token counts are deterministic character-based estimates (approximately four characters per token).
"""


def _system_ok(system: str, anchor: str) -> bool:
    """System prompt của bản ghi có hợp lệ để xuất không.

    Tách thành hàm riêng để v2 override được: v2 rải BA biến thể anchor trong
    cùng một dataset (`roledatav2/config.py::ANCHOR_VARIANT_PATHS`), nên phép so
    bằng một chuỗi duy nhất ở đây làm export chết ngay bản ghi mang biến thể B
    hoặc C. v1 chỉ có một anchor nên hành vi không đổi.
    """
    return system == anchor


def export(cfg: Config) -> dict[str, Any]:
    """Export train.jsonl after independently rechecking schema and system parity."""
    anchor = assert_parity(cfg)
    records = list(iter_jsonl(cfg.train_split_path))
    if not records:
        raise ValueError(f"Training split is empty or missing: {cfg.train_split_path}")

    seen: set[str] = set()
    exported: list[dict[str, Any]] = []
    case_counts: Counter[str] = Counter()
    input_tokens = 0
    output_tokens = 0
    for record in records:
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("Every export record must have a non-empty id")
        if record_id in seen:
            raise ValueError(f"Duplicate id in training split: {record_id}")
        seen.add(record_id)
        if not schema_valid(record):
            raise ValueError(f"Invalid message schema for record {record_id}")
        messages = record["messages"]
        if not _system_ok(messages[0]["content"], anchor):
            raise ValueError(f"System parity failure during export for record {record_id}")
        exported.append({"id": record_id, "messages": messages})
        case_counts[str(record.get("sample_kind") or "unknown")] += 1
        estimated_in, estimated_out = _token_estimate(messages)
        input_tokens += estimated_in
        output_tokens += estimated_out

    cfg.export_dir.mkdir(parents=True, exist_ok=True)
    with cfg.export_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in exported:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    dataset_info = {
        "acnellm_role_lora": {
            "file_name": cfg.export_path.name,
            "formatting": "sharegpt",
            "columns": {"messages": "messages"},
            "tags": {
                "role_tag": "role",
                "content_tag": "content",
                "user_tag": "user",
                "assistant_tag": "assistant",
                "system_tag": "system",
            },
        }
    }
    _write_json(cfg.dataset_info_path, dataset_info)
    digest = hashlib.sha256(cfg.export_path.read_bytes()).hexdigest()
    cfg.checksum_path.write_text(f"{digest}  export/{cfg.export_path.name}\n", encoding="ascii")
    cfg.dataset_card_path.write_text(
        _dataset_card(
            count=len(exported),
            case_counts=case_counts,
            anchor_hash=anchor_sha256(anchor),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            seed=cfg.seed,
        ),
        encoding="utf-8",
    )
    return {
        "records": len(exported),
        "anchor_sha256": anchor_sha256(anchor),
        "checksum_sha256": digest,
        "output": str(cfg.export_path),
    }


def main() -> int:
    result = export(Config())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
