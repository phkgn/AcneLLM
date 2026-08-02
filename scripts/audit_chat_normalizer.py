"""Audit rule-based chat normalizer coverage on acne chat JSONL data.

This script is intentionally read-only for datasets. It extracts the raw user
message, runs the same preprocessing + normalizer used by chat runtime, then
writes machine-readable and human-readable coverage reports.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from acne_llm.chat.fallback.rule_normalizer import normalize_chat_message  # noqa: E402
from acne_llm.chat.preprocess import preprocess_user_text  # noqa: E402


DEFAULT_INPUT = ROOT / "data" / "finetune" / "clean" / "acne_chat_response.clean.jsonl"
DEFAULT_JSON_REPORT = (
    ROOT / "data" / "finetune" / "clean" / "acne_chat_response.normalizer_audit_report.json"
)
DEFAULT_MD_REPORT = (
    ROOT / "data" / "finetune" / "clean" / "acne_chat_response.normalizer_audit_report.md"
)

RAW_USER_RE = re.compile(r"<raw_user_message>(.*?)</raw_user_message>", re.DOTALL | re.I)


def _pct(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count * 100 / total, 2)


def _counter_to_dict(counter: Counter[str], limit: int | None = None) -> dict[str, int]:
    items = counter.most_common(limit)
    return {key: value for key, value in items}


def _get_user_content(record: dict[str, Any]) -> str | None:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return None
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            return content if isinstance(content, str) else None
    return None


def _extract_raw_user_message(user_content: str) -> str:
    match = RAW_USER_RE.search(user_content)
    if match:
        return match.group(1).strip()
    return user_content.strip()


def _sample_payload(record: dict[str, Any], raw_user: str, normalized: Any | None = None) -> dict[str, Any]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    payload: dict[str, Any] = {
        "id": metadata.get("id"),
        "sample_type": metadata.get("sample_type"),
        "case_type": metadata.get("case_type"),
        "severity": metadata.get("severity"),
        "raw_user_message": raw_user[:500],
    }
    if normalized is not None:
        payload["normalized"] = normalized.model_dump(mode="json")
    return payload


def _add_examples(
    examples: dict[str, list[dict[str, Any]]],
    bucket: str,
    record: dict[str, Any],
    raw_user: str,
    normalized: Any | None = None,
    limit: int = 5,
) -> None:
    if len(examples[bucket]) < limit:
        examples[bucket].append(_sample_payload(record, raw_user, normalized))


def audit_dataset(input_path: Path) -> dict[str, Any]:
    stats = Counter()
    field_counts = Counter()
    context_values: dict[str, Counter[str]] = defaultdict(Counter)
    clinical_values: dict[str, Counter[str]] = defaultdict(Counter)
    metadata_values: dict[str, Counter[str]] = defaultdict(Counter)
    missing_breakdowns: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors: list[dict[str, Any]] = []

    with input_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stats["total_lines"] += 1
            line = line.strip()
            if not line:
                stats["empty_lines"] += 1
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                stats["json_errors"] += 1
                if len(errors) < 10:
                    errors.append({"line": line_no, "type": "json_error", "error": str(exc)})
                continue

            if not isinstance(record, dict):
                stats["bad_record_shape"] += 1
                continue

            user_content = _get_user_content(record)
            if not user_content:
                stats["missing_user_message"] += 1
                _add_examples(examples, "missing_user_message", record, "")
                continue

            raw_user = _extract_raw_user_message(user_content)
            clean_user = preprocess_user_text(raw_user)
            if not clean_user:
                stats["empty_user_after_preprocess"] += 1
                _add_examples(examples, "empty_user_after_preprocess", record, raw_user)
                continue

            metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
            sample_type = str(metadata.get("sample_type") or "unknown")
            case_type = str(metadata.get("case_type") or "unknown")
            for key in ("sample_type", "case_type", "severity", "confidence", "source_trust_level", "split"):
                value = metadata.get(key)
                if value is not None:
                    metadata_values[key][str(value)] += 1

            try:
                normalized = normalize_chat_message(clean_user)
            except Exception as exc:  # noqa: BLE001 - audit should collect malformed cases.
                stats["normalizer_errors"] += 1
                if len(errors) < 10:
                    errors.append(
                        {
                            "line": line_no,
                            "id": metadata.get("id"),
                            "type": "normalizer_error",
                            "error": str(exc),
                            "raw_user_message": raw_user[:500],
                        }
                    )
                continue

            stats["audited_records"] += 1
            context = normalized.context
            clinical = normalized.clinical

            if normalized.description != raw_user:
                field_counts["preprocess_changed_text"] += 1

            scalar_context = {
                "age": context.age,
                "sex": context.sex,
                "skin_type": context.skin_type,
                "duration_weeks": context.duration_weeks,
            }
            for key, value in scalar_context.items():
                if value is not None:
                    field_counts[key] += 1
                    context_values[key][str(value)] += 1

            if context.is_pregnant:
                field_counts["is_pregnant"] += 1
                context_values["is_pregnant"]["true"] += 1
            if context.is_breastfeeding:
                field_counts["is_breastfeeding"] += 1
                context_values["is_breastfeeding"]["true"] += 1

            list_context = {
                "current_products": context.current_products,
                "medications": context.medications,
            }
            for key, values in list_context.items():
                if values:
                    field_counts[key] += 1
                    context_values[key].update(values)

            if clinical is None:
                stats["no_clinical_extracted"] += 1
                missing_breakdowns["no_clinical_by_sample_type"][sample_type] += 1
                missing_breakdowns["no_clinical_by_case_type"][case_type] += 1
                _add_examples(examples, "no_clinical_extracted", record, raw_user, normalized)
                continue

            list_clinical = {
                "lesion_types": clinical.lesion_types,
                "lesion_distribution": clinical.lesion_distribution,
                "medication_history": clinical.medication_history,
                "hormonal_factors": clinical.hormonal_factors,
                "skincare_products": clinical.skincare_products,
                "red_flags_input": clinical.red_flags_input,
            }
            for key, values in list_clinical.items():
                if values:
                    field_counts[key] += 1
                    clinical_values[key].update(values)

            if clinical.inflammation_level:
                field_counts["inflammation_level"] += 1
                clinical_values["inflammation_level"][clinical.inflammation_level] += 1

            if not clinical.lesion_types:
                stats["missing_lesion_types"] += 1
                missing_breakdowns["missing_lesion_types_by_sample_type"][sample_type] += 1
                missing_breakdowns["missing_lesion_types_by_case_type"][case_type] += 1
                _add_examples(examples, "missing_lesion_types", record, raw_user, normalized)
            if not clinical.lesion_distribution:
                stats["missing_lesion_distribution"] += 1
                missing_breakdowns["missing_lesion_distribution_by_sample_type"][sample_type] += 1
                missing_breakdowns["missing_lesion_distribution_by_case_type"][case_type] += 1
                _add_examples(examples, "missing_lesion_distribution", record, raw_user, normalized)
            if clinical.red_flags_input:
                _add_examples(examples, "with_red_flags", record, raw_user, normalized)
            if context.medications:
                _add_examples(examples, "with_medications", record, raw_user, normalized)

    audited = stats["audited_records"]
    coverage = {
        key: {"count": field_counts[key], "pct": _pct(field_counts[key], audited)}
        for key in sorted(field_counts)
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_file": str(input_path),
        "stats": dict(stats),
        "coverage": coverage,
        "metadata_distributions": {
            key: _counter_to_dict(counter, 30) for key, counter in sorted(metadata_values.items())
        },
        "context_value_distributions": {
            key: _counter_to_dict(counter, 40) for key, counter in sorted(context_values.items())
        },
        "clinical_value_distributions": {
            key: _counter_to_dict(counter, 40) for key, counter in sorted(clinical_values.items())
        },
        "missing_breakdowns": {
            key: _counter_to_dict(counter, 40) for key, counter in sorted(missing_breakdowns.items())
        },
        "examples": dict(examples),
        "errors": errors,
    }


def write_json_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _md_table(rows: list[tuple[str, Any, Any]]) -> str:
    lines = ["| Field | Count | Percent |", "|---|---:|---:|"]
    for name, count, pct in rows:
        lines.append(f"| `{name}` | {count} | {pct}% |")
    return "\n".join(lines)


def _top_table(title: str, values: dict[str, int], limit: int = 20) -> list[str]:
    lines = [f"## {title}", "", "| Value | Count |", "|---|---:|"]
    for key, count in list(values.items())[:limit]:
        lines.append(f"| `{key}` | {count} |")
    if len(lines) == 4:
        lines.append("| _(none)_ | 0 |")
    lines.append("")
    return lines


def _breakdown_table(title: str, values: dict[str, int], total: int, limit: int = 20) -> list[str]:
    lines = [f"## {title}", "", "| Value | Count | Percent of bucket |", "|---|---:|---:|"]
    for key, count in list(values.items())[:limit]:
        lines.append(f"| `{key}` | {count} | {_pct(count, total)}% |")
    if len(lines) == 4:
        lines.append("| _(none)_ | 0 | 0.0% |")
    lines.append("")
    return lines


def _example_lines(title: str, examples: list[dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not examples:
        lines.append("No examples captured.")
        lines.append("")
        return lines
    for idx, example in enumerate(examples, start=1):
        lines.append(f"{idx}. `{example.get('id')}` / `{example.get('sample_type')}`")
        lines.append(f"   - User: {example.get('raw_user_message')}")
        summary = _normalized_summary(example.get("normalized"))
        if summary:
            lines.append(f"   - Extracted: {summary}")
    lines.append("")
    return lines


def _compact_values(values: Any) -> str:
    if not values:
        return ""
    if isinstance(values, list):
        return ", ".join(str(value) for value in values)
    return str(values)


def _normalized_summary(normalized: Any) -> str:
    if not isinstance(normalized, dict):
        return ""
    context = normalized.get("context") if isinstance(normalized.get("context"), dict) else {}
    clinical = normalized.get("clinical") if isinstance(normalized.get("clinical"), dict) else {}
    parts: list[str] = []
    for label, key in (
        ("age", "age"),
        ("sex", "sex"),
        ("skin", "skin_type"),
        ("duration_weeks", "duration_weeks"),
    ):
        value = context.get(key)
        if value not in (None, "", [], {}):
            parts.append(f"{label}={value}")
    for label, key in (
        ("products", "current_products"),
        ("medications", "medications"),
    ):
        value = _compact_values(context.get(key))
        if value:
            parts.append(f"{label}=[{value}]")
    for label, key in (
        ("lesions", "lesion_types"),
        ("distribution", "lesion_distribution"),
        ("inflammation", "inflammation_level"),
        ("red_flags", "red_flags_input"),
    ):
        value = _compact_values(clinical.get(key))
        if value:
            parts.append(f"{label}=[{value}]")
    return "; ".join(parts)


def write_markdown_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stats = report["stats"]
    audited = stats.get("audited_records", 0)
    coverage_rows = [
        (key, value["count"], value["pct"])
        for key, value in sorted(report["coverage"].items(), key=lambda item: item[1]["count"], reverse=True)
    ]

    lines = [
        "# Acne Chat Normalizer Audit",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Input file: `{report['input_file']}`",
        f"- Total lines: `{stats.get('total_lines', 0)}`",
        f"- Audited records: `{audited}`",
        f"- JSON errors: `{stats.get('json_errors', 0)}`",
        f"- Normalizer errors: `{stats.get('normalizer_errors', 0)}`",
        f"- No clinical extracted: `{stats.get('no_clinical_extracted', 0)}`",
        "",
        "## Field Coverage",
        "",
        _md_table(coverage_rows),
        "",
        "## Missing Clinical Details",
        "",
        "| Check | Count | Percent of audited |",
        "|---|---:|---:|",
        (
            f"| No clinical extracted | {stats.get('no_clinical_extracted', 0)} | "
            f"{_pct(stats.get('no_clinical_extracted', 0), audited)}% |"
        ),
        (
            f"| Missing lesion types | {stats.get('missing_lesion_types', 0)} | "
            f"{_pct(stats.get('missing_lesion_types', 0), audited)}% |"
        ),
        (
            f"| Missing lesion distribution | {stats.get('missing_lesion_distribution', 0)} | "
            f"{_pct(stats.get('missing_lesion_distribution', 0), audited)}% |"
        ),
        "",
    ]

    clinical = report["clinical_value_distributions"]
    context = report["context_value_distributions"]
    metadata = report["metadata_distributions"]
    missing_breakdowns = report.get("missing_breakdowns", {})

    lines.extend(
        _breakdown_table(
            "No Clinical Extracted By Case Type",
            missing_breakdowns.get("no_clinical_by_case_type", {}),
            stats.get("no_clinical_extracted", 0),
            25,
        )
    )
    lines.extend(
        _breakdown_table(
            "No Clinical Extracted By Sample Type",
            missing_breakdowns.get("no_clinical_by_sample_type", {}),
            stats.get("no_clinical_extracted", 0),
            25,
        )
    )
    lines.extend(
        _breakdown_table(
            "Missing Lesion Types By Case Type",
            missing_breakdowns.get("missing_lesion_types_by_case_type", {}),
            stats.get("missing_lesion_types", 0),
            25,
        )
    )
    lines.extend(
        _breakdown_table(
            "Missing Lesion Distribution By Case Type",
            missing_breakdowns.get("missing_lesion_distribution_by_case_type", {}),
            stats.get("missing_lesion_distribution", 0),
            25,
        )
    )

    for key in ("sample_type", "case_type", "severity", "confidence", "split"):
        lines.extend(_top_table(f"Metadata: {key}", metadata.get(key, {}), 20))
    for key in ("sex", "skin_type", "current_products", "medications"):
        lines.extend(_top_table(f"Context: {key}", context.get(key, {}), 20))
    for key in (
        "lesion_types",
        "lesion_distribution",
        "inflammation_level",
        "hormonal_factors",
        "red_flags_input",
    ):
        lines.extend(_top_table(f"Clinical: {key}", clinical.get(key, {}), 20))

    examples = report["examples"]
    for key in (
        "no_clinical_extracted",
        "missing_lesion_types",
        "missing_lesion_distribution",
        "with_red_flags",
        "with_medications",
    ):
        lines.extend(_example_lines(f"Examples: {key}", examples.get(key, [])))

    output_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input JSONL dataset.")
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--md-report", type=Path, default=DEFAULT_MD_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    report = audit_dataset(input_path)
    write_json_report(report, args.json_report.resolve())
    write_markdown_report(report, args.md_report.resolve())

    stats = report["stats"]
    print(f"Audited: {stats.get('audited_records', 0)} records")
    print(f"JSON errors: {stats.get('json_errors', 0)}")
    print(f"Normalizer errors: {stats.get('normalizer_errors', 0)}")
    print(f"JSON report: {args.json_report}")
    print(f"Markdown report: {args.md_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
