"""Bày ra traceback thật của lỗi '_type' mà di.py đang nuốt.

di.py bắt Exception rồi chỉ log message, nên ta mất chỗ ném. Chạy thẳng hai
lệnh đó ngoài try/except.

    python debug/why_rag_off.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    import chromadb
    print(f"chromadb  {chromadb.__version__}")
    for name in ("pydantic", "numpy", "rank_bm25"):
        try:
            print(f"{name:10}{__import__(name).__version__}")
        except Exception as e:
            print(f"{name:10}— ({e})")

    from acne_llm.config import settings
    chroma_dir = ROOT / "data" / "chroma_db"
    bm25_path = ROOT / "data" / "bm25_index.pkl"
    print(f"\nchroma_db  {chroma_dir.exists()}  ({chroma_dir})")
    print(f"bm25.pkl   {bm25_path.exists()}  "
          f"({bm25_path.stat().st_size / 1e6:.1f} MB)" if bm25_path.exists() else "")

    from acne_llm.rag.vectorstore import ChromaStore
    from acne_llm.rag.sparse import BM25Index

    print("\n--- ChromaStore ---")
    try:
        store = ChromaStore(persist_dir=str(chroma_dir))
        print(f"OK · {store.count()} chunk")
    except Exception:
        traceback.print_exc()
        store = None

    print("\n--- BM25Index.load ---")
    try:
        BM25Index.load(str(bm25_path))
        print("OK")
    except Exception:
        traceback.print_exc()

    if store is not None:
        print("\n--- collection thô (bỏ qua wrapper) ---")
        try:
            import chromadb as ch
            client = ch.PersistentClient(path=str(chroma_dir))
            print("collections:", [c.name for c in client.list_collections()])
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    main()
