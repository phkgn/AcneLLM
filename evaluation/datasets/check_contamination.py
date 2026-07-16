"""Kiểm tra train-test contamination (R3, §5.3): n-gram overlap giữa test set và
finetune train data. Mẫu trùng → gắn cờ, cân nhắc loại khỏi D2.

Usage:
    python -m evaluation.datasets.check_contamination \
        --test evaluation/datasets/v1/d2_test.jsonl \
        [--train data/finetune/clean/acne_chat_response.train.jsonl] \
        [--ngram 8] [--threshold 0.5]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import ROOT, read_jsonl, write_jsonl, utcnow  # noqa: E402


def _norm(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text.lower())
    return re.findall(r"\w+", text, re.UNICODE)


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _train_texts(path: Path) -> list[str]:
    """Hỗ trợ cả format messages (finetune) lẫn jsonl thường."""
    texts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "messages" in row:
            texts.extend(m.get("content", "") for m in row["messages"])
        else:
            texts.append(row.get("user_query") or row.get("query") or "")
    return texts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", required=True)
    ap.add_argument("--train",
                    default="data/finetune/clean/acne_chat_response.train.jsonl")
    ap.add_argument("--ngram", type=int, default=8)
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="tỉ lệ n-gram của test sample xuất hiện trong train → flag")
    args = ap.parse_args()

    print("Building train n-gram index (có thể mất vài phút với train lớn)...")
    train_ngrams: set[tuple[str, ...]] = set()
    for text in _train_texts(ROOT / args.train):
        train_ngrams |= _ngrams(_norm(text), args.ngram)
    print(f"Train index: {len(train_ngrams):,} {args.ngram}-grams")

    flagged, rows = [], read_jsonl(ROOT / args.test)
    for row in rows:
        text = " ".join([row.get("user_query") or "",
                         row.get("reference_answer") or ""])
        grams = _ngrams(_norm(text), args.ngram)
        if not grams:
            continue
        overlap = len(grams & train_ngrams) / len(grams)
        if overlap >= args.threshold:
            flagged.append({"sample_id": row["sample_id"],
                            "overlap": round(overlap, 3),
                            "user_query": (row.get("user_query") or "")[:120]})

    out = Path(args.test).with_suffix(".contamination.json")
    out.write_text(json.dumps({
        "checked_at": utcnow(), "test": args.test, "train": args.train,
        "ngram": args.ngram, "threshold": args.threshold,
        "n_test": len(rows), "n_flagged": len(flagged), "flagged": flagged,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(flagged)}/{len(rows)} mẫu bị flag (overlap ≥ {args.threshold}) -> {out}")
    if flagged:
        print("→ Loại các mẫu này khỏi D2 hoặc chuyển sang D9 in-distribution probe.")
        sys.exit(1)


if __name__ == "__main__":
    main()
