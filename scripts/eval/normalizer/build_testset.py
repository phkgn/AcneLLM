"""Build a normalizer evaluation test-set from the finetune data.

Extracts (raw_user_message, gold normalized_case, metadata) triples from
``data/finetune/cleanv3_gen.jsonl`` and writes a compact JSONL test-set.

The sample is *stratified* by ``metadata.severity`` and ``metadata.case_type``
so the evaluation covers mild/moderate/severe and the various case types in
proportion, and is *seeded* for reproducibility.

NOTE: the gold labels are LLM-generated (deepseek) — treat the resulting set as
a SILVER standard for agreement / regression testing, not an infallible oracle.
Hand-verify a subset if you need a true gold set.

Usage:
    python scripts/eval/normalizer/build_testset.py --n 1000 --seed 42
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "data" / "finetune" / "cleanv3_gen.jsonl"

RAW_RE = re.compile(r"<raw_user_message>(.*?)</raw_user_message>", re.S)
NORM_RE = re.compile(r"<normalized_case>(.*?)</normalized_case>", re.S)


def iter_records(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            user = next(
                (m["content"] for m in rec.get("messages", []) if m.get("role") == "user"),
                "",
            )
            raw = RAW_RE.search(user)
            norm = NORM_RE.search(user)
            if not (raw and norm):
                continue
            try:
                gold = json.loads(norm.group(1))
            except json.JSONDecodeError:
                continue
            meta = rec.get("metadata", {}) or {}
            yield {
                "id": meta.get("id"),
                "raw": raw.group(1).strip(),
                "gold": gold,
                "severity": meta.get("severity", "unknown"),
                "case_type": meta.get("case_type", "unknown"),
            }


def stratified_sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    if n >= len(rows):
        rng.shuffle(rows)
        return rows
    # bucket by (severity, case_type)
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[(r["severity"], r["case_type"])].append(r)
    for b in buckets.values():
        rng.shuffle(b)
    # proportional allocation with largest-remainder rounding
    total = len(rows)
    keys = list(buckets.keys())
    exact = {k: len(buckets[k]) / total * n for k in keys}
    alloc = {k: int(exact[k]) for k in keys}
    remainder = n - sum(alloc.values())
    for k in sorted(keys, key=lambda k: exact[k] - alloc[k], reverse=True)[:remainder]:
        alloc[k] += 1
    out: list[dict] = []
    for k in keys:
        out.extend(buckets[k][: alloc[k]])
    rng.shuffle(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000, help="test-set size")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "testset.jsonl",
    )
    args = ap.parse_args()

    rows = list(iter_records(args.src))
    print(f"parsed {len(rows)} usable records from {args.src.name}")
    sample = stratified_sample(rows, args.n, args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sample)
    with args.out.open("w", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())

    # quick stratification report
    from collections import Counter
    sev = Counter(r["severity"] for r in sample)
    print(f"wrote {len(sample)} rows -> {args.out}")
    print("severity mix:", dict(sev))


if __name__ == "__main__":
    main()
