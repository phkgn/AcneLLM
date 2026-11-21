"""Create deterministic, stratified train/validation/holdout splits."""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from ..config import Config
from ..writer import iter_jsonl

SPLIT_RATIOS = {"train": 0.85, "val": 0.08, "holdout": 0.07}
SAFETY_HOLDOUT_CASES = {"R8_meta_jailbreak", "B2_missing_answer", "B4_conflicting_docs"}


def _split_sizes(total: int, minimum_holdout: int) -> dict[str, int]:
    if total <= 0:
        raise ValueError("Cannot split an empty dataset")
    exact = {name: total * ratio for name, ratio in SPLIT_RATIOS.items()}
    sizes = {name: int(value) for name, value in exact.items()}
    order = {name: index for index, name in enumerate(SPLIT_RATIOS)}
    for name in sorted(SPLIT_RATIOS, key=lambda item: (-(exact[item] - sizes[item]), order[item])):
        if sum(sizes.values()) == total:
            break
        sizes[name] += 1

    if sizes["holdout"] < minimum_holdout:
        needed = minimum_holdout - sizes["holdout"]
        for donor in ("train", "val"):
            movable = max(0, sizes[donor] - (1 if donor == "train" else 0))
            moved = min(needed, movable)
            sizes[donor] -= moved
            sizes["holdout"] += moved
            needed -= moved
            if needed == 0:
                break
        if needed:
            raise ValueError("Dataset is too small to reserve required safety holdout cases")
    return sizes


def _allocate_by_case(
    counts: dict[str, int],
    total_slots: int,
    *,
    required: Iterable[str] = (),
) -> dict[str, int]:
    """Allocate exact slots proportionally, subject to per-case capacity and minima."""
    total = sum(counts.values())
    allocation = {case: 0 for case in counts}
    for case in required:
        if counts.get(case, 0) > 0:
            allocation[case] = 1
    if sum(allocation.values()) > total_slots:
        raise ValueError("Not enough holdout slots for all required safety cases")

    ideal = {
        case: (counts[case] * total_slots / total if total else 0.0)
        for case in counts
    }
    while sum(allocation.values()) < total_slots:
        candidates = [case for case in counts if allocation[case] < counts[case]]
        if not candidates:
            raise ValueError("Split allocation exceeds available records")
        selected = min(candidates, key=lambda case: (-(ideal[case] - allocation[case]), case))
        allocation[selected] += 1
    return allocation


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def split(cfg: Config, seed: int = 42) -> dict[str, Any]:
    """Split accepted raw records with exact global sizes and no cross-split IDs."""
    records = list(iter_jsonl(cfg.train_path))
    ids = [record.get("id") for record in records]
    if any(not isinstance(record_id, str) or not record_id for record_id in ids):
        raise ValueError("Every input record must have a non-empty string id")
    duplicates = [record_id for record_id, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate input ids prevent leakage-safe splitting: {duplicates[:3]}")

    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        case = record.get("sample_kind")
        if not isinstance(case, str) or not case:
            raise ValueError(f"Record {record.get('id')!r} has no sample_kind")
        by_case[case].append(record)

    present_safety = sorted(SAFETY_HOLDOUT_CASES & set(by_case))
    sizes = _split_sizes(len(records), len(present_safety))
    counts = {case: len(rows) for case, rows in by_case.items()}
    holdout_quota = _allocate_by_case(
        counts,
        sizes["holdout"],
        required=present_safety,
    )
    remaining_counts = {case: counts[case] - holdout_quota[case] for case in counts}
    val_quota = _allocate_by_case(remaining_counts, sizes["val"])

    rng = random.Random(seed)
    split_records: dict[str, list[dict[str, Any]]] = {"train": [], "val": [], "holdout": []}
    for case in sorted(by_case):
        rows = list(by_case[case])
        rng.shuffle(rows)
        holdout_end = holdout_quota[case]
        val_end = holdout_end + val_quota[case]
        split_records["holdout"].extend(rows[:holdout_end])
        split_records["val"].extend(rows[holdout_end:val_end])
        split_records["train"].extend(rows[val_end:])

    for name in split_records:
        rng.shuffle(split_records[name])

    id_sets = {
        name: {str(record["id"]) for record in rows}
        for name, rows in split_records.items()
    }
    if (
        id_sets["train"] & id_sets["val"]
        or id_sets["train"] & id_sets["holdout"]
        or id_sets["val"] & id_sets["holdout"]
        or len(set().union(*id_sets.values())) != len(records)
    ):
        raise RuntimeError("Split leakage invariant failed")

    _write_jsonl(cfg.train_split_path, split_records["train"])
    _write_jsonl(cfg.val_split_path, split_records["val"])
    _write_jsonl(cfg.holdout_split_path, split_records["holdout"])
    return {
        "seed": seed,
        "total": len(records),
        "counts": {name: len(rows) for name, rows in split_records.items()},
        "safety_holdout_cases": sorted(
            {str(row["sample_kind"]) for row in split_records["holdout"]}
            & SAFETY_HOLDOUT_CASES
        ),
        "leakage": 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = split(Config(), seed=args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

