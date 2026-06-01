#!/usr/bin/env python3
"""Xuất các ca extractor != nhãn để SOÁT TAY — tách lỗi code vs lỗi nhãn.

Mục đích: con số eval trộn (extractor sai + nhãn DeepSeek sai). Script này dump
từng ca lệch ra file dễ đọc, mỗi ca ghi text + gold + pred + chừa cột để bạn
đánh dấu "C" (lỗi Code) hay "N" (lỗi Nhãn). Đọc ~50 ca là ước lượng được tỉ lệ.

Output: data/extraction_errors_review.txt (người đọc) + .jsonl (máy đọc lại).

Usage:
    python scripts/dump_extraction_errors.py --golden data/golden_extraction_gen.jsonl --field inflammation --n 50
    python scripts/dump_extraction_errors.py --golden ... --field all --n 80
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acne_llm.chat.extraction_confidence import extract_with_confidence  # noqa: E402

SCALAR = ("skin_type", "inflammation")
LISTF = ("lesions", "distribution", "products")
GOLD_KEY = {"lesions": "lesions", "distribution": "distribution", "products": "products"}


def _load(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _pred(ec, field):
    if field == "skin_type":
        return ec.skin_type.value, ec.skin_type.confidence
    if field == "inflammation":
        return ec.inflammation.value, ec.inflammation.confidence
    if field == "lesions":
        return sorted(ec.lesion_types.values), ec.lesion_types.max_confidence
    if field == "distribution":
        return sorted(ec.distribution.values), ec.distribution.max_confidence
    if field == "products":
        return sorted(ec.products.values), ec.products.max_confidence
    return None, 0.0


def _gold(r, field):
    if field in SCALAR:
        return r.get(field)
    return sorted(r.get(GOLD_KEY[field], []) or [])


def _differs(field, g, p):
    if field in SCALAR:
        return g != p
    return set(g) != set(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="data/golden_extraction_gen.jsonl")
    ap.add_argument("--field", default="all",
                    help="skin_type|inflammation|lesions|distribution|products|all")
    ap.add_argument("--n", type=int, default=50, help="số ca lệch xuất ra mỗi field")
    ap.add_argument("--out", default="data/extraction_errors_review.txt")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    path = (ROOT / args.golden) if not Path(args.golden).is_absolute() else Path(args.golden)
    rows = _load(path)
    fields = LISTF + SCALAR if args.field == "all" else (args.field,)
    random.seed(args.seed)

    out_txt = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out_jsonl = out_txt.with_suffix(".jsonl")
    fh_txt = open(out_txt, "w", encoding="utf-8")
    fh_js = open(out_jsonl, "w", encoding="utf-8")

    fh_txt.write("# SOÁT TAY ca lệch — đánh dấu cột [?] = C (lỗi Code) / N (lỗi Nhãn)\n")
    fh_txt.write("# Quy ước: gold = nhãn DeepSeek, pred = extractor trích ra.\n\n")

    summary = {}
    for field in fields:
        diffs = []
        for r in rows:
            text = r.get("text", "")
            if not text:
                continue
            ec = extract_with_confidence(text)
            p, conf = _pred(ec, field)
            g = _gold(r, field)
            if _differs(field, g, p):
                diffs.append((r, g, p, conf))
        random.shuffle(diffs)
        sample = diffs[: args.n]
        summary[field] = (len(diffs), len(sample))

        fh_txt.write(f"\n{'='*70}\n## FIELD: {field}  (lệch {len(diffs)} ca, xuất {len(sample)})\n{'='*70}\n")
        for i, (r, g, p, conf) in enumerate(sample, 1):
            fh_txt.write(f"\n[{i:3d}] [?]___  conf={round(conf,2)}\n")
            fh_txt.write(f"  text : {r['text']}\n")
            fh_txt.write(f"  gold : {g}\n")
            fh_txt.write(f"  pred : {p}\n")
            fh_js.write(json.dumps({"field": field, "text": r["text"],
                                    "gold": g, "pred": p, "conf": round(conf, 3),
                                    "verdict": ""}, ensure_ascii=False) + "\n")

    fh_txt.close()
    fh_js.close()

    print("=== ĐÃ XUẤT CA LỆCH ===")
    for f, (total, shown) in summary.items():
        print(f"  {f:13s}: lệch {total} ca, xuất {shown} để soát")
    print(f"\nĐọc & đánh dấu tại: {out_txt}")
    print(f"(điền C/N vào dấu [?]___ — C=lỗi code, N=lỗi nhãn)")
    print(f"Bản máy-đọc: {out_jsonl}")


if __name__ == "__main__":
    main()
