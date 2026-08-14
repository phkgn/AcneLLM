"""Report distribution and gate statistics for ROLE dataset JSONL files.

Usage:
    python datagen/report_stats.py datagen/output/v4_role/v4_role.smoke.jsonl
    python datagen/report_stats.py datagen/output/v4_role/v4_role.train.jsonl
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    kinds = Counter(str(row.get("sample_kind")) for row in rows)
    styles = Counter(str(row.get("input_style")) for row in rows)
    gate_status = Counter(
        "pass" if (row.get("gate_results") or {}).get("pass") else "fail"
        for row in rows
    )
    grounded = [
        float(row["grounded_sentence_rate"])
        for row in rows
        if row.get("grounded_sentence_rate") is not None
    ]
    return {
        "records": len(rows),
        "sample_kind": dict(sorted(kinds.items())),
        "input_style": dict(sorted(styles.items())),
        "gate_status": dict(sorted(gate_status.items())),
        "grounded_rate_mean": round(sum(grounded) / len(grounded), 4) if grounded else None,
    }


def _print_section(title: str, values: dict[str, Any]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for key, value in values.items():
        print(f"{key:32} {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--json", action="store_true", help="In JSON thay vì bảng text.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = summarize(read_jsonl(args.jsonl))
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    print(f"Records: {summary['records']}")
    _print_section("Sample kind", summary["sample_kind"])
    _print_section("Input style", summary["input_style"])
    _print_section("Gate status", summary["gate_status"])
    print(f"\nGrounded rate mean: {summary['grounded_rate_mean']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

