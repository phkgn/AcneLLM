"""Merge chat fine-tuning datasets with deterministic sampling ratios."""
from __future__ import annotations

import json
import random
from pathlib import Path

import typer

app = typer.Typer()


def _load_records(path: Path, allowed_splits: set[str]) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            split = (record.get("metadata") or {}).get("split", "train")
            if split in allowed_splits:
                records.append(record)
    return records


def _take(records: list[dict], n: int, rng: random.Random) -> list[dict]:
    if n <= 0 or not records:
        return []
    if n >= len(records):
        out = list(records)
        rng.shuffle(out)
        return out
    return rng.sample(records, n)


@app.command()
def main(
    llm_only: str = typer.Option("data/finetune/llm_only_chatml.jsonl", "--llm-only"),
    hybrid: str = typer.Option("data/finetune/hybrid_chatml.jsonl", "--hybrid"),
    qa: str = typer.Option("data/finetune/chunk_qa.jsonl", "--qa"),
    output: str = typer.Option("data/finetune/train_mix_chatml.jsonl", "--output"),
    ratios: str = typer.Option("0.25,0.50,0.25", "--ratios", help="llm_only,hybrid,qa"),
    splits: str = typer.Option("train", "--splits", help="Comma-separated splits to include"),
    seed: int = typer.Option(3407, "--seed"),
) -> None:
    ratio_values = [float(part.strip()) for part in ratios.split(",")]
    if len(ratio_values) != 3 or any(value < 0 for value in ratio_values) or sum(ratio_values) <= 0:
        raise typer.BadParameter("--ratios must be three non-negative numbers")
    total_ratio = sum(ratio_values)
    ratio_values = [value / total_ratio for value in ratio_values]

    allowed_splits = {part.strip() for part in splits.split(",") if part.strip()}
    rng = random.Random(seed)
    sources = [
        ("llm_only", Path(llm_only), ratio_values[0]),
        ("hybrid", Path(hybrid), ratio_values[1]),
        ("qa", Path(qa), ratio_values[2]),
    ]
    loaded = [(name, _load_records(path, allowed_splits), ratio) for name, path, ratio in sources]
    active = [(name, records, ratio) for name, records, ratio in loaded if records and ratio > 0]
    if not active:
        raise RuntimeError("No input records found for requested splits.")

    max_total = min(int(len(records) / ratio) for _, records, ratio in active)
    merged: list[dict] = []
    counts: dict[str, int] = {}
    for name, records, ratio in active:
        n = min(len(records), max(1, int(round(max_total * ratio))))
        picked = _take(records, n, rng)
        counts[name] = len(picked)
        merged.extend(picked)
    rng.shuffle(merged)

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for record in merged:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    typer.echo(f"Wrote {len(merged)} records to {out_path}")
    typer.echo(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    app()
