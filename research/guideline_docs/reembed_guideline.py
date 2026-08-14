"""Embed lai RIENG phan guideline, khong dung 23k chunk web.

Vi sao can: build_kb.py --step embed --force xoa sach ChromaDB roi embed lai CA
24393 chunk -- vai tieng tren CPU -- du chi co ~1000 chunk guideline thay doi.
Moi lan chinh bo loc guideline ma phai tra gia do thi khong ai chinh nua.

Script nay:
  1. Xoa moi vector co chunk_id bat dau "guideline:" khoi ChromaDB
  2. Embed lai tu data/raw/chunks_guideline.jsonl
  3. Upsert vao chinh collection do

Chunk web KHONG bi dung toi -> tiet kiem ~95% thoi gian.

LUU Y ve chunk_id: build_guideline_chunks.py danh so tuan tu `{doc_id}_{i}` tren
danh sach chunk DA LOC. Bo bot mot chunk la moi chunk sau no doi so -> khong the
"chi embed phan moi", phai lam lai ca nhom guideline. Van re hon 24x so voi full.

Chay (theo dung thu tu):
    python guideline_docs/build_guideline_chunks.py     # -> chunks_guideline.jsonl
    python guideline_docs/merge_guideline_chunks.py     # -> chunks.jsonl
    python guideline_docs/reembed_guideline.py          # -> ChromaDB
    python scripts/build_kb.py --step bm25 --force      # BM25 nhanh, lam full
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

GUIDELINE_PATH = ROOT / "data" / "raw" / "chunks_guideline.jsonl"
CHROMA_DIR = ROOT / "data" / "chroma_db"
DOC_PREFIX = "guideline:"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not GUIDELINE_PATH.exists():
        sys.exit(f"Chua co {GUIDELINE_PATH.relative_to(ROOT)} "
                 f"(chay: python guideline_docs/build_guideline_chunks.py)")

    rows = [json.loads(line) for line in GUIDELINE_PATH.open(encoding="utf-8") if line.strip()]
    if not rows:
        sys.exit(f"{GUIDELINE_PATH.name} rong.")
    lac = [r for r in rows if not str(r.get("doc_id", "")).startswith(DOC_PREFIX)]
    if lac:
        sys.exit(f"{len(lac)} chunk khong co doc_id '{DOC_PREFIX}...' -- sai file.")

    from acne_llm.config import settings
    from acne_llm.rag.vectorstore import ChromaStore
    from acne_llm.schemas.kb import KBChunk

    store = ChromaStore(persist_dir=str(CHROMA_DIR))
    before = store.count()

    # Chroma khong loc duoc theo tien to id -> lay het id roi loc trong Python.
    got = store.col.get(include=[])
    old_ids = [i for i in (got.get("ids") or []) if str(i).startswith(DOC_PREFIX)]

    print(f"ChromaDB hien co : {before} vector ({len(old_ids)} guideline)")
    print(f"Se ghi lai       : {len(rows)} chunk guideline")
    print(f"Chunk web         : {before - len(old_ids)} -- KHONG dung toi")
    if args.dry_run:
        print("\n--dry-run: khong ghi gi.")
        return

    if old_ids:
        for i in range(0, len(old_ids), 500):
            store.col.delete(ids=old_ids[i:i + 500])
        print(f"-> da xoa {len(old_ids)} vector guideline cu (con {store.count()})")

    from acne_llm.rag.embedder import Embedder
    emb = Embedder(model_name=settings.embedding_model, device=settings.device,
                   batch_size=args.batch_size)

    step = args.batch_size * 4
    t0 = time.time()
    done = 0
    for i in range(0, len(rows), step):
        batch = rows[i:i + step]
        vecs = emb.embed_passages([r["text"] for r in batch])
        store.upsert([KBChunk(**r) for r in batch], vecs.tolist())
        done += len(batch)
        rate = done / max(time.time() - t0, 1e-6)
        print(f"   {done}/{len(rows)} | {rate:.0f} chunk/s | "
              f"ETA {(len(rows) - done) / max(rate, 1e-6) / 60:.1f} phut")

    after = store.count()
    print(f"\nChromaDB: {before} -> {after}")
    expected = before - len(old_ids) + len(rows)
    if after != expected:
        print(f"(!) Le ch: mong doi {expected}. Kiem tra lai truoc khi dung.")
    else:
        print("Khop. Con lai: python scripts/build_kb.py --step bm25 --force")


if __name__ == "__main__":
    main()
