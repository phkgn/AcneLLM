from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from evaluation.common import ROOT, read_jsonl, sha256_file
from evaluation.datasets.check_contamination import _ngrams, _norm, _train_texts
from evaluation.datasets.registry import validate_file
from evaluation.validate.types import CheckResult


def normalize_query(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").casefold()
    value = "".join(
        char for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(re.findall(r"\w+", value, re.UNICODE))


def _near(a: str, b: str, threshold: float = 0.94) -> bool:
    if not a or not b:
        return False
    ratio = min(len(a), len(b)) / max(len(a), len(b))
    return ratio >= 0.75 and SequenceMatcher(None, a, b).ratio() >= threshold


def _specific_missing_info_case(row: dict[str, Any]) -> bool:
    query = normalize_query(str(row.get("user_query") or ""))
    missing_markers = (
        "chua ro",
        "khong ro",
        "khong biet",
        "khong chac",
        "nen mo ta them",
        "can hoi them",
    )
    expected = row.get("expected_answer_points") or []
    treatment_terms = (
        "isotretinoin",
        "tretinoin",
        "adapalene",
        "benzoyl",
        "salicylic",
        "aha",
        "bha",
        "kháng sinh",
        "retinoid",
    )
    joined = " ".join(str(value).casefold() for value in expected)
    return (
        row.get("intent_label") == "clarify"
        and any(marker in query for marker in missing_markers)
        and (len(expected) >= 5 or any(term in joined for term in treatment_terms))
    )


def _router_bait(row: dict[str, Any]) -> bool:
    query = str(row.get("user_query") or "").casefold()
    markers = (
        "ignore previous",
        "bỏ qua mọi",
        "act as",
        "đóng vai",
        "dan mode",
        "developer mode",
        "đừng từ chối",
        "hãy từ chối",
    )
    return any(marker in query for marker in markers)


def audit_datasets(
    dataset_dir: Path,
    target_path: Path,
    train_path: Path | None = None,
    *,
    ngram: int = 8,
    threshold: float = 0.5,
) -> tuple[CheckResult, dict[str, Any], list[dict[str, Any]]]:
    files = sorted(dataset_dir.glob("*.jsonl"))
    report: dict[str, Any] = {
        "dataset_dir": str(dataset_dir),
        "target": str(target_path),
        "files": {},
        "cross_file_duplicates": [],
        "target_leakage": [],
        "contamination": {
            "train": str(train_path) if train_path else None,
            "ngram": ngram,
            "threshold": threshold,
            "status": "SKIPPED",
        },
    }
    human_queue: list[dict[str, Any]] = []
    critical: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    all_exact: dict[str, list[tuple[str, str, str | None]]] = {}
    rows_by_path: dict[Path, list[dict[str, Any]]] = {}

    manifest_path = dataset_dir / "MANIFEST.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            critical.append({
                "message": "MANIFEST.json is invalid JSON.",
                "detail": str(exc),
                "file": str(manifest_path),
            })
    elif target_path.parent.resolve() == dataset_dir.resolve():
        critical.append({
            "message": "Target dataset is not frozen: MANIFEST.json is missing.",
            "file": str(manifest_path),
        })

    for path in files:
        rows = read_jsonl(path)
        rows_by_path[path] = rows
        schema_errors = validate_file(path)
        ids = [str(row.get("sample_id")) for row in rows]
        exact_seen: dict[str, list[dict[str, Any]]] = {}
        contradictory: list[dict[str, Any]] = []
        near_duplicates: list[dict[str, Any]] = []
        status_counts: dict[str, int] = {}
        for row in rows:
            status = str(row.get("annotation_status") or "missing")
            status_counts[status] = status_counts.get(status, 0) + 1
            norm = normalize_query(str(row.get("user_query") or ""))
            exact_seen.setdefault(norm, []).append(row)
            all_exact.setdefault(norm, []).append(
                (path.name, str(row.get("sample_id")), row.get("intent_label"))
            )
            if _specific_missing_info_case(row):
                human_queue.append({
                    "case_id": row.get("sample_id"),
                    "file": str(path),
                    "reason": "Missing-information query has overly specific expected points.",
                })
            if _router_bait(row):
                human_queue.append({
                    "case_id": row.get("sample_id"),
                    "file": str(path),
                    "reason": "Router keyword bait; verify label from semantics, not trigger words.",
                })
        exact_duplicates = [
            {
                "query": query,
                "case_ids": [row.get("sample_id") for row in grouped],
            }
            for query, grouped in exact_seen.items()
            if query and len(grouped) > 1
            and not all(row.get("parent_sample_id") for row in grouped[1:])
        ]
        for grouped in exact_seen.values():
            labels = {
                str(row.get("intent_label"))
                for row in grouped
                if row.get("intent_label") is not None
            }
            if len(labels) > 1:
                contradictory.append({
                    "case_ids": [row.get("sample_id") for row in grouped],
                    "labels": sorted(labels),
                    "query": grouped[0].get("user_query"),
                })
        originals = [row for row in rows if not row.get("parent_sample_id")]
        for index, left in enumerate(originals):
            left_norm = normalize_query(str(left.get("user_query") or ""))
            for right in originals[index + 1:]:
                right_norm = normalize_query(str(right.get("user_query") or ""))
                if not _near(left_norm, right_norm):
                    continue
                item = {
                    "case_ids": [left.get("sample_id"), right.get("sample_id")],
                    "similarity": round(SequenceMatcher(None, left_norm, right_norm).ratio(), 4),
                    "labels": [left.get("intent_label"), right.get("intent_label")],
                }
                near_duplicates.append(item)
                if left.get("intent_label") != right.get("intent_label"):
                    contradictory.append(item)
        expected_hash = (manifest.get("files") or {}).get(path.name)
        current_hash = sha256_file(path)
        frozen = expected_hash == current_hash if expected_hash else False
        file_report = {
            "n": len(rows),
            "schema_errors": schema_errors,
            "annotation_status": status_counts,
            "exact_duplicates": exact_duplicates,
            "near_duplicates": near_duplicates,
            "contradictory_labels": contradictory,
            "sha256": current_hash,
            "manifest_sha256": expected_hash,
            "frozen": frozen,
        }
        report["files"][path.name] = file_report
        if schema_errors:
            critical.append({
                "message": "Dataset schema validation failed.",
                "file": str(path),
                "errors": schema_errors[:50],
            })
        if exact_duplicates or contradictory:
            critical.append({
                "message": "Duplicate or contradictory labels found.",
                "file": str(path),
                "duplicates": exact_duplicates[:25],
                "contradictions": contradictory[:25],
            })
        if path.resolve() == target_path.resolve() and not frozen:
            critical.append({
                "message": "Target dataset SHA-256 is not pinned by MANIFEST.json.",
                "file": str(path),
                "sha256": current_hash,
            })
        non_approved = sum(
            count for status, count in status_counts.items()
            if status != "approved"
        )
        if non_approved:
            warnings.append({
                "message": "Dataset contains rows that are not human-approved.",
                "file": str(path),
                "annotation_status": status_counts,
            })

    for query, locations in all_exact.items():
        files_seen = {item[0] for item in locations}
        if query and len(files_seen) > 1:
            item = {"query": query, "locations": locations}
            report["cross_file_duplicates"].append(item)
            if any(name == target_path.name for name in files_seen):
                report["target_leakage"].append(item)
    if report["target_leakage"]:
        critical.append({
            "message": "Target queries appear verbatim in other evaluation splits.",
            "cases": report["target_leakage"][:50],
        })

    if train_path and train_path.exists():
        train_ngrams: set[tuple[str, ...]] = set()
        for text in _train_texts(train_path):
            train_ngrams |= _ngrams(_norm(text), ngram)
        contamination_files: dict[str, list[dict[str, Any]]] = {}
        for path, rows in rows_by_path.items():
            flagged: list[dict[str, Any]] = []
            for row in rows:
                text = " ".join([
                    str(row.get("user_query") or ""),
                    str(row.get("reference_answer") or ""),
                ])
                grams = _ngrams(_norm(text), ngram)
                if not grams:
                    continue
                overlap = len(grams & train_ngrams) / len(grams)
                if overlap >= threshold:
                    flagged.append({
                        "case_id": row.get("sample_id"),
                        "overlap": round(overlap, 4),
                    })
            contamination_files[path.name] = flagged
        report["contamination"] = {
            "status": "CHECKED",
            "train": str(train_path),
            "train_sha256": sha256_file(train_path),
            "ngram": ngram,
            "threshold": threshold,
            "files": contamination_files,
        }
        target_flags = contamination_files.get(target_path.name, [])
        if target_flags:
            critical.append({
                "message": "Target dataset overlaps finetune train data.",
                "file": str(target_path),
                "cases": target_flags[:100],
                "n": len(target_flags),
            })
    else:
        warnings.append({
            "message": "Train contamination check was skipped because train data is unavailable.",
            "file": str(train_path) if train_path else None,
        })

    if human_queue:
        warnings.append({
            "message": "Dataset cases require targeted human review.",
            "n": len(human_queue),
            "cases": human_queue[:100],
        })
    if critical:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"
    evidence = critical + warnings
    if not evidence:
        evidence = [{
            "message": "All v1 datasets passed schema, freeze, duplicate and contamination checks.",
            "n_files": len(files),
        }]
    return CheckResult(
        "dataset_validity",
        status,
        evidence,
        critical=bool(critical),
    ), report, human_queue


def default_train_path() -> Path | None:
    candidates = [
        ROOT / "data" / "finetune" / "clean" / "acne_chat_response.train.jsonl",
        ROOT / "data" / "finetune" / "cleanv3" / "acne_chat_response.train.jsonl",
    ]
    return next((path for path in candidates if path.exists()), None)
