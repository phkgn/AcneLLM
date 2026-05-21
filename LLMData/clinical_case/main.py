"""CLI entrypoint for clinical-case fine-tuning dataset generation/validation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from .generator import write_dataset
from .validator import validate_file


DEFAULT_OUTPUT = ROOT / "data" / "finetune" / "acne_case_structuring.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate or validate clinical-case fine-tuning JSONL"
    )
    subparsers = parser.add_subparsers(dest="command")

    generate_parser = subparsers.add_parser("generate", help="Generate curated clinical-case dataset")
    generate_parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output JSONL path",
    )
    generate_parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Write records without running safety/schema validation",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate clinical-case JSONL")
    validate_parser.add_argument("input", help="Input JSONL")
    validate_parser.add_argument("--output", help="Optional path for accepted records")

    args = parser.parse_args()

    if args.command == "generate":
        count = write_dataset(args.output, validate=not args.no_validate)
        print(json.dumps({
            "output": args.output,
            "records": count,
            "validated": not args.no_validate,
        }, ensure_ascii=False, indent=2))
        return

    if args.command == "validate":
        stats = validate_file(args.input, args.output)
        print(json.dumps({
            "total": stats.total,
            "kept": stats.kept,
            "rejected": stats.rejected,
            "reasons": stats.reasons,
        }, ensure_ascii=False, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
