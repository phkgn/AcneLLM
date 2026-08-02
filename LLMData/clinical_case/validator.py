"""Validate clinical-case chat JSONL before fine-tuning.

Expected record format:
    {
      "messages": [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "free-form patient message"},
        {"role": "assistant", "content": "{... ClinicalCaseTrainingOutput JSON ...}"}
      ]
    }
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .schema import ClinicalCaseTrainingOutput


_RX_DOSE_RE = re.compile(
    r"(?:isotretinoin|tretinoin|adapalene|tazarotene|doxycycline|"
    r"minocycline|tetracycline|lymecycline|clindamycin|erythromycin|"
    r"spironolactone)"
    r"[^\n]{0,90}\d+(?:[.,]\d+)?\s*(?:mg/kg|mg|mcg|%|viên|lần/ngày|ngày|tuần)",
    re.IGNORECASE | re.UNICODE,
)
_SELF_RX_RE = re.compile(
    r"(?:tự\s*(?:mua|dùng|uống|bôi)|mua\s+về\s+dùng)[^\n]{0,80}"
    r"(?:isotretinoin|kháng\s*sinh|antibiotic|doxycycline|minocycline|"
    r"tetracycline|clindamycin|erythromycin)",
    re.IGNORECASE | re.UNICODE,
)
_PREGNANCY_UNSAFE = (
    "isotretinoin", "tretinoin", "adapalene", "retinoid", "retinol",
    "tazarotene", "doxycycline", "minocycline", "tetracycline",
)
_ANTIBIOTIC_TERMS = (
    "kháng sinh", "antibiotic", "doxycycline", "minocycline",
    "tetracycline", "lymecycline", "clindamycin", "erythromycin",
)
_ANTIBIOTIC_BOUNDARY_TERMS = (
    "benzoyl peroxide", "bpo", "bác sĩ", "da liễu", "kê đơn",
    "không tự", "theo dõi", "prescription",
)
_NEGATION_TERMS = ("không", "không nên", "tránh", "đừng", "không được")


@dataclass
class ValidationStats:
    total: int = 0
    kept: int = 0
    rejected: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def add_reject(self, reason: str) -> None:
        self.rejected += 1
        self.reasons[reason] = self.reasons.get(reason, 0) + 1


def _assistant_content(record: dict[str, Any]) -> str:
    messages = record.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            return str(msg.get("content") or "")
    return ""


def _all_output_text(output: ClinicalCaseTrainingOutput) -> str:
    # Medication safety should inspect human-facing recommendation text. Machine
    # flags like requests_isotretinoin_self_use are allowed labels, not advice.
    chunks: list[str] = [output.guideline_alignment.notes]
    for rec in output.recommendations:
        chunks.extend([rec.action, rec.rationale or "", " ".join(rec.guideline_refs)])
    return " ".join(chunks).lower()


def _safety_violation(output: ClinicalCaseTrainingOutput) -> str | None:
    text = _all_output_text(output)
    case = output.normalized_case
    if _RX_DOSE_RE.search(text):
        return "rx_dose_or_frequency"
    if _has_unnegated_self_rx(text):
        return "self_use_rx_or_antibiotic"
    if case.demographics.is_pregnant or case.demographics.is_breastfeeding:
        if any(term in text for term in _PREGNANCY_UNSAFE):
            return "pregnancy_breastfeeding_unsafe_drug"
    if output.severity == "severe":
        has_referral = any(
            rec.category == "see_doctor" or "bác sĩ" in rec.action.lower() or "da liễu" in rec.action.lower()
            for rec in output.recommendations
        )
        if not has_referral:
            return "severe_without_referral"
    has_antibiotic = any(term in text for term in _ANTIBIOTIC_TERMS)
    if has_antibiotic and not any(term in text for term in _ANTIBIOTIC_BOUNDARY_TERMS):
        return "antibiotic_without_boundary"
    return None


def _has_unnegated_self_rx(text: str) -> bool:
    for match in _SELF_RX_RE.finditer(text):
        prefix = text[max(0, match.start() - 24):match.start()]
        context = prefix + match.group(0)
        if any(term in context for term in _NEGATION_TERMS):
            continue
        return True
    return False


def validate_record(record: dict[str, Any]) -> tuple[bool, str, ClinicalCaseTrainingOutput | None]:
    content = _assistant_content(record)
    if not content:
        return False, "missing_assistant_content", None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return False, "assistant_content_not_json", None
    try:
        output = ClinicalCaseTrainingOutput.model_validate(payload)
    except ValidationError:
        return False, "assistant_schema_invalid", None
    violation = _safety_violation(output)
    if violation:
        return False, violation, output
    return True, "ok", output


def validate_file(input_path: str | Path, output_path: str | Path | None = None) -> ValidationStats:
    stats = ValidationStats()
    inp = Path(input_path)
    out = Path(output_path) if output_path else None
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("", encoding="utf-8")

    with inp.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            stats.total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                stats.add_reject("record_not_json")
                continue
            ok, reason, _ = validate_record(record)
            if not ok:
                stats.add_reject(reason)
                continue
            stats.kept += 1
            if out:
                with out.open("a", encoding="utf-8") as wf:
                    wf.write(json.dumps(record, ensure_ascii=False) + "\n")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate clinical-case fine-tuning JSONL")
    parser.add_argument("input", help="Input JSONL")
    parser.add_argument("--output", help="Optional path for accepted records")
    args = parser.parse_args()
    stats = validate_file(args.input, args.output)
    print(json.dumps({
        "total": stats.total,
        "kept": stats.kept,
        "rejected": stats.rejected,
        "reasons": stats.reasons,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
