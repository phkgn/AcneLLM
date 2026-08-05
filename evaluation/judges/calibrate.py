"""Cohen's κ giữa người và LLM judge — kiểm tra dụng cụ đo trước khi tin số.

Khâu 3 và 4 đều dựa trên một LLM judge. Không có κ thì mọi con số ablation
không phòng thủ được. Quy trình 3 bước:

    1. --export   lấy ngẫu nhiên N câu đã judge, ghi phiếu KHÔNG kèm điểm judge
                  (tránh anchor) + file khoá riêng
    2. người chấm điền human_answer_quality / human_role_tone (1-5)
    3. --import   ghép lại, tính κ thường + κ có trọng số bậc hai + Spearman

Usage:
    python -m evaluation.judges.calibrate --export \\
        --results evaluation/reports/full_eval/ablation/results.json --size 50
    # → calibration_sheet.jsonl (đưa người chấm) + calibration_key.jsonl (đừng mở)
    python -m evaluation.judges.calibrate --import <sheet đã chấm>
"""
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
# Phải khớp từng chữ với rubric trong run_ablation._judge_prompt. Lệch rubric thì
# κ đo độ lệch đề bài, không đo chất lượng judge.
from evaluation.judges import rubrics

AXES = ("answer_quality", "role_tone")
# Người chấm phải đọc ĐÚNG thang mà judge đã dùng — khác thang thì κ vô nghĩa.
# Một nguồn sự thật: judges/rubrics.py.
RUBRIC = {
    "answer_quality": rubrics.ANSWER_QUALITY,
    "role_tone": rubrics.ROLE_TONE,
    "khong_cham": (
        "KHÔNG chấm độ bám tài liệu, an toàn hay từ chối trong hai trục này — "
        "ba mặt đó đo bằng metric độc lập"
    ),
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


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def collect_judged(results_path: Path) -> list[dict[str, Any]]:
    """Mọi câu đã có điểm judge, từ mọi arm trong artifact ablation."""
    report = json.loads(results_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for arm, payload in (report.get("arms") or {}).items():
        for item in payload.get("items") or []:
            scorecard = item.get("scorecard")
            if not item.get("ok") or not isinstance(scorecard, dict):
                continue
            if any(
                not isinstance(scorecard.get(axis), (int, float)) for axis in AXES
            ):
                continue
            rows.append(
                {
                    "arm": arm,
                    "sample_id": str(item.get("sample_id") or ""),
                    "query": str(item.get("user_query") or ""),
                    "answer": str(item.get("answer") or ""),
                    "judge": {axis: int(scorecard[axis]) for axis in AXES},
                }
            )
    return [row for row in rows if row["sample_id"] and row["answer"]]


def export_sheet(
    results_path: Path,
    sheet_path: Path,
    key_path: Path,
    *,
    size: int = 50,
    seed: int = 42,
) -> list[dict[str, Any]]:
    candidates = collect_judged(results_path)
    if not candidates:
        raise ValueError(f"Không có dòng nào đã judge trong {results_path}")
    rng = random.Random(seed)
    rng.shuffle(candidates)
    selected = candidates[: min(size, len(candidates))]

    # Phiếu cho người: không điểm judge, không mã arm. Biết arm là biết
    # "cái này của model API" → thiên vị ngay.
    _write_jsonl(sheet_path, [
        {
            "row_id": index,
            "query": row["query"],
            "answer": row["answer"],
            "rubric": RUBRIC,
            "human_answer_quality": None,
            "human_role_tone": None,
        }
        for index, row in enumerate(selected)
    ])
    _write_jsonl(key_path, [
        {
            "row_id": index,
            "arm": row["arm"],
            "sample_id": row["sample_id"],
            "judge": row["judge"],
        }
        for index, row in enumerate(selected)
    ])
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


def _cohen_kappa(
    left: Sequence[int],
    right: Sequence[int],
    *,
    weighted: bool = False,
) -> float:
    """κ thường (weighted=False) hoặc κ trọng số bậc hai (weighted=True).

    Thang 1-5 là thang thứ tự: lệch 4 vs 5 nhẹ hơn nhiều so với 1 vs 5, nhưng κ
    thường coi hai cái như nhau. Báo cả hai; κ trọng số mới là số nên trích dẫn.
    """
    if len(left) != len(right) or not left:
        raise ValueError("Cohen kappa cần hai mảng nhãn cùng độ dài, khác rỗng")
    labels = sorted(set(left) | set(right))
    if len(labels) == 1:
        return 1.0
    span = (len(labels) - 1) ** 2
    position = {label: index for index, label in enumerate(labels)}

    def distance(a: int, b: int) -> float:
        if not weighted:
            return 0.0 if a == b else 1.0
        return (position[a] - position[b]) ** 2 / span

    n = len(left)
    observed = sum(distance(a, b) for a, b in zip(left, right)) / n
    expected = sum(
        (left.count(a) / n) * (right.count(b) / n) * distance(a, b)
        for a in labels
        for b in labels
    )
    if expected == 0.0:
        return 1.0 if observed == 0.0 else 0.0
    return round(1.0 - observed / expected, 4)


def _interpret(kappa: float) -> str:
    """Landis & Koch 1977."""
    for threshold, label in (
        (0.81, "gần như hoàn toàn đồng thuận"),
        (0.61, "đồng thuận đáng kể"),
        (0.41, "đồng thuận vừa phải"),
        (0.21, "đồng thuận yếu"),
        (0.01, "đồng thuận rất yếu"),
    ):
        if kappa >= threshold:
            return label
    return "không hơn ngẫu nhiên"


def import_labels(
    sheet_path: Path,
    key_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    key = {row["row_id"]: row for row in _read_jsonl(key_path)}
    human: dict[str, list[int]] = {axis: [] for axis in AXES}
    judge: dict[str, list[int]] = {axis: [] for axis in AXES}
    for row in _read_jsonl(sheet_path):
        row_id = row.get("row_id")
        if row_id not in key:
            raise ValueError(f"row_id {row_id} không có trong file khoá")
        for axis in AXES:
            value = row.get(f"human_{axis}")
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
                raise ValueError(
                    f"row_id {row_id}: human_{axis} phải là số nguyên 1..5 "
                    f"(đang là {value!r}) — chấm hết trước khi import"
                )
            human[axis].append(value)
            judge[axis].append(int(key[row_id]["judge"][axis]))

    artifact = {
        "schema_version": 2,
        "source": _relative(sheet_path),
        "n": len(human[AXES[0]]),
        "axes": {
            axis: {
                "cohen_kappa": _cohen_kappa(human[axis], judge[axis]),
                "cohen_kappa_quadratic": _cohen_kappa(
                    human[axis], judge[axis], weighted=True
                ),
                "interpretation": _interpret(
                    _cohen_kappa(human[axis], judge[axis], weighted=True)
                ),
                "spearman": _spearman(human[axis], judge[axis]),
                "human_distribution": {
                    str(score): human[axis].count(score) for score in range(1, 6)
                },
                "judge_distribution": {
                    str(score): judge[axis].count(score) for score in range(1, 6)
                },
                "mean_human_minus_judge": round(
                    float(np.mean(human[axis]) - np.mean(judge[axis])), 4
                ),
            }
            for axis in AXES
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return artifact


def demo() -> None:
    assert _cohen_kappa([1, 2, 3], [1, 2, 3]) == 1.0
    # Lệch 1 bậc trên thang thứ tự: κ trọng số phải cao hơn κ thường.
    near = ([1, 2, 3, 4, 5], [1, 2, 3, 4, 4])
    assert _cohen_kappa(*near, weighted=True) > _cohen_kappa(*near)
    # Lệch tối đa: κ trọng số phải tệ hơn hẳn.
    far = ([1, 1, 5, 5], [5, 5, 1, 1])
    assert _cohen_kappa(*far, weighted=True) < 0
    assert _interpret(0.85).startswith("gần như")
    assert _spearman([1, 2, 3], [1, 2, 3]) == 1.0
    print("calibrate demo OK")


def main(argv: Sequence[str] | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--export", action="store_true")
    mode.add_argument("--import", dest="import_path")
    mode.add_argument("--demo", action="store_true")
    parser.add_argument("--results", type=Path, help="ablation/results.json")
    parser.add_argument("--sheet", type=Path)
    parser.add_argument("--key", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    if args.size < 1:
        parser.error("--size phải dương")

    def _abs(path: Path) -> Path:
        return (path if path.is_absolute() else ROOT / path).resolve()

    if args.demo:
        demo()
        return {}

    if args.export:
        if args.results is None:
            parser.error("--export cần --results <ablation/results.json>")
        results = _abs(args.results)
        sheet = _abs(args.sheet) if args.sheet else results.parent / "calibration_sheet.jsonl"
        key = _abs(args.key) if args.key else results.parent / "calibration_key.jsonl"
        rows = export_sheet(results, sheet, key, size=args.size, seed=args.seed)
        print(f"Xuất {len(rows)} dòng mù → {_relative(sheet)}")
        print(f"File khoá (ĐỪNG MỞ trước khi chấm xong) → {_relative(key)}")
        return rows

    sheet = _abs(Path(args.import_path))
    key = _abs(args.key) if args.key else sheet.with_name("calibration_key.jsonl")
    output = _abs(args.output) if args.output else DEFAULT_RESULT
    artifact = import_labels(sheet, key, output)
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return artifact


if __name__ == "__main__":
    main(sys.argv[1:])
