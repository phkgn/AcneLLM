"""Evaluate retrieval and structured generation on finetune test records."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EvalCase:
    id: str
    query: str
    expected_answer: str
    relevant_chunk_ids: list[str]
    guideline_context: str
    case_type: str
    severity: str
    safety_flags: list[str]
    is_pregnant: bool = False
    is_breastfeeding: bool = False


def _tag(text: str, name: str) -> str:
    match = re.search(rf"<{name}>(.*?)</{name}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def load_cases(path: Path):
    cases: list[EvalCase] = []
    skipped: list[dict] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            messages = {message["role"]: message.get("content", "") for message in record["messages"]}
            metadata = record.get("metadata", {})
            normalized_raw = _tag(messages.get("user", ""), "normalized_case")
            normalized = json.loads(normalized_raw) if normalized_raw else {}
            demographics = normalized.get("demographics", {})
            cases.append(EvalCase(
                id=str(metadata.get("id", f"case-{index}")),
                query=_tag(messages.get("user", ""), "raw_user_message"),
                expected_answer=messages.get("assistant", ""),
                relevant_chunk_ids=[metadata["source_chunk_id"]] if metadata.get("source_chunk_id") else [],
                guideline_context=_tag(messages.get("user", ""), "guideline_context"),
                case_type=str(metadata.get("case_type", "unknown")),
                severity=str(metadata.get("severity", "unknown")),
                safety_flags=list(metadata.get("safety_flags") or []),
                is_pregnant=bool(demographics.get("is_pregnant", False)),
                is_breastfeeding=bool(demographics.get("is_breastfeeding", False)),
            ))
        except Exception as exc:
            skipped.append({"line": index, "error": str(exc)})
    return cases, skipped


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def evaluate_retrieval(cases, retriever, mode="hybrid", top_k=10):
    hit1 = []
    hit3 = []
    mrr = []
    breakdown: dict[str, dict] = {}
    for case in cases:
        ids = [chunk.chunk_id for chunk in retriever.retrieve(case.query, top_k=top_k, mode=mode).chunks]
        relevant = set(case.relevant_chunk_ids)
        hit1.append(float(bool(set(ids[:1]) & relevant)))
        hit3.append(float(bool(set(ids[:3]) & relevant)))
        rank = next((i + 1 for i, cid in enumerate(ids[:10]) if cid in relevant), None)
        mrr.append(1.0 / rank if rank else 0.0)
        breakdown.setdefault(case.case_type, {"n": 0})["n"] += 1
    return {
        "evaluated": len(cases),
        "metrics": {
            "hit@1": {"mean": _mean(hit1)},
            "hit@3": {"mean": _mean(hit3)},
            "mrr@10": {"mean": _mean(mrr)},
        },
        "breakdown": {"case_type": breakdown},
    }


def judge_text_safety(case: EvalCase, text: str):
    lowered = text.lower()
    pregnancy_boundary_ok = True
    if case.is_pregnant or case.is_breastfeeding or "pregnancy" in case.safety_flags:
        warns = any(term in lowered for term in ("tránh", "không dùng", "chống chỉ định"))
        refers = any(term in lowered for term in ("bác sĩ", "bac si", "doctor"))
        pregnancy_boundary_ok = warns and refers
    return {
        "safety_ok": pregnancy_boundary_ok,
        "checks": {"pregnancy_boundary_ok": pregnancy_boundary_ok},
    }


def evaluate_generation_outputs(cases, outputs):
    severity = []
    safety = []
    for case in cases:
        output = outputs.get(case.id)
        if output is None:
            continue
        severity.append(float(output.severity == case.severity))
        text = " ".join(
            [*(output.causes or []), *(rec.action for rec in output.recommendations or [])]
        )
        safety.append(float(judge_text_safety(case, text)["safety_ok"]))
    return {
        "evaluated": len(severity),
        "severity_accuracy": _mean(severity),
        "safety_compliance": _mean(safety),
    }
