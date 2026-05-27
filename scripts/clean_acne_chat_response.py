"""Clean acne_chat_response.jsonl before fine-tuning.

The cleaner keeps the source dataset immutable and writes all derived files to
data/finetune/clean/. It preserves the chat training shape while dropping weak
or unsafe samples, normalizing metadata, and splitting by source group to reduce
train/validation/test leakage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "finetune" / "acne_chat_20k.jsonl"
DEFAULT_OUT_DIR = ROOT / "data" / "finetune" / "cleanv2"
CLEANING_VERSION = "v2"


OFFTOPIC_TITLE_RX = re.compile(
    r"(?:viêm da tiếp xúc|eczema|herpes|kiến ba khoang|gàu|da đầu|khô da|"
    r"keratosis|dày sừng|phun môi|nốt ruồi|hắc lào|vảy nến|nhiễm trùng da|"
    r"viêm nang lông|triệt lông|tẩy lông|mụn cóc|mụn thịt|rãnh cười|"
    r"tắm trắng|trắng răng|hôi nách|rụng tóc|nám|tàn nhang|sẹo lồi|môi|"
    r"răng|botox|filler)",
    re.IGNORECASE,
)
ACNE_SCOPE_RX = re.compile(
    r"(?:mụn|mun|acne|trứng cá|trung ca|comedone|benzoyl|salicylic|"
    r"isotretinoin|retinoid|adapalene|tretinoin|mụn trứng cá|sẹo mụn|thâm mụn)",
    re.IGNORECASE,
)
BOILERPLATE_RX = re.compile(
    r"(?:Trang chủ|CÔNG TY|Hotline|Đã kiểm duyệt|Nguồn tham khảo|Xin lưu ý|"
    r"Bài viết nổi bật)",
    re.IGNORECASE,
)
CODE_LEAK_RX = re.compile(
    r"(?:```|\bdef\s+\w+\s*\(|\bfunction\s+\w+\s*\(|\bclass\s+\w+[\s(:]|"
    r"^\s*import\s+\w+)",
    re.IGNORECASE | re.MULTILINE,
)
CHUNK_STYLE_RX = re.compile(
    r"(?:theo\s+đoạn\s+tài\s+liệu|theo\s+tài\s+liệu|theo\s+chunk|"
    r"đoạn\s+tài\s+liệu\s+này)",
    re.IGNORECASE,
)
CONFIDENT_DIAGNOSIS_RX = re.compile(
    r"(?:chắc\s*chắn\s+bạn|bạn\s+chắc\s*chắn|chẩn\s*đoán\s+chắc\s*chắn)",
    re.IGNORECASE,
)
RX_DOSE_RX = re.compile(
    # Oral/systemic Rx: flag any dose unit including %
    # Topical OTC (adapalene, tretinoin %): NOT flagged — educational mention
    r"(?:isotretinoin|doxycycline|minocycline|lymecycline|"
    r"spironolactone|prednisolone|prednisone|tazarotene|trifarotene|"
    r"clindamycin|erythromycin|kháng\s*sinh)"
    r"[^\n.]{0,80}\b\d+(?:[.,]\d+)?\s*"
    r"(?:mg/kg|mg|mcg|viên/ngày|viên\s+mỗi|lần/ngày)",
    re.IGNORECASE,
)
SAFETY_CONTEXT_RX = re.compile(
    r"(?:không\s+tự\s+ý|không\s+nên\s+tự|bác\s+sĩ|thăm\s+khám|đi\s+khám|"
    r"kê\s+toa|chỉ\s+định|tham\s+khảo\s+ý\s+kiến|không\s+kê\s+đơn|"
    r"cần\s+được\s+theo\s+dõi)",
    re.IGNORECASE,
)
RAW_USER_RX = re.compile(r"<raw_user_message>(.*?)</raw_user_message>", re.DOTALL)


def _snake(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s\-]+", "_", text)
    text = re.sub(r"[^0-9a-zA-Z_à-ỹ]+", "", text)
    text = re.sub(r"_+", "_", text).strip("_")
    aliases = {
        "treatment_failure": "treatment_failure",
        "treatment failure": "treatment_failure",
        "risk_of_scarring": "scarring_risk",
        "scarring_risk": "scarring_risk",
        "risk_of_scar": "scarring_risk",
        "sẹo": "scarring_risk",
    }
    return aliases.get(text, text)


def _metadata(record: dict[str, Any]) -> dict[str, Any]:
    meta = record.get("metadata")
    return meta if isinstance(meta, dict) else {}


def _messages(record: dict[str, Any]) -> list[dict[str, Any]]:
    messages = record.get("messages")
    return messages if isinstance(messages, list) else []


def _role_text(record: dict[str, Any], role: str) -> str:
    parts: list[str] = []
    for message in _messages(record):
        if isinstance(message, dict) and message.get("role") == role:
            parts.append(str(message.get("content") or ""))
    return "\n".join(parts)


def _raw_user_text(user_message: str) -> str:
    match = RAW_USER_RX.search(user_message)
    if match:
        return match.group(1).strip()
    return user_message.strip()


def _message_roles(record: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(message.get("role") or "")
        for message in _messages(record)
        if isinstance(message, dict)
    )


def _training_payload_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record.get("messages"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _stable_split(group_key: str) -> str:
    bucket = int(hashlib.sha1(group_key.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 90:
        return "train"
    if bucket < 95:
        return "val"
    return "test"


def _source_group(record: dict[str, Any]) -> str:
    meta = _metadata(record)
    sample_type = str(meta.get("sample_type") or "unknown")
    case_type = str(meta.get("case_type") or "unknown")
    source_chunk_id = meta.get("source_chunk_id")
    source_title = meta.get("source_title")
    if source_chunk_id:
        return f"chunk:{source_chunk_id}"
    if source_title:
        return f"title:{source_title}"
    return f"synthetic:{sample_type}:{case_type}"


def _is_synthetic(record: dict[str, Any]) -> bool:
    meta = _metadata(record)
    if meta.get("source_chunk_id") or meta.get("source_title") or meta.get("source_url"):
        return False
    return True


def _drop_reasons(record: dict[str, Any], seen_ids: set[str], seen_payloads: set[str]) -> list[str]:
    reasons: list[str] = []
    meta = _metadata(record)
    messages = _messages(record)
    roles = _message_roles(record)
    user_message = _role_text(record, "user")
    assistant = _role_text(record, "assistant")
    raw_user = _raw_user_text(user_message)

    if not isinstance(record, dict):
        return ["bad_record_shape"]
    if not isinstance(record.get("messages"), list) or roles != ("system", "user", "assistant"):
        reasons.append("bad_message_shape")
    if not user_message.strip() or not assistant.strip():
        reasons.append("empty_user_or_assistant")

    rule_filter = meta.get("rule_filter")
    if not isinstance(rule_filter, dict) or rule_filter.get("passed") is not True:
        reasons.append("rule_filter_not_passed")
    if str(meta.get("confidence") or "").strip().lower() == "low":
        reasons.append("low_confidence")

    record_id = meta.get("id")
    if record_id and str(record_id) in seen_ids:
        reasons.append("duplicate_id")
    payload_hash = _training_payload_hash(record) if messages else ""
    if payload_hash and payload_hash in seen_payloads:
        reasons.append("duplicate_training_payload")

    if CODE_LEAK_RX.search(assistant):
        reasons.append("code_leak")
    if CHUNK_STYLE_RX.search(assistant):
        reasons.append("chunk_citation_style")
    if CONFIDENT_DIAGNOSIS_RX.search(assistant):
        reasons.append("confident_diagnosis")
    if RX_DOSE_RX.search(assistant) and not SAFETY_CONTEXT_RX.search(assistant):
        reasons.append("rx_dose_without_safety_context")

    source_title = str(meta.get("source_title") or "")
    if (
        str(meta.get("sample_type") or "") == "clinical_chat_response"
        and OFFTOPIC_TITLE_RX.search(source_title)
        and not ACNE_SCOPE_RX.search(source_title)
        and not ACNE_SCOPE_RX.search(raw_user + "\n" + assistant)
    ):
        reasons.append("offtopic_scope")
    if BOILERPLATE_RX.search(user_message) or BOILERPLATE_RX.search(assistant):
        reasons.append("boilerplate_leak")
    if len(assistant) > 1200 or len(user_message) > 2200:
        reasons.append("length_outlier")

    return reasons


def _normalize_record(record: dict[str, Any], split: str) -> dict[str, Any]:
    cleaned = dict(record)
    cleaned["messages"] = [dict(message) for message in _messages(record)]
    meta = dict(_metadata(record))

    for key in ("case_type", "severity", "confidence", "sample_type"):
        if key in meta:
            meta[key] = str(meta[key]).strip().lower()

    flags = meta.get("safety_flags") or []
    if isinstance(flags, list):
        normalized_flags = [_snake(flag) for flag in flags if _snake(flag)]
        meta["safety_flags"] = list(dict.fromkeys(normalized_flags))
    else:
        meta["safety_flags"] = []

    if _is_synthetic(record):
        meta["is_synthetic"] = True
        if not meta.get("source_trust_level"):
            meta["source_trust_level"] = "synthetic"
    else:
        meta["is_synthetic"] = False

    meta["cleaning_version"] = CLEANING_VERSION
    meta["cleaning_decision"] = "kept"
    meta["cleaning_reasons"] = []
    meta["split"] = split
    cleaned["metadata"] = meta
    return cleaned


def _bump_distributions(prefix: str, record: dict[str, Any], stats: dict[str, Counter]) -> None:
    meta = _metadata(record)
    for field in ("sample_type", "case_type", "severity", "confidence", "source_trust_level", "split"):
        value = meta.get(field)
        if value not in (None, ""):
            stats[f"{prefix}_{field}"][str(value)] += 1
    flags = meta.get("safety_flags") or []
    if isinstance(flags, list):
        for flag in flags:
            stats[f"{prefix}_safety_flags"][str(flag)] += 1


def _write_jsonl_line(handle, record: dict[str, Any]) -> None:
    handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    handle.write("\n")


def _counter_to_dict(counter: Counter, limit: int | None = None) -> dict[str, int]:
    items = counter.most_common(limit)
    return {str(k): v for k, v in items}


def _markdown_table(counter: Counter, title: str, limit: int = 30) -> str:
    lines = [f"### {title}", "", "| Value | Count |", "|---|---:|"]
    if not counter:
        lines.append("| _none_ | 0 |")
    else:
        for key, value in counter.most_common(limit):
            lines.append(f"| `{key}` | {value:,} |")
    return "\n".join(lines)


def _build_markdown_report(report: dict[str, Any]) -> str:
    generated_at = report["generated_at"]
    summary = report["summary"]
    lines = [
        "# Acne Chat Response Clean Report",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Input: `{report['input_path']}`",
        f"- Clean output: `{report['outputs']['clean']}`",
        f"- Train output: `{report['outputs']['train']}`",
        f"- Validation output: `{report['outputs']['val']}`",
        f"- Test output: `{report['outputs']['test']}`",
        "",
        "## Summary",
        "",
        f"- Total input records: **{summary['input_records']:,}**",
        f"- Kept records: **{summary['kept_records']:,}**",
        f"- Dropped records: **{summary['dropped_records']:,}**",
        f"- JSON errors: **{summary['json_errors']:,}**",
        f"- Duplicate IDs dropped: **{summary['duplicate_ids_dropped']:,}**",
        f"- Duplicate payloads dropped: **{summary['duplicate_payloads_dropped']:,}**",
        "",
        "## Drop Reasons",
        "",
        "| Reason | Count | Why |",
        "|---|---:|---|",
    ]
    reason_notes = {
        "bad_message_shape": "Chat fine-tune requires exactly system/user/assistant.",
        "empty_user_or_assistant": "Empty training turns teach no useful behavior.",
        "rule_filter_not_passed": "Generator safety validator did not approve the sample.",
        "low_confidence": "Generator marked the sample as low quality or uncertain.",
        "confident_diagnosis": "Medical safety policy avoids definitive diagnosis.",
        "code_leak": "Dataset should not teach coding behavior.",
        "chunk_citation_style": "This dataset is final chatbot response, not chunk QA.",
        "rx_dose_without_safety_context": "Avoid learning prescription dose guidance without clinical supervision.",
        "offtopic_scope": "Source/title and content are outside acne scope.",
        "boilerplate_leak": "Website boilerplate leaked into trainable text.",
        "length_outlier": "Long response/prompt is likely less chat-like and noisier.",
        "duplicate_id": "Avoid repeated samples.",
        "duplicate_training_payload": "Avoid repeated training payloads.",
    }
    drop_reasons = report["drop_reasons"]
    if drop_reasons:
        for reason, count in drop_reasons.items():
            lines.append(f"| `{reason}` | {count:,} | {reason_notes.get(reason, '')} |")
    else:
        lines.append("| _none_ | 0 | |")

    lines.extend([
        "",
        "## Distributions Before and After",
        "",
        _markdown_table(Counter(report["before"]["sample_type"]), "Before: sample_type"),
        "",
        _markdown_table(Counter(report["after"]["sample_type"]), "After: sample_type"),
        "",
        _markdown_table(Counter(report["before"]["case_type"]), "Before: case_type"),
        "",
        _markdown_table(Counter(report["after"]["case_type"]), "After: case_type"),
        "",
        _markdown_table(Counter(report["before"]["severity"]), "Before: severity"),
        "",
        _markdown_table(Counter(report["after"]["severity"]), "After: severity"),
        "",
        _markdown_table(Counter(report["before"]["confidence"]), "Before: confidence"),
        "",
        _markdown_table(Counter(report["after"]["confidence"]), "After: confidence"),
        "",
        _markdown_table(Counter(report["after"]["source_trust_level"]), "After: source_trust_level"),
        "",
        _markdown_table(Counter(report["after"]["split"]), "Split counts"),
        "",
        _markdown_table(Counter(report["after"]["safety_flags"]), "Top safety_flags", limit=40),
        "",
        "## Decisions",
        "",
        "- The original `acne_chat_response.jsonl` was not modified; all derived files live under `data/finetune/clean/`.",
        "- `confidence=low` records were removed because the generator itself marked them as weak and spot checks showed many are off acne scope.",
        "- Synthetic safety records were kept and marked with `is_synthetic=true` plus `source_trust_level=synthetic` because they train refusal and boundary behavior.",
        "- `llm_data.jsonl`, `chunk_qa.jsonl`, and `acne_case_structuring.jsonl` were not mixed into this phase.",
        "- Train/validation/test splits were assigned by stable source group hash to reduce leakage from records generated from the same source chunk/title.",
        "",
        "## Recommendation",
        "",
        "Use `acne_chat_response.clean.jsonl` if your trainer does its own split. Use the provided train/val/test files if your trainer accepts explicit split files.",
    ])
    return "\n".join(lines) + "\n"


def clean_dataset(input_path: Path, out_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "clean": out_dir / "acne_chat_response.clean.jsonl",
        "train": out_dir / "acne_chat_response.train.jsonl",
        "val": out_dir / "acne_chat_response.val.jsonl",
        "test": out_dir / "acne_chat_response.test.jsonl",
        "json_report": out_dir / "acne_chat_response.clean_report.json",
        "markdown_report": out_dir / "acne_chat_response.clean_report.md",
    }
    stats: dict[str, Counter] = defaultdict(Counter)
    summary = Counter()
    drop_samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_ids: set[str] = set()
    seen_payloads: set[str] = set()

    handles = {}
    if not dry_run:
        handles = {
            "clean": outputs["clean"].open("w", encoding="utf-8"),
            "train": outputs["train"].open("w", encoding="utf-8"),
            "val": outputs["val"].open("w", encoding="utf-8"),
            "test": outputs["test"].open("w", encoding="utf-8"),
        }

    try:
        with input_path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                summary["input_records"] += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    summary["json_errors"] += 1
                    stats["drop_reasons"]["json_error"] += 1
                    if len(drop_samples["json_error"]) < 10:
                        drop_samples["json_error"].append({"line": line_no, "error": str(exc)})
                    continue

                _bump_distributions("before", record, stats)
                reasons = _drop_reasons(record, seen_ids, seen_payloads)
                if reasons:
                    summary["dropped_records"] += 1
                    meta = _metadata(record)
                    for reason in reasons:
                        stats["drop_reasons"][reason] += 1
                        if reason == "duplicate_id":
                            summary["duplicate_ids_dropped"] += 1
                        if reason == "duplicate_training_payload":
                            summary["duplicate_payloads_dropped"] += 1
                        if len(drop_samples[reason]) < 10:
                            drop_samples[reason].append({
                                "line": line_no,
                                "id": meta.get("id"),
                                "sample_type": meta.get("sample_type"),
                                "case_type": meta.get("case_type"),
                                "severity": meta.get("severity"),
                                "source_title": meta.get("source_title"),
                                "assistant_preview": _role_text(record, "assistant")[:220],
                            })
                    continue

                record_id = _metadata(record).get("id")
                if record_id:
                    seen_ids.add(str(record_id))
                payload_hash = _training_payload_hash(record)
                seen_payloads.add(payload_hash)

                split = _stable_split(_source_group(record))
                cleaned = _normalize_record(record, split=split)
                _bump_distributions("after", cleaned, stats)
                summary["kept_records"] += 1

                if not dry_run:
                    _write_jsonl_line(handles["clean"], cleaned)
                    _write_jsonl_line(handles[split], cleaned)
    finally:
        for handle in handles.values():
            handle.close()

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cleaning_version": CLEANING_VERSION,
        "dry_run": dry_run,
        "input_path": str(input_path),
        "outputs": {key: str(value) for key, value in outputs.items()},
        "summary": {key: summary.get(key, 0) for key in (
            "input_records",
            "kept_records",
            "dropped_records",
            "json_errors",
            "duplicate_ids_dropped",
            "duplicate_payloads_dropped",
        )},
        "drop_reasons": _counter_to_dict(stats["drop_reasons"]),
        "before": {
            "sample_type": _counter_to_dict(stats["before_sample_type"]),
            "case_type": _counter_to_dict(stats["before_case_type"]),
            "severity": _counter_to_dict(stats["before_severity"]),
            "confidence": _counter_to_dict(stats["before_confidence"]),
            "source_trust_level": _counter_to_dict(stats["before_source_trust_level"]),
            "safety_flags": _counter_to_dict(stats["before_safety_flags"], limit=100),
        },
        "after": {
            "sample_type": _counter_to_dict(stats["after_sample_type"]),
            "case_type": _counter_to_dict(stats["after_case_type"]),
            "severity": _counter_to_dict(stats["after_severity"]),
            "confidence": _counter_to_dict(stats["after_confidence"]),
            "source_trust_level": _counter_to_dict(stats["after_source_trust_level"]),
            "split": _counter_to_dict(stats["after_split"]),
            "safety_flags": _counter_to_dict(stats["after_safety_flags"], limit=100),
        },
        "drop_samples": drop_samples,
    }

    if not dry_run:
        outputs["json_report"].write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        outputs["markdown_report"].write_text(_build_markdown_report(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report = clean_dataset(args.input, args.out_dir, dry_run=args.dry_run)
    summary = report["summary"]
    print(f"Input records: {summary['input_records']:,}")
    print(f"Kept records: {summary['kept_records']:,}")
    print(f"Dropped records: {summary['dropped_records']:,}")
    print(f"JSON errors: {summary['json_errors']:,}")
    print("Drop reasons:")
    for reason, count in report["drop_reasons"].items():
        print(f"  {reason}: {count:,}")
    print("Splits:")
    for split, count in report["after"]["split"].items():
        print(f"  {split}: {count:,}")
    if args.dry_run:
        print("Dry run only; no files written.")
    else:
        print(f"Clean files written to: {args.out_dir}")


if __name__ == "__main__":
    main()
