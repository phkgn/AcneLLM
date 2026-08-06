"""Cohen's κ giữa người và LLM judge — kiểm tra dụng cụ đo trước khi tin số.

Khâu 3 và 4 đều dựa trên một LLM judge. Không có κ thì mọi con số ablation
không phòng thủ được. Quy trình 3 bước:

    1. --export   lấy ngẫu nhiên N câu đã judge, ghi phiếu KHÔNG kèm điểm judge
                  (tránh anchor) + file khoá riêng
    2. người chấm điền human_<mặt> cho mọi mặt có trong phiếu
       answer_quality / role_tone 1-5 · incorrect_content / missing_content 0-3
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

# Mặt -> (thấp nhất, cao nhất). Hai mặt mới thang 0-3 và THẤP LÀ TỐT nên không
# dùng chung khoảng 1-5 được; khoảng phải khớp `_score_candidate` trong
# run_ablation, lệch một bậc là κ đo sai.
AXES: dict[str, tuple[int, int]] = {
    "answer_quality": (1, 5),
    "role_tone": (1, 5),
    "incorrect_content": (0, 3),
    "missing_content": (0, 3),
}
# Artifact chấm TRƯỚC khi tách trục chỉ có hai mặt này. Dòng thiếu hai mặt mới
# vẫn dùng được cho κ của hai mặt cũ — loại hẳn thì mất sạch 1182 dòng đã có.
CORE_AXES = ("answer_quality", "role_tone")
# Người chấm phải đọc ĐÚNG thang mà judge đã dùng — khác thang thì κ vô nghĩa.
# Một nguồn sự thật: judges/rubrics.py.
RUBRIC = {
    "answer_quality": rubrics.ANSWER_QUALITY,
    "role_tone": rubrics.ROLE_TONE,
    "incorrect_content": rubrics.INCORRECT_CONTENT,
    "missing_content": rubrics.MISSING_CONTENT,
    "luu_y": (
        "incorrect_content và missing_content THẤP LÀ TỐT, 0 = không có lỗi loại "
        "đó. Một lỗi chỉ tính vào MỘT trong hai: nói sai thì vào incorrect, "
        "không nói thì vào missing."
    ),
    "khong_cham": (
        "KHÔNG chấm độ bám tài liệu, an toàn hay từ chối trong các trục này — "
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
            judged = {
                axis: int(scorecard[axis])
                for axis in AXES
                if isinstance(scorecard.get(axis), (int, float))
                and not isinstance(scorecard.get(axis), bool)
            }
            # Thiếu mặt CỐT LÕI thì bỏ; thiếu mặt mới thì vẫn giữ, κ của mặt đó
            # tính trên số dòng ít hơn và `n` trong artifact nói rõ điều đó.
            if any(axis not in judged for axis in CORE_AXES):
                continue
            rows.append(
                {
                    "arm": arm,
                    "sample_id": str(item.get("sample_id") or ""),
                    "query": str(item.get("user_query") or ""),
                    "answer": str(item.get("answer") or ""),
                    "judge": judged,
                }
            )
    return [row for row in rows if row["sample_id"] and row["answer"]]


def stratify(
    rows: Sequence[dict[str, Any]], size: int, rng: random.Random
) -> list[dict[str, Any]]:
    """Bốc phân tầng theo (arm, answer_quality) thay vì ngẫu nhiên thuần.

    Ngẫu nhiên thuần trên phân bố lệch — 2.95 là mode 3, chỉ 18% đạt ≥4 — thì
    phiếu 50 dòng dễ toàn câu tầm tầm. κ đo được lúc đó cao một cách vô nghĩa:
    hai bên cùng chấm 3 cho mọi thứ vẫn ra κ đẹp mà không chứng minh judge phân
    biệt được tốt với tệ. Vòng tròn qua từng tầng đảm bảo cả câu 1 điểm lẫn câu
    5 điểm đều có mặt trước khi bất kỳ tầng nào được lấy dòng thứ hai.
    """
    buckets: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(
            (row["arm"], row["judge"]["answer_quality"]), []
        ).append(row)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    order = sorted(buckets)                      # tất định, không phụ thuộc dict order
    selected: list[dict[str, Any]] = []
    while len(selected) < size and any(buckets[key] for key in order):
        for key in order:
            if not buckets[key]:
                continue
            selected.append(buckets[key].pop())
            if len(selected) >= size:
                break
    rng.shuffle(selected)                        # trộn lại để người chấm không đoán ra tầng
    return selected


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
    selected = stratify(candidates, size, random.Random(seed))

    # Phiếu cho người: không điểm judge, không mã arm. Biết arm là biết
    # "cái này của model API" → thiên vị ngay.
    # Chỉ hỏi những mặt judge THẬT SỰ đã chấm cho dòng đó — bắt người chấm một
    # mặt mà judge bỏ trống thì không ghép cặp được, chỉ tốn công.
    _write_jsonl(sheet_path, [
        {
            "row_id": index,
            "query": row["query"],
            "answer": row["answer"],
            "rubric": {
                key: value for key, value in RUBRIC.items()
                if key in row["judge"] or key in ("luu_y", "khong_cham")
            },
            **{f"human_{axis}": None for axis in AXES if axis in row["judge"]},
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
        judged = key[row_id]["judge"]
        for axis, (low, high) in AXES.items():
            if axis not in judged:
                continue          # judge không chấm mặt này -> không có cặp để so
            value = row.get(f"human_{axis}")
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not low <= value <= high
            ):
                raise ValueError(
                    f"row_id {row_id}: human_{axis} phải là số nguyên "
                    f"{low}..{high} (đang là {value!r}) — chấm hết trước khi import"
                )
            human[axis].append(value)
            judge[axis].append(int(judged[axis]))

    scored = {axis: values for axis, values in human.items() if values}
    if not scored:
        raise ValueError("Không mặt nào ghép được cặp người/judge — phiếu rỗng?")

    def _axis_report(axis: str) -> dict[str, Any]:
        low, high = AXES[axis]
        weighted = _cohen_kappa(human[axis], judge[axis], weighted=True)
        return {
            "n": len(human[axis]),
            "scale": f"{low}-{high}",
            "lower_is_better": axis in rubrics.LOWER_IS_BETTER,
            "cohen_kappa": _cohen_kappa(human[axis], judge[axis]),
            "cohen_kappa_quadratic": weighted,
            "interpretation": _interpret(weighted),
            "spearman": _spearman(human[axis], judge[axis]),
            "human_distribution": {
                str(score): human[axis].count(score)
                for score in range(low, high + 1)
            },
            "judge_distribution": {
                str(score): judge[axis].count(score)
                for score in range(low, high + 1)
            },
            "mean_human_minus_judge": round(
                float(np.mean(human[axis]) - np.mean(judge[axis])), 4
            ),
        }

    artifact = {
        "schema_version": 3,
        "source": _relative(sheet_path),
        "n": max(len(values) for values in scored.values()),
        "axes": {axis: _axis_report(axis) for axis in scored},
        # Landis & Koch: dưới 0.61 là chưa "đáng kể". Mặt nào rơi vào đây thì con
        # số của nó KHÔNG nên trích ra ngoài như một phép đo.
        "khong_du_tin_cay": [
            axis for axis in scored
            if _cohen_kappa(human[axis], judge[axis], weighted=True) < 0.61
        ],
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

    # Khoảng thang phải khớp run_ablation._score_candidate, lệch là κ sai.
    assert AXES["answer_quality"] == (1, 5) and AXES["missing_content"] == (0, 3)
    assert set(rubrics.LOWER_IS_BETTER) <= set(AXES)

    # Phân tầng: phủ hết các bậc điểm trước khi lấy dòng thứ hai của bất kỳ bậc nào.
    lech = (
        [{"arm": "RRR", "judge": {"answer_quality": 3}, "id": f"m{i}"} for i in range(40)]
        + [{"arm": "RRR", "judge": {"answer_quality": 5}, "id": "hiem"}]
    )
    picked = stratify(lech, 4, random.Random(0))
    assert len(picked) == 4
    assert any(row["id"] == "hiem" for row in picked), "bốc phân tầng phải với tới bậc hiếm"
    # Tất định theo seed.
    assert [r["id"] for r in stratify(lech, 4, random.Random(0))] == \
           [r["id"] for r in stratify(lech, 4, random.Random(0))]
    # Xin nhiều hơn số dòng có thì trả về hết chứ không lặp.
    assert len(stratify(lech, 999, random.Random(0))) == len(lech)
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
