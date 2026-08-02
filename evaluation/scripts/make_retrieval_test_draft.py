"""Create the deterministic D8 manual-intent review draft."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "evaluation/datasets/v1/retrieval_test.jsonl"
DEFAULT_OUTPUT = ROOT / "evaluation/datasets/drafts/v1/retrieval_test.draft.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: expected an object")
        rows.append(row)
    return rows


def make_draft(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**row, "intent_label": None} for row in rows]


def main() -> Path:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    source = args.source if args.source.is_absolute() else ROOT / args.source
    rows = make_draft(read_jsonl(source))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    os.replace(temporary, output)
    print(f"Wrote {len(rows)} rows to {output.relative_to(ROOT)}")
    return output


if __name__ == "__main__":
    main()
