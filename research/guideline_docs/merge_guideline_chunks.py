"""Nap chunks_guideline.jsonl vao chunks.jsonl (KB chinh).

Chay:  python guideline_docs/merge_guideline_chunks.py            # nap
       python guideline_docs/merge_guideline_chunks.py --dry-run  # chi in
       python guideline_docs/merge_guideline_chunks.py --remove   # go het chunk guideline

Buoc 1 la build_guideline_chunks.py -> chunks_guideline.jsonl (file rieng, soi duoc).
Buoc 2 la script nay -> ghep vao chunks.jsonl.

Idempotent: xoa het chunk co doc_id bat dau "guideline:" roi ghi lai lo moi, nen
chay bao nhieu lan cung ra mot ket qua. Chunk web khong bi dung toi.

SAU KHI CHAY phai rebuild ca 2 index, khong thi chunks.jsonl lech voi bm25/chroma:
    python scripts/build_kb.py --step bm25  --force
    python scripts/build_kb.py --step embed --force --batch-size 64
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_PATH = ROOT / "data" / "raw" / "chunks.jsonl"
GUIDELINE_PATH = ROOT / "data" / "raw" / "chunks_guideline.jsonl"
DOC_PREFIX = "guideline:"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for n, line in enumerate(path.open(encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            sys.exit(f"{path.name} dong {n} khong phai JSON hop le: {e}")
    return out


def is_guideline(row: dict) -> bool:
    return str(row.get("doc_id", "")).startswith(DOC_PREFIX)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="chi in, khong ghi")
    ap.add_argument("--remove", action="store_true",
                    help="go het chunk guideline khoi chunks.jsonl roi thoat")
    args = ap.parse_args()

    if not CHUNKS_PATH.exists():
        sys.exit(f"Chua co {CHUNKS_PATH.relative_to(ROOT)} "
                 f"(chay: python scripts/build_kb.py --step chunk)")
    current = read_jsonl(CHUNKS_PATH)
    web = [r for r in current if not is_guideline(r)]
    old_guideline = len(current) - len(web)

    if not web:
        sys.exit("chunks.jsonl khong con chunk web nao -- dung lai de tranh ghi de nham.")

    if args.remove:
        new = web
        label = "go chunk guideline"
    else:
        new_guideline = read_jsonl(GUIDELINE_PATH)
        if not new_guideline:
            sys.exit(f"Chua co {GUIDELINE_PATH.relative_to(ROOT)} hoac file rong "
                     f"(chay: python guideline_docs/build_guideline_chunks.py)")
        lac = [r for r in new_guideline if not is_guideline(r)]
        if lac:
            sys.exit(f"{len(lac)} chunk trong {GUIDELINE_PATH.name} khong co doc_id "
                     f"'{DOC_PREFIX}...' -- sai file hoac sai dinh dang.")
        ids = Counter(r["chunk_id"] for r in new_guideline)
        dup = [k for k, v in ids.items() if v > 1]
        if dup:
            sys.exit(f"{len(dup)} chunk_id trung trong {GUIDELINE_PATH.name}: {dup[:3]}")
        new = web + new_guideline
        label = "nap chunk guideline"

    print(f"{label}")
    print(f"  chunk web        : {len(web)}   (khong doi)")
    print(f"  guideline cu     : {old_guideline}  -> moi: {len(new) - len(web)}")
    print(f"  chunks.jsonl     : {len(current)} -> {len(new)}")
    if not args.remove:
        per = Counter(r.get("title") for r in new[len(web):])
        print("  theo tai lieu    :")
        for t, n in per.most_common():
            print(f"      {n:>4}  {t}")

    if args.dry_run:
        print("\n--dry-run: khong ghi gi.")
        return

    tmp = CHUNKS_PATH.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in new:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, CHUNKS_PATH)
    print(f"\n-> da ghi {CHUNKS_PATH.relative_to(ROOT)}")
    print("   Con phai rebuild index, khong thi bm25/chroma lech voi chunks.jsonl:")
    print("     python scripts/build_kb.py --step bm25  --force")
    print("     python scripts/build_kb.py --step embed --force --batch-size 64")


if __name__ == "__main__":
    main()
