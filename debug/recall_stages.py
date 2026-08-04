"""Recall theo TỪNG TẦNG — tách embedder khỏi fusion/prune khỏi reranker.

Câu hỏi: retriever trượt 89% tài liệu vàng là do đâu?

    tầng 1  dense thô @50    chỉ embedder + Chroma. Không boost, không prune,
                             không BM25, không rerank.
    tầng 2  retrieve() @50   thêm BM25 + RRF + trust boost + prune 30%
    tầng 3  retrieve() @15   đúng chat_retrieve_top_k của production
    tầng 4  sau rerank @5    lấy từ rows.jsonl của run đã chạy

Đọc kết quả:
    tầng 1 cao, tầng 4 thấp  → embedder ổn, hỏng ở fusion/prune/rerank
    tầng 1 đã thấp           → embedder không tìm ra. Rerank không cứu được.

Chạy:  python debug/recall_stages.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DATASET = ROOT / "evaluation/datasets/eval_set.jsonl"
ROWS = ROOT / "evaluation/reports/full_eval/ablation/rows.jsonl"
DEEP = 50


def load_gold() -> list[dict]:
    out = []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("relevant_chunk_ids"):
            out.append(row)
    return out


def production_at5() -> dict[str, list[str]]:
    """Chunk mà production THỰC SỰ đã dùng — khỏi chạy lại, đọc từ checkpoint."""
    got = {}
    if not ROWS.exists():
        return got
    for line in ROWS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry["arm"] == "RRR" and entry["record"].get("ok"):
            got[entry["record"]["sample_id"]] = entry["record"].get("used_chunks") or []
    return got


def main() -> None:
    from acne_llm.config import settings
    from acne_llm.di import build_container

    container = build_container(settings)
    if not container.retriever or not container.embedder or not container.store:
        raise SystemExit("RAG chưa sẵn sàng — kiểm tra data/chroma_db và bm25_index.pkl")

    samples, at5 = load_gold(), production_at5()
    print(f"{len(samples)} câu có chunk vàng · sâu {DEEP}\n")

    hit = {k: [0, 0] for k in ("dense_thô", "retrieve_50", "retrieve_15", "rerank_5")}
    rank_when_found: list[int] = []

    for i, row in enumerate(samples, 1):
        query = row["user_query"]
        gold = set(row["relevant_chunk_ids"])
        gold_docs = {c.rsplit("::", 1)[0] for c in gold}

        # ── tầng 1: dense thô, không qua retrieve() ──────────────────────
        qvec = container.embedder.embed_query(query)
        raw = container.store.query(qvec, top_k=DEEP)
        dense_ids = (raw.get("ids") or [[]])[0]

        # ── tầng 2 & 3: qua retrieve() đầy đủ ────────────────────────────
        r50 = [c.chunk_id for c in container.retriever.retrieve(query, top_k=DEEP).chunks]
        r15 = [c.chunk_id for c in container.retriever.retrieve(query, top_k=15).chunks]

        for name, ids in (("dense_thô", dense_ids), ("retrieve_50", r50),
                          ("retrieve_15", r15), ("rerank_5", at5.get(row["sample_id"], []))):
            hit[name][0] += bool(set(ids) & gold)
            hit[name][1] += bool({c.rsplit("::", 1)[0] for c in ids} & gold_docs)

        found = [j for j, c in enumerate(dense_ids, 1) if c in gold]
        if found:
            rank_when_found.append(found[0])
        print(f"\r  {i}/{len(samples)}", end="", flush=True)

    n = len(samples)
    print("\n")
    print(f"{'tầng':14}{'recall chunk':>14}{'recall tài liệu':>18}")
    for name, (c, d) in hit.items():
        print(f"{name:14}{f'{c}/{n} = {c/n:.0%}':>14}{f'{d}/{n} = {d/n:.0%}':>18}")

    print(f"\nKhi dense thô tìm được, chunk vàng nằm ở hạng: "
          f"{sorted(rank_when_found) if rank_when_found else 'không lần nào'}")
    if rank_when_found:
        deep = sum(1 for r in rank_when_found if r > 15)
        print(f"  nằm sâu hơn 15 (ngoài tầm chat_retrieve_top_k): {deep}/{len(rank_when_found)}")

    # ── Index có lành không: lấy chính chunk vàng làm query, tìm lại ────
    # Không ra hạng 1 nghĩa là index hỏng thật (model embed lúc build khác lúc
    # query, hoặc quên normalize vector) — chưa cần bàn tới ngữ nghĩa.
    print("\nIndex có lành không — lấy nguyên văn chunk làm query, tìm lại chính nó:")
    self_rank = []
    for row in samples[:20]:
        cid = row["relevant_chunk_ids"][0]
        got = container.store.get_by_ids([cid])
        text = (got.get("documents") or [""])[0]
        if not text:
            continue
        ids = (container.store.query(container.embedder.embed_query(text), top_k=5)
               .get("ids") or [[]])[0]
        self_rank.append(ids.index(cid) + 1 if cid in ids else 99)
    perfect = sum(1 for r in self_rank if r == 1)
    print(f"  ra hạng 1: {perfect}/{len(self_rank)}   hạng: {sorted(self_rank)}")
    if perfect < len(self_rank) * 0.9:
        print("  ⚠ INDEX HỎNG — chunk không tìm lại được chính nó. Sửa cái này trước.")

    print("\n=> ", end="")
    c50, c5 = hit["dense_thô"][0] / n, hit["rerank_5"][0] / n
    if c50 < 0.25:
        print("EMBEDDER. Chunk vàng không nổi lên kể cả ở top-50 thô.\n"
              "   Rerank/boost không cứu được. Rebuild index bằng model đa ngữ.")
    elif c50 - c5 > 0.20:
        print("FUSION/PRUNE/RERANK. Embedder tìm ra, tầng sau vứt đi.\n"
              "   Soi _MIN_FUSION_SCORE_RELATIVE=0.30 và chat_retrieve_top_k=15.")
    else:
        print("Không tầng nào nổi bật — cần đo thêm.")


if __name__ == "__main__":
    main()
