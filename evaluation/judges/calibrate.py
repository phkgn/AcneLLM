"""Export blind judge rows and import human correctness labels."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import random
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULT = ROOT / "evaluation/reports/judge_calibration.json"
RUBRIC = {
    "axis": "correctness",
    "scale": "1-5 integer",
    "instruction": "Chấm độ đúng của câu trả lời so với câu hỏi, độc lập với độ dài/văn phong.",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: expected an object")
        rows.append(row)
    return rows


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _result_index(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _read_jsonl(path):
        key = (str(row.get("system_id") or ""), str(row.get("sample_id") or ""))
        # Resume logs may append a later failed retry after an earlier valid
        # answer. Judged files necessarily refer to the valid answer, so never
        # let the failed retry hide it during the blind join.
        if row.get("ok") or key not in index:
            index[key] = row
    return index


def export_sheet(
    run_dir: Path,
    output_path: Path,
    *,
    size: int = 50,
    seed: int = 42,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for judged_path in sorted(run_dir.glob("*.judged.jsonl")):
        results = _result_index(
            judged_path.with_name(judged_path.name.replace(".judged.jsonl", ".results.jsonl"))
        )
        for judged in _read_jsonl(judged_path):
            pointwise = judged.get("pointwise")
            if not isinstance(pointwise, dict) or not isinstance(
                pointwise.get("correctness"), (int, float)
            ):
                continue
            sample_id = str(judged.get("sample_id") or "")
            system_id = str(judged.get("system_id") or "")
            result = results.get((system_id, sample_id), {})
            trace = result.get("trace") if isinstance(result.get("trace"), dict) else {}
            query = (
                trace.get("prepared_clean_text")
                or trace.get("query")
                or result.get("user_query")
                or ""
            )
            answer = result.get("answer") or ""
            if not sample_id or not system_id or not query or not answer:
                continue
            candidates.append(
                {
                    "sample_id": sample_id,
                    "system_id": system_id,
                    "query": str(query),
                    "answer": str(answer),
                    "rubric": RUBRIC,
                    "human_score": None,
                    "judge_file": _relative(judged_path),
                }
            )
    if not candidates:
        raise ValueError(f"No joined judged rows found in {run_dir}")
    rng = random.Random(seed)
    rng.shuffle(candidates)
    selected = candidates[: min(size, len(candidates))]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected),
        encoding="utf-8",
    )
    return selected


def _average_ranks(values: Sequence[float]) -> np.ndarray:
    order = np.argsort(np.asarray(values, dtype=float), kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    index = 0
    while index < len(order):
        end = index + 1
        while end < len(order) and values[order[end]] == values[order[index]]:
            end += 1
        ranks[order[index:end]] = (index + end - 1) / 2 + 1
        index = end
    return ranks


def _spearman(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) < 2:
        return 0.0
    left_ranks = _average_ranks(left)
    right_ranks = _average_ranks(right)
    if np.std(left_ranks) == 0 or np.std(right_ranks) == 0:
        return 0.0
    return round(float(np.corrcoef(left_ranks, right_ranks)[0, 1]), 4)


def _cohen_kappa(left: Sequence[int], right: Sequence[int]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Cohen kappa needs equal non-empty label arrays")
    labels = sorted(set(left) | set(right))
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    expected = sum(
        (left.count(label) / len(left)) * (right.count(label) / len(right))
        for label in labels
    )
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return round((observed - expected) / (1.0 - expected), 4)


def import_labels(labeled_path: Path, output_path: Path) -> dict[str, Any]:
    human_scores: list[int] = []
    judge_scores: list[int] = []
    judge_cache: dict[Path, dict[tuple[str, str], dict[str, Any]]] = {}
    for row in _read_jsonl(labeled_path):
        human = row.get("human_score")
        if not isinstance(human, int) or isinstance(human, bool) or not 1 <= human <= 5:
            raise ValueError(f"{row.get('sample_id')}: human_score must be an integer 1..5")
        raw_judge_path = row.get("judge_file")
        if not isinstance(raw_judge_path, str) or not raw_judge_path:
            raise ValueError(f"{row.get('sample_id')}: missing judge_file")
        judge_path = Path(raw_judge_path)
        judge_path = judge_path if judge_path.is_absolute() else ROOT / judge_path
        judge_path = judge_path.resolve()
        if ROOT.resolve() not in (judge_path, *judge_path.parents):
            raise ValueError("judge_file must stay inside the repository")
        if judge_path not in judge_cache:
            judge_cache[judge_path] = {
                (str(item.get("system_id") or ""), str(item.get("sample_id") or "")): item
                for item in _read_jsonl(judge_path)
            }
        key = (str(row.get("system_id") or ""), str(row.get("sample_id") or ""))
        judged = judge_cache[judge_path].get(key)
        pointwise = judged.get("pointwise") if judged else None
        judge = pointwise.get("correctness") if isinstance(pointwise, dict) else None
        if not isinstance(judge, int) or isinstance(judge, bool) or not 1 <= judge <= 5:
            raise ValueError(f"{key}: missing integer judge correctness 1..5")
        human_scores.append(human)
        judge_scores.append(judge)
    artifact = {
        "schema_version": 1,
        "source": _relative(labeled_path),
        "n": len(human_scores),
        "cohen_kappa": _cohen_kappa(human_scores, judge_scores),
        "spearman": _spearman(human_scores, judge_scores),
        "human_score_distribution": {
            str(score): human_scores.count(score) for score in range(1, 6)
        },
        "judge_score_distribution": {
            str(score): judge_scores.count(score) for score in range(1, 6)
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifact


def main(argv: Sequence[str] | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--export", action="store_true")
    mode.add_argument("--import", dest="import_path")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    if args.size < 1:
        parser.error("--size must be positive")

    if args.export:
        if args.run_dir is None:
            parser.error("--export requires --run-dir")
        run_dir = args.run_dir if args.run_dir.is_absolute() else ROOT / args.run_dir
        output = args.output or run_dir / "calibration_sheet.jsonl"
        output = output if output.is_absolute() else ROOT / output
        result = export_sheet(run_dir.resolve(), output.resolve(), size=args.size, seed=args.seed)
        print(f"Exported {len(result)} blind rows to {_relative(output)}")
        return result

    labeled = Path(args.import_path)
    labeled = labeled if labeled.is_absolute() else ROOT / labeled
    output = args.output or DEFAULT_RESULT
    output = output if output.is_absolute() else ROOT / output
    artifact = import_labels(labeled.resolve(), output.resolve())
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return artifact


if __name__ == "__main__":
    main(sys.argv[1:])
