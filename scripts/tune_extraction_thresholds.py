#!/usr/bin/env python3
"""Do do phu/do chinh xac cua extraction confidence tren golden set.

Chay extractor (extract_with_confidence) tren data/golden_extraction.jsonl,
doi chieu nhan, bao:
  - skin_type: accuracy + ty le dat nguong confidence ky vong
  - products : recall cua products_contains (fuzzy bat sai chinh ta)
  - inflammation: accuracy + confidence
Khong goi LLM. Dung de tinh chinh nguong trong .env (heuristic -> golden).

Usage: python scripts/tune_extraction_thresholds.py [path.jsonl]
"""
from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from acne_llm.chat.fallback.rule_extractor import extract_with_confidence


def load(path):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def main(path="data/golden_extraction.jsonl"):
    rows = list(load(path))
    skin_total = skin_ok = skin_conf_ok = 0
    prod_need = prod_hit = 0
    infl_total = infl_ok = 0

    for r in rows:
        ec = extract_with_confidence(r["text"])

        if "skin_type" in r:
            skin_total += 1
            got = ec.skin_type.value
            if got == r["skin_type"]:
                skin_ok += 1
            cmin = r.get("skin_type_conf_min")
            cmax = r.get("skin_type_conf_max")
            ok = True
            if cmin is not None:
                ok = ok and ec.skin_type.confidence >= cmin
            if cmax is not None:
                ok = ok and ec.skin_type.confidence <= cmax
            skin_conf_ok += int(ok)

        if "products_contains" in r:
            for p in r["products_contains"]:
                prod_need += 1
                if p in ec.products.values:
                    prod_hit += 1

        if r.get("products_empty"):
            if ec.products.values:
                print(f"  [WARN] products khong rong cho: {r['text']!r} -> {ec.products.values}")

        if "inflammation" in r:
            infl_total += 1
            if ec.inflammation.value == r["inflammation"]:
                infl_ok += 1

    print("=== GOLDEN SET EVAL ===")
    print(f"rows: {len(rows)}")
    if skin_total:
        print(f"skin_type accuracy : {skin_ok}/{skin_total} = {skin_ok/skin_total:.2f}")
        print(f"skin_type conf-band: {skin_conf_ok}/{skin_total} = {skin_conf_ok/skin_total:.2f}")
    if prod_need:
        print(f"products recall    : {prod_hit}/{prod_need} = {prod_hit/prod_need:.2f}")
    if infl_total:
        print(f"inflammation acc   : {infl_ok}/{infl_total} = {infl_ok/infl_total:.2f}")


if __name__ == "__main__":
    main(*sys.argv[1:])
