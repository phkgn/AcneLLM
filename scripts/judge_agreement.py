#!/usr/bin/env python3
"""Export a blind 40-row scorecard review and measure human/judge agreement."""
from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.metrics.scorecard import BINARY_FACES, ORDINAL_FACES  # noqa: E402


ARM_ORDER = ("z", "x", "w", "y")
DEFAULT_LIMIT = 40


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} is not a JSON object")
        rows.append(value)
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _stable_order_key(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def _review_candidates(paths: Sequence[Path]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        if artifact.get("schema_version") != 2:
            raise ValueError(f"{path} is not a bottleneck scorecard v2 artifact")
        dataset = str(artifact.get("dataset") or "")
        for arm, payload in (artifact.get("arms") or {}).items():
            for row in payload.get("items", []):
                scorecard = row.get("scorecard")
                if not row.get("ok") or not isinstance(scorecard, Mapping):
                    continue
                sample_id = str(row.get("sample_id") or "")
                review_id = hashlib.sha256(
                    f"{dataset}:{arm}:{sample_id}".encode("utf-8")
                ).hexdigest()[:16]
                if review_id in seen:
                    continue
                seen.add(review_id)
                trace = row.get("trace") if isinstance(row.get("trace"), Mapping) else {}
                candidates.append(
                    {
                        "review_id": review_id,
                        "dataset": dataset,
                        "arm": arm,
                        "sample_id": sample_id,
                        "question": row.get("user_query"),
                        "user_context": row.get("user_context") or {},
                        "expected_behavior": row.get("expected_behavior"),
                        "expected_answer_points": row.get("expected_answer_points") or [],
                        "forbidden_claims": row.get("forbidden_claims") or [],
                        "answer": row.get("answer"),
                        "contexts": [
                            chunk.get("text")
                            for chunk in trace.get("context_chunks", [])
                            if isinstance(chunk, Mapping) and chunk.get("text")
                        ],
                        "actual_intent": trace.get("primary_intent"),
                        "expected_intent": row.get("intent_label"),
                        "machine_scorecard": {
                            face: scorecard.get(face)
                            for face in (*ORDINAL_FACES, *BINARY_FACES)
                        },
                    }
                )
    return candidates


def select_stratified(
    candidates: Sequence[Mapping[str, Any]], *, limit: int, seed: int
) -> list[dict[str, Any]]:
    """Round-robin arms, then fill deterministically; Y must be represented."""
    if len(candidates) < limit:
        raise ValueError(
            f"need {limit} judged rows, but only {len(candidates)} are available"
        )
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_arm[str(candidate.get("arm"))].append(dict(candidate))
    for arm_rows in by_arm.values():
        arm_rows.sort(
            key=lambda row: _stable_order_key(seed, str(row.get("review_id")))
        )
    if not by_arm.get("y"):
        raise ValueError("agreement sample must include arm Y")

    selected: list[dict[str, Any]] = []
    while len(selected) < limit:
        progressed = False
        for arm in ARM_ORDER:
            rows = by_arm.get(arm) or []
            if rows and len(selected) < limit:
                selected.append(rows.pop(0))
                progressed = True
        if not progressed:
            break
    if len(selected) != limit:
        raise ValueError(f"could select only {len(selected)} of {limit} rows")
    return selected


def export_review(
    inputs: Sequence[Path], output: Path, key_output: Path, *, limit: int, seed: int
) -> dict[str, Any]:
    selected = select_stratified(_review_candidates(inputs), limit=limit, seed=seed)
    review_rows = []
    key_rows = []
    for row in selected:
        review_rows.append(
            {
                key: row[key]
                for key in (
                    "review_id",
                    "dataset",
                    "arm",
                    "sample_id",
                    "question",
                    "user_context",
                    "expected_behavior",
                    "expected_answer_points",
                    "forbidden_claims",
                    "answer",
                    "contexts",
                    "actual_intent",
                    "expected_intent",
                )
            }
            | {
                "human_scores": {
                    "grounding_support": None,
                    "safety_pass": None,
                    "refusal_fidelity": None,
                    "answer_quality": None,
                    "role_tone": None,
                },
                "review_notes": "",
            }
        )
        key_rows.append(
            {
                "review_id": row["review_id"],
                "dataset": row["dataset"],
                "arm": row["arm"],
                "sample_id": row["sample_id"],
                "machine_scorecard": row["machine_scorecard"],
            }
        )
    _write_jsonl(output, review_rows)
    _write_json(
        key_output,
        {
            "schema_version": 1,
            "blind_review": str(output),
            "rows": key_rows,
        },
    )
    return {
        "rows": len(review_rows),
        "arm_counts": {
            arm: sum(row["arm"] == arm for row in review_rows) for arm in ARM_ORDER
        },
        "review": str(output),
        "key": str(key_output),
    }


def _ranks(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average = (index + 1 + end) / 2
        for original, _ in ordered[index:end]:
            ranks[original] = average
        index = end
    return ranks


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_ranks, right_ranks = _ranks(left), _ranks(right)
    left_mean = statistics.fmean(left_ranks)
    right_mean = statistics.fmean(right_ranks)
    numerator = sum(
        (a - left_mean) * (b - right_mean)
        for a, b in zip(left_ranks, right_ranks)
    )
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left_ranks)
        * sum((b - right_mean) ** 2 for b in right_ranks)
    )
    return round(numerator / denominator, 4) if denominator else None


def cohen_kappa(left: Sequence[bool], right: Sequence[bool]) -> float | None:
    if len(left) != len(right) or not left:
        return None
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_true = sum(left) / len(left)
    right_true = sum(right) / len(right)
    expected = left_true * right_true + (1 - left_true) * (1 - right_true)
    if expected == 1:
        return 1.0 if observed == 1 else None
    return round((observed - expected) / (1 - expected), 4)


def _agreement(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    faces: dict[str, Any] = {}
    for face in ORDINAL_FACES:
        pairs = [
            (row["machine"][face], row["human"][face])
            for row in rows
            if isinstance(row["machine"].get(face), (int, float))
            and isinstance(row["human"].get(face), (int, float))
        ]
        coefficient = spearman(
            [float(pair[0]) for pair in pairs],
            [float(pair[1]) for pair in pairs],
        )
        faces[face] = {
            "method": "spearman",
            "n": len(pairs),
            "coefficient": coefficient,
            "threshold": 0.4,
            "acceptable": coefficient is not None and coefficient >= 0.4,
        }
    for face in BINARY_FACES:
        pairs = [
            (row["machine"][face], row["human"][face])
            for row in rows
            if isinstance(row["machine"].get(face), bool)
            and isinstance(row["human"].get(face), bool)
        ]
        machine = [bool(pair[0]) for pair in pairs]
        human = [bool(pair[1]) for pair in pairs]
        kappa = cohen_kappa(machine, human)
        threshold = 0.6 if face == "safety_pass" else 0.4
        faces[face] = {
            "method": "cohen_kappa_and_exact_agreement",
            "n": len(pairs),
            "cohen_kappa": kappa,
            "exact_agreement": (
                round(sum(a == b for a, b in zip(machine, human)) / len(pairs), 4)
                if pairs
                else None
            ),
            "threshold": threshold,
            "acceptable": kappa is not None and kappa >= threshold,
        }
    return {
        "faces": faces,
        "judge_usable": all(face["acceptable"] for face in faces.values()),
    }


def score_review(review: Path, key: Path, output: Path) -> dict[str, Any]:
    human_rows = _read_jsonl(review)
    key_payload = json.loads(key.read_text(encoding="utf-8"))
    key_by_id = {row["review_id"]: row for row in key_payload.get("rows", [])}
    merged: list[dict[str, Any]] = []
    for row in human_rows:
        review_id = row.get("review_id")
        machine = key_by_id.get(review_id)
        if machine is None:
            raise ValueError(f"review_id {review_id!r} is missing from the key")
        human = row.get("human_scores")
        if not isinstance(human, Mapping):
            raise ValueError(f"review_id {review_id!r} has no human_scores object")
        for face in ORDINAL_FACES:
            value = human.get(face)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 1 <= value <= 5:
                raise ValueError(f"review_id {review_id!r}: {face} must be 1..5")
        for face in BINARY_FACES:
            value = human.get(face)
            if not isinstance(value, bool):
                raise ValueError(f"review_id {review_id!r}: {face} must be boolean")
        merged.append(
            {
                "arm": machine["arm"],
                "machine": machine["machine_scorecard"],
                "human": dict(human),
            }
        )
    result = {
        "schema_version": 1,
        "rows": len(merged),
        "overall": _agreement(merged),
        "arm_y": _agreement([row for row in merged if row["arm"] == "y"]),
    }
    _write_json(output, result)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export")
    export.add_argument("--input", action="append", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--key-output", required=True)
    export.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    export.add_argument("--seed", type=int, default=42)
    score = subparsers.add_parser("score")
    score.add_argument("--review", required=True)
    score.add_argument("--key", required=True)
    score.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "export" and args.limit < 1:
        parser.error("--limit must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if args.command == "export":
        result = export_review(
            [Path(value).resolve() for value in args.input],
            Path(args.output).resolve(),
            Path(args.key_output).resolve(),
            limit=args.limit,
            seed=args.seed,
        )
    else:
        result = score_review(
            Path(args.review).resolve(),
            Path(args.key).resolve(),
            Path(args.output).resolve(),
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
