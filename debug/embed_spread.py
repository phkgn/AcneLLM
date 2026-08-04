"""Embedder có phân biệt được gì không?

Triệu chứng: top-5 cho điểm 0.9992 / 0.9988 / 0.9983 / 0.9980 / 0.9979 cho năm
tài liệu khác hẳn nhau, và chunk không tìm lại được chính nó.

Hai khả năng, phải tách:
  A. index hỏng    — chunk vs CHÍNH NÓ không ra 1.0
  B. vector sụp đổ — mọi cặp đều ~0.99, embedding không mang thông tin

Chạy:  python debug/embed_spread.py
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    from acne_llm.config import settings
    from acne_llm.rag.embedder import Embedder
    from acne_llm.rag.vectorstore import ChromaStore

    store = ChromaStore(persist_dir=str(ROOT / "data" / "chroma_db"))
    emb = Embedder(model_name=settings.embedding_model, device=settings.device)

    # Lấy mẫu chunk kèm text ĐÚNG NHƯ ĐÃ LƯU — không đọc lại từ JSONL nguồn.
    raw = store.col.get(limit=400, include=["documents", "metadatas"])
    ids, docs = raw["ids"], raw["documents"]
    pool = [(i, d) for i, d in zip(ids, docs) if d and len(d) > 300]
    random.seed(0)
    pick = random.sample(pool, min(30, len(pool)))

    # ── A. chunk có tìm lại được chính nó không ────────────────────────
    print("A. Tìm lại chính nó (query = text đã lưu, không sửa gì)\n")
    ranks, selfsim = [], []
    for cid, text in pick[:15]:
        q = emb._embed_query_raw(text)
        res = store.query(q, top_k=5)
        got = (res.get("ids") or [[]])[0]
        dist = (res.get("distances") or [[]])[0]
        r = got.index(cid) + 1 if cid in got else 99
        ranks.append(r)
        if cid in got:
            selfsim.append(1 - dist[got.index(cid)])
        print(f"  hạng {r if r < 99 else '>5':>3}   top1={got[0][:40]:<42}"
              f" sim={1 - dist[0]:.4f}")
    ok = sum(1 for r in ranks if r == 1)
    print(f"\n  ra hạng 1: {ok}/{len(ranks)}"
          + (f"   sim với chính nó: {np.mean(selfsim):.4f}" if selfsim else ""))
    if ok < len(ranks):
        print("  ⚠ INDEX HỎNG — vector đã lưu KHÁC vector tính lại từ cùng text.")
        print("    Nghi can: build dùng embed_passages, khác tham số/độ dài cắt,")
        print("    hoặc index build bằng model khác model đang cấu hình.")

    # ── B. vector có sụp đổ không ──────────────────────────────────────
    print("\n\nB. Độ phân tán — 30 chunk ngẫu nhiên, tự tính vector\n")
    V = np.stack([emb._embed_query_raw(t) for _, t in pick])
    S = V @ V.T
    off = S[~np.eye(len(V), dtype=bool)]
    print(f"  cosine giữa các cặp KHÁC nhau:")
    print(f"    min={off.min():.4f}  p25={np.percentile(off, 25):.4f}  "
          f"median={np.median(off):.4f}  p75={np.percentile(off, 75):.4f}  "
          f"max={off.max():.4f}")
    print(f"    độ lệch chuẩn = {off.std():.4f}")
    print(f"  chuẩn vector: {np.linalg.norm(V, axis=1).mean():.4f} "
          f"(phải = 1.0 nếu normalize)")

    print("\n=> ", end="")
    if off.mean() > 0.95:
        print("VECTOR SỤP ĐỔ. Mọi chunk gần như trùng hướng — embedding không\n"
              "   mang thông tin phân biệt. Đổi model là bắt buộc, không phải tuỳ chọn.")
    elif off.mean() > 0.80:
        print("Phân tán hẹp nhưng chưa sụp. Bình thường với domain hẹp (toàn về mụn).\n"
              "   Trần 21% là do model yếu, không phải do index hỏng.")
    else:
        print("Phân tán bình thường. Vấn đề nằm chỗ khác — xem lại phần A.")


if __name__ == "__main__":
    main()
