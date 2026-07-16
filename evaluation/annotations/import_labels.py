"""Import nhãn human đã chấm + giải mã blind mapping → human_labels.jsonl.

Tính luôn: human means per system, Spearman correlation với judge (calibration §7),
và intra-rater agreement nếu có file retest.

Usage:
    python -m evaluation.annotations.import_labels --run-dir evaluation/reports/main_2x2_t3 \
        [--retest evaluation/reports/main_2x2_t3/annotation/blind_tasks_retest.csv]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import read_jsonl, write_jsonl  # noqa: E402

AXES = ["answers_question", "no_contradiction", "safe",
        "complete_vs_expected", "natural_vietnamese"]


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 5:
        return None
    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = ranks(x), ranks(y)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 4) if den else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--retest", default=None)
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    ann = run_dir / "annotation"
    mapping = json.loads((ann / "SECRET_mapping.json").read_text(encoding="utf-8"))["mapping"]
    rows = _read_csv(ann / "blind_tasks.csv")

    labels = []
    for row in rows:
        blind_id = row["blind_id"]
        system_id = mapping[blind_id]["system_id"]
        sample_id = blind_id.split("__")[0]
        scores = {}
        for axis in AXES:
            try:
                scores[axis] = int(row[axis])
            except (ValueError, KeyError):
                scores[axis] = None
        labels.append({"sample_id": sample_id, "system_id": system_id,
                       "blind_id": blind_id, "scores": scores,
                       "notes": row.get("notes", "")})
    write_jsonl(ann / "human_labels.jsonl", labels)

    # Human means per system
    by_system: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for lb in labels:
        for axis, v in lb["scores"].items():
            if v is not None:
                by_system[lb["system_id"]][axis].append(v)
    print("Human means per system:")
    for system, axes in sorted(by_system.items()):
        print(f"  {system}: " + ", ".join(f"{a}={mean(v):.2f}" for a, v in axes.items()))

    # Calibration human ↔ judge (correctness ~ answers_question, safety ~ safe)
    for system in by_system:
        judged_path = run_dir / f"{system}.judged.jsonl"
        if not judged_path.exists():
            continue
        judged = {r["sample_id"]: r for r in read_jsonl(judged_path)}
        pairs = [(lb["scores"]["answers_question"],
                  (judged.get(lb["sample_id"], {}).get("pointwise") or {}).get("correctness"))
                 for lb in labels if lb["system_id"] == system]
        pairs = [(h, j) for h, j in pairs if h is not None and j is not None]
        if pairs:
            rho = spearman([float(h) for h, _ in pairs], [float(j) for _, j in pairs])
            print(f"  calib {system}: Spearman human↔judge (correctness) = {rho} "
                  f"(n={len(pairs)}) {'⚠ <0.6 — tăng human review' if rho and rho < 0.6 else ''}")

    # Intra-rater retest
    if args.retest:
        retest = {r["blind_id"]: r for r in _read_csv(Path(args.retest))}
        agree, total = 0, 0
        for row in rows:
            other = retest.get(row["blind_id"])
            if not other:
                continue
            for axis in AXES:
                if row.get(axis) and other.get(axis):
                    total += 1
                    agree += row[axis] == other[axis]
        if total:
            print(f"Intra-rater exact agreement: {agree / total:.3f} (n={total})")


if __name__ == "__main__":
    main()
